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

    async def lookup_details(
        self,
        *,
        adhesion_id: uuid.UUID | None,
        email: str | None,
        cni: str | None,
        tel_mobile: str | None,
    ) -> Adhesion:
        criteria = [
            ("id", adhesion_id),
            ("email", email),
            ("cni", cni),
            ("tel_mobile", tel_mobile),
        ]
        provided = [(k, v) for (k, v) in criteria if v is not None and str(v).strip() != ""]
        if not provided:
            raise HTTPException(status_code=400, detail="Un critère de recherche est requis (id, email, cni, tel_mobile)")
        if len(provided) > 1:
            raise HTTPException(status_code=400, detail="Un seul critère de recherche doit être fourni")

        key, value = provided[0]
        if key == "id":
            adhesion = await self.adhesions.get_by_id(value)
        elif key == "email":
            adhesion = await self.adhesions.get_latest_by_email(normalize_email(str(value)))
        elif key == "cni":
            adhesion = await self.adhesions.get_latest_by_cni(str(value).strip())
        else:
            adhesion = await self.adhesions.get_latest_by_tel_mobile(str(value).strip())

        if not adhesion:
            raise HTTPException(status_code=404, detail="Adhésion introuvable")
        return adhesion

    async def _validate_region_departement(self, *, region_id: uuid.UUID, departement_id: uuid.UUID) -> None:
        departement = await self.geo.get_departement(departement_id)
        if not departement or departement.region_id != region_id:
            raise HTTPException(status_code=400, detail="Département incohérent avec la région")

    async def _validate_departement_commune(self, *, departement_id: uuid.UUID, commune_id: uuid.UUID) -> None:
        commune = await self.geo.get_commune(commune_id)
        if not commune or commune.departement_id != departement_id:
            raise HTTPException(status_code=400, detail="Commune incohérente avec le département")

    def _idempotency_hash(self, data: dict, photo_recto: UploadFile, photo_verso: UploadFile, cv: UploadFile) -> str:
        payload = dict(data)
        payload["photo_recto_filename"] = photo_recto.filename
        payload["photo_verso_filename"] = photo_verso.filename
        payload["cv_filename"] = cv.filename
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    async def create(
        self,
        *,
        data: CreateAdhesionInput,
        photo_recto: UploadFile,
        photo_verso: UploadFile,
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
            idem_hash = self._idempotency_hash(payload_dict, photo_recto, photo_verso, cv)
            existing = await self.adhesions.get_by_idempotency_key(idempotency_key)
            if existing:
                if existing.idempotency_hash and existing.idempotency_hash != idem_hash:
                    raise HTTPException(status_code=409, detail="Idempotency-Key déjà utilisée avec un autre payload")
                return existing

        photo_recto_url = await self.storage.save(file=photo_recto, subdir="photos")
        photo_verso_url = await self.storage.save(file=photo_verso, subdir="photos")
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
            photo_url=photo_recto_url,
            photo_recto_url=photo_recto_url,
            photo_verso_url=photo_verso_url,
            cv_url=cv_url,
            idempotency_key=idempotency_key,
            idempotency_hash=idem_hash,
        )

        await self.adhesions.create(adhesion)
        await self.session.commit()
        await self.session.refresh(adhesion)
        return adhesion
