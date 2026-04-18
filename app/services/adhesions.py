from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import normalize_email
from app.models.adhesion import Adhesion
from app.models.enums import EngagementType, PaymentMode
from app.repositories.adhesions import AdhesionRepository
from app.repositories.geo import GeoRepository
from app.storage.local import LocalStorage


@dataclass(frozen=True)
class CreateAdhesionInput:
    nom: str
    prenom: str
    date_naissance: date
    lieu_naissance: str
    profession: str
    tel_mobile: str
    tel_fixe: str | None
    email: str
    cni: str
    carte_electeur: str | None
    carte_pastef: str | None
    region_domicile_id: uuid.UUID
    departement_domicile_id: uuid.UUID
    commune_domicile_id: uuid.UUID
    region_militantisme_id: uuid.UUID
    departement_militantisme_id: uuid.UUID
    commune_militantisme_id: uuid.UUID | None
    fonction_professionnelle: str
    engagement: EngagementType
    commissariat: str
    mode_paiement: PaymentMode
    montant_adhesion: int
    certification: bool
    reference_paiement: str | None


class AdhesionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.adhesions = AdhesionRepository(session)
        self.geo = GeoRepository(session)
        self.storage = LocalStorage()

    async def _validate_region_departement(self, *, region_id: uuid.UUID, departement_id: uuid.UUID) -> None:
        departement = await self.geo.get_departement(departement_id)
        if not departement or departement.region_id != region_id:
            raise HTTPException(status_code=400, detail="Département incohérent avec la région")

    async def _validate_departement_commune(self, *, departement_id: uuid.UUID, commune_id: uuid.UUID) -> None:
        commune = await self.geo.get_commune(commune_id)
        if not commune or commune.departement_id != departement_id:
            raise HTTPException(status_code=400, detail="Commune incohérente avec le département")

    def _idempotency_hash(self, data: dict, photo: UploadFile, cv: UploadFile) -> str:
        payload = dict(data)
        payload["photo_filename"] = photo.filename
        payload["cv_filename"] = cv.filename
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    async def create(
        self,
        *,
        data: CreateAdhesionInput,
        photo: UploadFile,
        cv: UploadFile,
        idempotency_key: str | None,
    ) -> Adhesion:
        if not data.certification:
            raise HTTPException(status_code=400, detail="Certification requise")
        if data.montant_adhesion < 0:
            raise HTTPException(status_code=400, detail="Montant invalide")

        await self._validate_region_departement(region_id=data.region_domicile_id, departement_id=data.departement_domicile_id)
        await self._validate_departement_commune(
            departement_id=data.departement_domicile_id, commune_id=data.commune_domicile_id
        )

        await self._validate_region_departement(
            region_id=data.region_militantisme_id, departement_id=data.departement_militantisme_id
        )
        if data.commune_militantisme_id is not None:
            await self._validate_departement_commune(
                departement_id=data.departement_militantisme_id, commune_id=data.commune_militantisme_id
            )

        payload_dict = data.__dict__
        idem_hash = None
        existing = None
        if idempotency_key:
            idem_hash = self._idempotency_hash(payload_dict, photo, cv)
            existing = await self.adhesions.get_by_idempotency_key(idempotency_key)
            if existing:
                if existing.idempotency_hash and existing.idempotency_hash != idem_hash:
                    raise HTTPException(status_code=409, detail="Idempotency-Key déjà utilisée avec un autre payload")
                return existing

        photo_url = await self.storage.save(file=photo, subdir="photos")
        cv_url = await self.storage.save(file=cv, subdir="cvs")

        adhesion = Adhesion(
            nom=data.nom,
            prenom=data.prenom,
            date_naissance=data.date_naissance,
            lieu_naissance=data.lieu_naissance,
            profession=data.profession,
            tel_mobile=data.tel_mobile,
            tel_fixe=data.tel_fixe,
            email=normalize_email(data.email),
            cni=data.cni,
            carte_electeur=data.carte_electeur,
            carte_pastef=data.carte_pastef,
            region_domicile_id=data.region_domicile_id,
            departement_domicile_id=data.departement_domicile_id,
            commune_domicile_id=data.commune_domicile_id,
            region_militantisme_id=data.region_militantisme_id,
            departement_militantisme_id=data.departement_militantisme_id,
            commune_militantisme_id=data.commune_militantisme_id,
            fonction_professionnelle=data.fonction_professionnelle,
            engagement=data.engagement,
            commissariat=data.commissariat,
            mode_paiement=data.mode_paiement,
            montant_adhesion=data.montant_adhesion,
            reference_paiement=data.reference_paiement,
            certification=data.certification,
            photo_url=photo_url,
            cv_url=cv_url,
            idempotency_key=idempotency_key,
            idempotency_hash=idem_hash,
        )

        await self.adhesions.create(adhesion)
        await self.session.commit()
        await self.session.refresh(adhesion)
        return adhesion
