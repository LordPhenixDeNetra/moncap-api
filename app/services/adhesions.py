from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
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
    est_diaspora: bool
    niveau_etude: str | None
    annees_experience: int | None
    biographie: str | None
    region_domicile_id: uuid.UUID | None
    departement_domicile_id: uuid.UUID | None
    commune_domicile_id: uuid.UUID | None
    region_militantisme_id: uuid.UUID | None
    departement_militantisme_id: uuid.UUID | None
    commune_militantisme_id: uuid.UUID | None
    pays_domicile_id: uuid.UUID | None
    ville_domicile: str | None
    pays_militantisme_id: uuid.UUID | None
    ville_militantisme: str | None
    fonction_professionnelle: str
    engagement: list[EngagementType]
    commissariat: str
    commissariat_scientifique_principal: str | None
    commissariat_scientifique_secondaire: str | None
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
        if not data.engagement:
            raise HTTPException(status_code=400, detail="Au moins un type d'engagement est requis")

        if data.commissariat.strip().lower() == "commissariat scientifique":
            if not data.commissariat_scientifique_principal or not data.commissariat_scientifique_principal.strip():
                raise HTTPException(status_code=400, detail="Le commissariat scientifique principal est requis")
            if not data.commissariat_scientifique_secondaire or not data.commissariat_scientifique_secondaire.strip():
                raise HTTPException(status_code=400, detail="Le commissariat scientifique secondaire est requis")

        if data.est_diaspora:
            if not data.pays_domicile_id:
                raise HTTPException(status_code=400, detail="Le pays de domicile est requis pour un adhérent de la diaspora")
            if not data.ville_domicile or not data.ville_domicile.strip():
                raise HTTPException(status_code=400, detail="La ville de domicile est requise pour un adhérent de la diaspora")
        else:
            if not data.region_domicile_id or not data.departement_domicile_id or not data.commune_domicile_id:
                raise HTTPException(status_code=400, detail="La région, le département et la commune de domicile sont requis")
            if not data.region_militantisme_id or not data.departement_militantisme_id:
                raise HTTPException(status_code=400, detail="La région et le département de militantisme sont requis")
            await self._validate_region_departement(region_id=data.region_domicile_id, departement_id=data.departement_domicile_id)
            await self._validate_departement_commune(departement_id=data.departement_domicile_id, commune_id=data.commune_domicile_id)
            await self._validate_region_departement(region_id=data.region_militantisme_id, departement_id=data.departement_militantisme_id)
            if data.commune_militantisme_id is not None:
                await self._validate_departement_commune(departement_id=data.departement_militantisme_id, commune_id=data.commune_militantisme_id)

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

        email_norm = normalize_email(data.email)
        conflict = await self.adhesions.get_conflict_by_email(email_norm)
        if conflict:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DUPLICATE_EMAIL",
                    "field": "email",
                    "message": "Une adhésion existe déjà avec cet email",
                },
            )

        cni_norm = str(data.cni).strip()
        conflict = await self.adhesions.get_conflict_by_cni(cni_norm)
        if conflict:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DUPLICATE_CNI",
                    "field": "cni",
                    "message": "Une adhésion existe déjà avec ce CNI",
                },
            )

        if data.carte_electeur and str(data.carte_electeur).strip() != "":
            carte_electeur_norm = str(data.carte_electeur).strip()
            conflict = await self.adhesions.get_conflict_by_carte_electeur(carte_electeur_norm)
            if conflict:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "DUPLICATE_CARTE_ELECTEUR",
                        "field": "carte_electeur",
                        "message": "Une adhésion existe déjà avec cette carte d'électeur",
                    },
                )

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
            email=email_norm,
            cni=cni_norm,
            carte_electeur=carte_electeur_norm if data.carte_electeur and str(data.carte_electeur).strip() != "" else None,
            carte_pastef=data.carte_pastef,
            est_diaspora=data.est_diaspora,
            niveau_etude=data.niveau_etude,
            annees_experience=data.annees_experience,
            biographie=data.biographie,
            region_domicile_id=data.region_domicile_id,
            departement_domicile_id=data.departement_domicile_id,
            commune_domicile_id=data.commune_domicile_id,
            region_militantisme_id=data.region_militantisme_id,
            departement_militantisme_id=data.departement_militantisme_id,
            commune_militantisme_id=data.commune_militantisme_id,
            pays_domicile_id=data.pays_domicile_id,
            ville_domicile=data.ville_domicile,
            pays_militantisme_id=data.pays_militantisme_id,
            ville_militantisme=data.ville_militantisme,
            fonction_professionnelle=data.fonction_professionnelle,
            engagement=[e.value for e in data.engagement],
            commissariat=data.commissariat,
            commissariat_scientifique_principal=data.commissariat_scientifique_principal,
            commissariat_scientifique_secondaire=data.commissariat_scientifique_secondaire,
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

        try:
            await self.adhesions.create(adhesion)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DUPLICATE_IDENTIFIER",
                    "message": "Une adhésion existe déjà avec un identifiant déjà utilisé (email, cni ou carte_electeur)",
                },
            )
        await self.session.refresh(adhesion)
        return adhesion
