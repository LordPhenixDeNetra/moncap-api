from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_roles
from app.core.settings import get_settings
from app.db.session import get_db
from app.models.enums import AdhesionStatus, DisabledReason
from app.repositories.adhesions import AdhesionRepository
from app.schemas.admin import (
    AdminAdhesionListResponse,
    AdminConfirmPaymentRequest,
    AdminUpdateAdhesionRequest,
    AdminUpdateAdhesionInfoRequest,
    AdminUpdateAdhesionResponse,
)
from app.schemas.adhesions import AdhesionDetailResponse
from app.schemas.radiation_admin import (
    ApplyMassiveRadiationRequest,
    ApplyMassiveRadiationResponse,
    RadiationCandidateOut,
    RadiationCandidatesResponse,
    RadiationResultItem,
    RadierManuelRequest,
    RehabiliterRequest,
)
from app.services.adhesion_mail_templates import build_adhesion_status_changed, build_payment_confirmed
from app.services.adhesions import AdhesionService
from app.services.mail import send_email_best_effort
from app.services.radiation_mail_templates import (
    build_radiation_notification,
    build_reactivation_notification,
    resolve_recipient_email,
)
from app.services.radiation_service import RadiationService

_ALL_STAFF_ROLES = ("admin", "comite_accueil", "comite_directoire")

router = APIRouter(prefix="/admin")

read_router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_roles(*_ALL_STAFF_ROLES))],
)

write_router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_roles("admin"))],
)


