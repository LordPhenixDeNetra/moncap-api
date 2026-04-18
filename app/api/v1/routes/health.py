from fastapi import APIRouter

router = APIRouter()


@router.get(
    "/health",
    summary="Vérification de l'état de l'API",
    description="Retourne un statut 'ok' si l'API est fonctionnelle. Utile pour le monitoring.",
)
async def health():
    return {"data": {"status": "ok"}}

