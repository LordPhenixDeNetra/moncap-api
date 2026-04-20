from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import normalize_email
from app.db.session import get_db
from app.models.enums import EngagementType, PaymentMode
from app.repositories.adhesions import AdhesionRepository
from app.schemas.adhesions import AdhesionCreatedResponse, AdhesionPublicListResponse
from app.services.adhesions import AdhesionService, CreateAdhesionInput

router = APIRouter(prefix="/adhesions")


@router.post(
    "",
    response_model=AdhesionCreatedResponse,
    summary="Créer une nouvelle adhésion",
    description="Permet à un citoyen de soumettre une demande d'adhésion. Nécessite l'envoi de fichiers (photo_recto, photo_verso et CV) via multipart/form-data. Gère l'idempotence via l'en-tête 'Idempotency-Key'.",
)
async def create_adhesion(
    nom: str = Form(...),
    prenom: str = Form(...),
    date_naissance: date = Form(...),
    lieu_naissance: str = Form(...),
    profession: str = Form(...),
    tel_mobile: str = Form(...),
    tel_fixe: str | None = Form(None),
    email: str = Form(...),
    cni: str = Form(...),
    carte_electeur: str | None = Form(None),
    carte_pastef: str | None = Form(None),
    region_domicile_id: uuid.UUID = Form(...),
    departement_domicile_id: uuid.UUID = Form(...),
    commune_domicile_id: uuid.UUID = Form(...),
    region_militantisme_id: uuid.UUID = Form(...),
    departement_militantisme_id: uuid.UUID = Form(...),
    commune_militantisme_id: uuid.UUID | None = Form(None),
    fonction_professionnelle: str = Form(...),
    engagement: EngagementType = Form(...),
    commissariat: str = Form(...),
    mode_paiement: PaymentMode = Form(...),
    montant_adhesion: int = Form(25000),
    reference_paiement: str | None = Form(None),
    certification: bool = Form(...),
    photo_recto: UploadFile | None = File(None),
    photo_verso: UploadFile = File(...),
    photo: UploadFile | None = File(None),
    cv: UploadFile = File(...),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    photo_recto_final = photo_recto or photo
    if not photo_recto_final:
        raise HTTPException(status_code=422, detail="photo_recto (ou photo) est requis")

    data = CreateAdhesionInput(
        nom=nom,
        prenom=prenom,
        date_naissance=date_naissance,
        lieu_naissance=lieu_naissance,
        profession=profession,
        tel_mobile=tel_mobile,
        tel_fixe=tel_fixe,
        email=normalize_email(email),
        cni=cni,
        carte_electeur=carte_electeur,
        carte_pastef=carte_pastef,
        region_domicile_id=region_domicile_id,
        departement_domicile_id=departement_domicile_id,
        commune_domicile_id=commune_domicile_id,
        region_militantisme_id=region_militantisme_id,
        departement_militantisme_id=departement_militantisme_id,
        commune_militantisme_id=commune_militantisme_id,
        fonction_professionnelle=fonction_professionnelle,
        engagement=engagement,
        commissariat=commissariat,
        mode_paiement=mode_paiement,
        montant_adhesion=montant_adhesion,
        certification=certification,
        reference_paiement=reference_paiement,
    )
    adhesion = await AdhesionService(db).create(
        data=data,
        photo_recto=photo_recto_final,
        photo_verso=photo_verso,
        cv=cv,
        idempotency_key=idempotency_key,
    )
    return {"data": {"id": adhesion.id, "statut": adhesion.statut, "createdAt": adhesion.created_at}}


@router.get(
    "",
    response_model=AdhesionPublicListResponse,
    summary="Suivre ses demandes d'adhésion",
    description="Permet à un citoyen de lister ses demandes d'adhésion en cours ou passées à partir de son adresse email.",
)
async def list_adhesions(email: str, db: AsyncSession = Depends(get_db)):
    email = normalize_email(email)
    if not email:
        raise HTTPException(status_code=400, detail="Email requis")
    items = await AdhesionRepository(db).list_by_email(email)
    return {
        "data": [
            {"id": x.id, "statut": x.statut, "createdAt": x.created_at, "motifRejet": x.motif_rejet} for x in items
        ]
    }