@read_router.get(
    "/adhesions",
    response_model=AdminAdhesionListResponse,
    summary="Lister les adhésions (Admin)",
    description="Permet aux administrateurs de lister, filtrer et rechercher parmi toutes les demandes d'adhésion. Supporte la pagination.",
)
async def list_adhesions(
    limit: int = 50,
    offset: int = 0,
    status: AdhesionStatus | None = None,
    commissariat: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    items, total = await AdhesionRepository(db).list_admin(
        limit=limit,
        offset=offset,
        status=status,
        commissariat=commissariat,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )
    return {
        "data": [
            {
                "id": x.id,
                "nom": x.nom,
                "prenom": x.prenom,
                "email": x.email,
                "cni": x.cni,
                "commissariat": x.commissariat,
                "statut": x.statut,
                "createdAt": x.created_at,
            }
            for x in items
        ],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@write_router.patch(
    "/adhesions/{adhesion_id}",
    response_model=AdminUpdateAdhesionResponse,
    summary="Mettre à jour le statut d'une adhésion",
    description="Permet de demander un complément d'information ou de rejeter une demande d'adhésion. Un motif est obligatoire en cas de rejet.",
)
async def update_adhesion(
    adhesion_id: uuid.UUID,
    payload: AdminUpdateAdhesionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if payload.statut not in [AdhesionStatus.rejetee, AdhesionStatus.complement]:
        raise HTTPException(status_code=400, detail="Cette action n'est pas autorisée pour ce statut")

    if payload.statut == AdhesionStatus.rejetee and not (payload.motif_rejet and payload.motif_rejet.strip()):
        raise HTTPException(status_code=400, detail="Motif requis si rejet")
    before = await AdhesionRepository(db).get_by_id(adhesion_id)
    if not before:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    rowcount = await AdhesionRepository(db).update_status(
        adhesion_id=adhesion_id, statut=payload.statut, motif_rejet=payload.motif_rejet
    )
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    await db.commit()
    after = await AdhesionRepository(db).get_by_id(adhesion_id)
    settings = get_settings()
    if settings.mail_enabled and after and after.email:
        subject, text, html = build_adhesion_status_changed(
            adhesion=after, old_status=before.statut, base_url=settings.public_base_url
        )
        background_tasks.add_task(
            send_email_best_effort,
            to=after.email,
            subject=subject,
            text=text,
            html=html,
            settings=settings,
        )
    return {"data": {"updated": True}}

@read_router.get(
    "/adhesions/lookup",
    response_model=AdhesionDetailResponse,
    summary="Récupérer une adhésion (lookup)",
    description="Retourne la fiche complète d'une adhésion en recherchant par id, email, cni ou tel_mobile. Un seul critère doit être fourni.",
)
async def lookup_adhesion(
    id: uuid.UUID | None = None,
    email: str | None = None,
    cni: str | None = None,
    tel_mobile: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    adhesion = await AdhesionService(db).lookup_details(
        adhesion_id=id, email=email, cni=cni, tel_mobile=tel_mobile
    )
    return {"data": adhesion}

@write_router.patch(
    "/adhesions/{adhesion_id}/info",
    response_model=AdhesionDetailResponse,
    summary="Mettre à jour les informations d'une adhésion",
    description="Permet à l’admin de corriger les informations d’une adhésion (hors suppression).",
)
async def update_adhesion_info(
    adhesion_id: uuid.UUID,
    payload: AdminUpdateAdhesionInfoRequest,
    db: AsyncSession = Depends(get_db),
):
    updated = await AdhesionService(db).admin_update_info(adhesion_id=adhesion_id, payload=payload.model_dump(exclude_unset=True))
    return {"data": updated}


@write_router.patch(
    "/adhesions/{adhesion_id}/files",
    response_model=AdhesionDetailResponse,
    summary="Remplacer des fichiers d'une adhésion",
    description="Permet à l’admin de remplacer profile_photo, photo_recto, photo_verso et/ou cv.",
)
async def update_adhesion_files(
    adhesion_id: uuid.UUID,
    profile_photo: UploadFile | None = File(None),
    photo_recto: UploadFile | None = File(None),
    photo_verso: UploadFile | None = File(None),
    cv: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    updated = await AdhesionService(db).admin_update_files(
        adhesion_id=adhesion_id,
        profile_photo=profile_photo,
        photo_recto=photo_recto,
        photo_verso=photo_verso,
        cv=cv,
    )
    return {"data": updated}


@write_router.delete(
    "/adhesions/{adhesion_id}",
    response_model=AdminUpdateAdhesionResponse,
    summary="Supprimer une adhésion",
    description="Suppression logique (soft delete). L’adhésion est masquée des listes/lookup.",
)
async def delete_adhesion(
    adhesion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await AdhesionService(db).admin_soft_delete(adhesion_id=adhesion_id)
    return {"data": {"deleted": True}}


@write_router.patch(
    "/adhesions/{adhesion_id}/payment",
    response_model=AdminUpdateAdhesionResponse,
    summary="Confirmer le paiement d'une adhésion",
    description="Permet de marquer le paiement comme confirmé et d'enregistrer une référence. Envoie un email à l’adhérant si paiement confirmé.",
)
async def confirm_payment(
    adhesion_id: uuid.UUID,
    payload: AdminConfirmPaymentRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    rowcount = await AdhesionRepository(db).update_payment(
        adhesion_id=adhesion_id,
        paiement_confirme=payload.paiement_confirme,
        reference_paiement=payload.reference_paiement,
    )
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Adhésion introuvable")
    await db.commit()
    adhesion = await AdhesionRepository(db).get_by_id(adhesion_id)
    settings = get_settings()
    if settings.mail_enabled and payload.paiement_confirme and adhesion and adhesion.email:
        subject, text, html = build_payment_confirmed(adhesion=adhesion, base_url=settings.public_base_url)
        background_tasks.add_task(
            send_email_best_effort,
            to=adhesion.email,
            subject=subject,
            text=text,
            html=html,
            settings=settings,
        )
    return {"data": {"updated": True}}


@read_router.get(
    "/adhesions/export.csv",
    summary="Exporter les adhésions en CSV",
    description="Génère un fichier CSV contenant les données des adhésions filtrées. Idéal pour les rapports Excel.",
)
async def export_csv(
    status: AdhesionStatus | None = None,
    commissariat: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    items = await AdhesionRepository(db).list_admin_export_rows(
        status=status,
        commissariat=commissariat,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )

    def _iter():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "nom",
                "prenom",
                "email",
                "tel_mobile",
                "cni",
                "region_domicile_nom",
                "departement_domicile_nom",
                "commune_domicile_nom",
                "region_militantisme_nom",
                "departement_militantisme_nom",
                "commune_militantisme_nom",
                "mode_paiement",
                "montant_adhesion",
                "paiement_confirme",
                "reference_paiement",
                "commissariat",
                "commissariat_scientifique_principal",
                "commissariat_scientifique_secondaire",
                "statut",
                "created_at",
            ]
        )
        yield "\ufeff" + buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for x in items:
            writer.writerow(
                [
                    str(x["id"]),
                    x["nom"],
                    x["prenom"],
                    x["email"],
                    x["tel_mobile"],
                    x["cni"],
                    x["region_domicile_nom"],
                    x["departement_domicile_nom"],
                    x["commune_domicile_nom"],
                    x["region_militantisme_nom"],
                    x["departement_militantisme_nom"],
                    x["commune_militantisme_nom"],
                    x["mode_paiement"].value if hasattr(x["mode_paiement"], "value") else str(x["mode_paiement"]),
                    x["montant_adhesion"],
                    x["paiement_confirme"],
                    x["reference_paiement"],
                    x["commissariat"],
                    x["commissariat_scientifique_principal"],
                    x["commissariat_scientifique_secondaire"],
                    x["statut"].value if hasattr(x["statut"], "value") else str(x["statut"]),
                    x["created_at"].isoformat() if x["created_at"] else "",
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    headers = {"Content-Disposition": 'attachment; filename="adhesions.csv"'}
    return StreamingResponse(_iter(), media_type="text/csv; charset=utf-8", headers=headers)


@read_router.get(
    "/adhesions/export.xlsx",
    summary="Exporter les adhésions en Excel",
    description="Génère un fichier Excel (.xlsx) contenant les données des adhésions filtrées, avec un encodage correct pour les caractères spéciaux.",
)
async def export_xlsx(
    status: AdhesionStatus | None = None,
    commissariat: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        from openpyxl import Workbook
    except ModuleNotFoundError:
        raise HTTPException(status_code=500, detail="Dépendance manquante: openpyxl")

    items = await AdhesionRepository(db).list_admin_export_rows(
        status=status,
        commissariat=commissariat,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("adhesions")
    ws.append(
        [
            "id",
            "nom",
            "prenom",
            "email",
            "tel_mobile",
            "cni",
            "region_domicile_nom",
            "departement_domicile_nom",
            "commune_domicile_nom",
            "region_militantisme_nom",
            "departement_militantisme_nom",
            "commune_militantisme_nom",
            "mode_paiement",
            "montant_adhesion",
            "paiement_confirme",
            "reference_paiement",
            "commissariat",
            "commissariat_scientifique_principal",
            "commissariat_scientifique_secondaire",
            "statut",
            "created_at",
        ]
    )

    for x in items:
        mode = x["mode_paiement"].value if hasattr(x["mode_paiement"], "value") else str(x["mode_paiement"])
        statut = x["statut"].value if hasattr(x["statut"], "value") else str(x["statut"])
        created_at = x["created_at"].isoformat() if x["created_at"] else ""
        ws.append(
            [
                str(x["id"]),
                x["nom"],
                x["prenom"],
                x["email"],
                x["tel_mobile"],
                x["cni"],
                x["region_domicile_nom"],
                x["departement_domicile_nom"],
                x["commune_domicile_nom"],
                x["region_militantisme_nom"],
                x["departement_militantisme_nom"],
                x["commune_militantisme_nom"],
                mode,
                x["montant_adhesion"],
                x["paiement_confirme"],
                x["reference_paiement"],
                x["commissariat"],
                x["commissariat_scientifique_principal"],
                x["commissariat_scientifique_secondaire"],
                statut,
                created_at,
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    headers = {"Content-Disposition": 'attachment; filename="adhesions.xlsx"'}
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


# ===================================================================
#  RADIATIONS AUTOMATIQUES / MANUELLES
# ===================================================================


@read_router.get(
    "/radiations/candidats",
    response_model=RadiationCandidatesResponse,
    summary="Lister les membres éligibles à la radiation (3+ mois impayés)",
    description=(
        "[DEMANDE EXPLICITE USER] Retourne la liste des adhésions validées avec N mois impayés "
        "consécutifs EN PARTANT du mois présent (pas un streak ancien). "
        "Exclut automatiquement les rôles privilégiés (Admin, CA, CD, CC, CR, Modérateur). "
        "Exclut les nouvelles recrues avec moins de N+1 cotisations générées. "
        "Utilisable en fallback manuel si le CRON / CLI ne fonctionne pas."
    ),
)
async def list_radiation_candidates(
    delai_mois: int | None = None,
    include_privileges: bool = False,
    limit: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    service = RadiationService(db)
    candidats = await service.list_candidates(
        exclude_privileged_roles=not include_privileges,
        delai_mois=delai_mois,
        limit=max(0, limit) if limit else None,
    )
    out_items: list[RadiationCandidateOut] = []
    for c in candidats:
        out_items.append(
            RadiationCandidateOut(
                adhesionId=c.adhesion_id,
                adhesionNom=c.adhesion_nom,
                adhesionPrenom=c.adhesion_prenom,
                email=c.email,
                telMobile=c.tel_mobile,
                userId=c.user_id,
                streakMoisImpayes=c.streak_mois_impayes,
                premierMoisImpaye=c.premier_mois_impaye,
                dernierMoisImpaye=c.dernier_mois_impaye,
                moisConcernes=[
                    {"annee": m.annee, "mois": m.mois, "statut": m.statut}
                    for m in c.mois_concernes
                ],
            )
        )
    as_of = datetime.utcnow().isoformat()
    return {
        "data": out_items,
        "meta": {
            "total": len(out_items),
            "delaiMois": (
                delai_mois
                if delai_mois is not None
                else settings.radiation_delai_mois_impayes_consecutifs
            ),
            "automatiqueEnabled": settings.radiation_automatique_enabled,
            "excludePrivilegedRoles": not include_privileges,
            "asOf": as_of,
        },
    }


@write_router.post(
    "/radiations/apply-massive",
    response_model=ApplyMassiveRadiationResponse,
    summary="Appliquer radiation massive sur les candidats ou une liste d'ids",
    description=(
        "Applique la radiation pour (A) tous les candidats détectés auto OU "
        "(B) les adhesionIds fournis (doivent être candidats ou erreur). "
        "Radiation atomique (adhesion.statut=radiee + user.is_active=false + timestamps + motif). "
        "Envoie un email de notification si MAIL_ENABLED=true (best-effort)."
    ),
)
async def apply_massive_radiation(
    payload: ApplyMassiveRadiationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    settings = get_settings()
    service = RadiationService(db)
    candidats = await service.list_candidates()
    candidats_by_id: dict[uuid.UUID, object] = {c.adhesion_id: c for c in candidats}

    ids_requetes = list(payload.adhesion_ids) if payload.adhesion_ids else None
    if ids_requetes:
        # Vérifier que tous les ids fournis sont BIEN dans la liste candidats (ou refuser silencieusement ? Non: erreur explicite)
        cibles: list[tuple[uuid.UUID, object | None]] = []
        for rid in ids_requetes:
            if rid not in candidats_by_id:
                # Autoriser l'admin à radier même non candidat (car demande manuelle, ex: pour test) ?
                # On accepte, et on génère un motif "hors critères auto"
                cibles.append((rid, None))
            else:
                cibles.append((rid, candidats_by_id[rid]))
    else:
        cibles = [(cid, candidats_by_id[cid]) for cid in candidats_by_id]

    resultats: list[RadiationResultItem] = []
    total_ok = 0
    total_err = 0

    from datetime import datetime as _dt_now

    for adhesion_id, c_obj in cibles:
        # Générer motif
        motif_final = payload.motif_override.strip() if payload.motif_override and payload.motif_override.strip() else ""
        streak = getattr(c_obj, "streak_mois_impayes", None) if c_obj is not None else None
        if not motif_final:
            if streak is not None:
                motif_final = (
                    f"Radiation automatique — {streak} mois impayés consécutifs."
                )
            else:
                motif_final = (
                    "Radiation administrative massive (hors critères auto)."
                )

        try:
            adhesion, user_after = await service.apply_radiation(
                adhesion_id=adhesion_id,
                reason_code=DisabledReason.MANUEL_ADMIN
                if c_obj is None
                else DisabledReason.AUTOMATIQUE_3_MOIS,
                motif=motif_final,
                radie_par_user_id=principal.user_id,
            )
            await db.commit()

            # Relecture pour relations après commit (si besoin email)
            adhesion_fresh = await AdhesionRepository(db).get_by_id(adhesion.id)
            email_to = None
            if adhesion_fresh is not None:
                # Récupérer user après commit
                user_fresh = None
                if getattr(adhesion_fresh, "user_account", None) is not None:
                    user_fresh = adhesion_fresh.user_account
                email_to = resolve_recipient_email(
                    adhesion=adhesion_fresh, user=user_fresh
                )
                mois_labels = [
                    (m.annee, m.mois)
                    for m in (getattr(c_obj, "mois_concernes", []) if c_obj is not None else [])
                ]
                if settings.mail_enabled and email_to:
                    subj, text, html = build_radiation_notification(
                        adhesion=adhesion_fresh,
                        user=user_fresh,
                        motif=motif_final,
                        reason_code=DisabledReason.AUTOMATIQUE_3_MOIS if c_obj is not None else DisabledReason.MANUEL_ADMIN,
                        mois_concernes=mois_labels,
                        base_url=settings.public_base_url,
                    )
                    background_tasks.add_task(
                        send_email_best_effort,
                        to=email_to,
                        subject=subj,
                        text=text,
                        html=html,
                        settings=settings,
                    )

            resultats.append(
                RadiationResultItem(
                    adhesionId=adhesion.id,
                    adhesionNom=adhesion.nom,
                    adhesionPrenom=adhesion.prenom,
                    statut="radié",
                    erreur=None,
                )
            )
            total_ok += 1
        except HTTPException as e:
            # adhesion introuvable / déjà radiée ...
            nom_err = getattr(c_obj, "adhesion_nom", "") if c_obj is not None else ""
            pre_err = getattr(c_obj, "adhesion_prenom", "") if c_obj is not None else ""
            resultats.append(
                RadiationResultItem(
                    adhesionId=adhesion_id,
                    adhesionNom=nom_err,
                    adhesionPrenom=pre_err,
                    statut="erreur",
                    erreur=str(e.detail),
                )
            )
            total_err += 1
        except Exception as e:  # noqa: BLE001 - on ne veut jamais faire échouer le lot
            nom_err = getattr(c_obj, "adhesion_nom", "") if c_obj is not None else ""
            pre_err = getattr(c_obj, "adhesion_prenom", "") if c_obj is not None else ""
            resultats.append(
                RadiationResultItem(
                    adhesionId=adhesion_id,
                    adhesionNom=nom_err,
                    adhesionPrenom=pre_err,
                    statut="erreur",
                    erreur=str(e),
                )
            )
            total_err += 1

    return {
        "data": resultats,
        "meta": {
            "total": len(resultats),
            "radiés": total_ok,
            "erreurs": total_err,
            "dryRun": False,
            "radiéParUserId": str(principal.user_id),
            "effectuéÀ": _dt_now.utcnow().isoformat(),
        },
    }


@write_router.post(
    "/adhesions/{adhesion_id}/radier",
    response_model=AdhesionDetailResponse,
    summary="Radier manuellement une adhésion + désactiver compte membre",
    description=(
        "Action ADMIN manuelle : raison=manuel_admin, radie_par_user_id = admin courant, "
        "motif OBLIGATOIRE (min 10 caractères). Envoie un email si MAIL_ENABLED=true."
    ),
)
async def radier_manuel_adhesion(
    adhesion_id: uuid.UUID,
    payload: RadierManuelRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    settings = get_settings()
    service = RadiationService(db)
    motif_clean = payload.motif.strip()
    adhesion, user_after = await service.apply_radiation(
        adhesion_id=adhesion_id,
        reason_code=DisabledReason.MANUEL_ADMIN,
        motif=motif_clean,
        radie_par_user_id=principal.user_id,
    )
    await db.commit()
    adhesion_fresh = await AdhesionRepository(db).get_by_id(adhesion.id)
    if adhesion_fresh is not None and settings.mail_enabled:
        user_fresh = getattr(adhesion_fresh, "user_account", None)
        email_to = resolve_recipient_email(adhesion=adhesion_fresh, user=user_fresh)
        if email_to:
            subj, text, html = build_radiation_notification(
                adhesion=adhesion_fresh,
                user=user_fresh,
                motif=motif_clean,
                reason_code=DisabledReason.MANUEL_ADMIN,
                mois_concernes=[],
                base_url=settings.public_base_url,
            )
            background_tasks.add_task(
                send_email_best_effort,
                to=email_to,
                subject=subj,
                text=text,
                html=html,
                settings=settings,
            )
    if adhesion_fresh is None:
        raise HTTPException(status_code=404, detail="Adhésion introuvable après radiation")
    return {"data": adhesion_fresh}


@write_router.post(
    "/adhesions/{adhesion_id}/rehabiliter",
    response_model=AdhesionDetailResponse,
    summary="Réhabiliter une adhésion radiée + réactiver compte membre",
    description=(
        "Action ADMIN 100% MANUELLE. Remet adhesion.statut=validee, user.is_active=true, "
        "efface les timestamps (conserve motif historique avec préfixe [REHABILITE]). "
        "N'exige AUCUN paiement rétro : l'administration décide souverainement. "
        "Envoie un email si MAIL_ENABLED=true."
    ),
)
async def rehabiliter_adhesion(
    adhesion_id: uuid.UUID,
    payload: RehabiliterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    settings = get_settings()
    service = RadiationService(db)
    motif_clean = payload.motif.strip()
    adhesion, user_after = await service.apply_reactivation(
        adhesion_id=adhesion_id,
        motif=motif_clean,
        reactiv_par_user_id=principal.user_id,
    )
    await db.commit()
    adhesion_fresh = await AdhesionRepository(db).get_by_id(adhesion.id)
    if adhesion_fresh is not None and settings.mail_enabled:
        user_fresh = getattr(adhesion_fresh, "user_account", None)
        email_to = resolve_recipient_email(adhesion=adhesion_fresh, user=user_fresh)
        if email_to:
            subj, text, html = build_reactivation_notification(
                adhesion=adhesion_fresh,
                user=user_fresh,
                motif_reactivation=motif_clean,
                base_url=settings.public_base_url,
            )
            background_tasks.add_task(
                send_email_best_effort,
                to=email_to,
                subject=subj,
                text=text,
                html=html,
                settings=settings,
            )
    if adhesion_fresh is None:
        raise HTTPException(status_code=404, detail="Adhésion introuvable après réhabilitation")
    return {"data": adhesion_fresh}

