from contextlib import asynccontextmanager
import logging
import sys
import warnings

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.core.errors import install_exception_handlers
from app.core.middleware import RequestIdMiddleware, TimingMiddleware
from app.core.settings import get_settings


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.session import AsyncSessionLocal
    from app.services.paiements import ParametresPaiementService
    try:
        async with AsyncSessionLocal() as session:
            ps = ParametresPaiementService(session)
            await ps.seed_defaults_if_empty()
    except Exception:
        pass
    yield


def _construire_cors_origins(settings) -> list[str]:
    """Construit la liste CORS avec :
    1) Les valeurs explicites venant du .env
    2) Les localhost standards pour dev (5173 Vite, 3000 React/CRA, 8080 Vue)
    RÈGLE CRITIQUE CORS : JAMAIS '*' si allow_credentials=True (navigateur bloque)
    """
    origins: list[str] = []
    for raw in settings.cors_allow_origins or []:
        s = str(raw).strip().rstrip("/")
        if not s:
            continue
        if s == "*":
            warnings.warn(
                "CORS: allow_origins contient '*' mais allow_credentials=True est INCOMPATIBLE "
                "par spec W3C. On retire '*' pour éviter le blocage navigateur sur endpoints JWT. "
                "Remplacez '*' par le domaine exact dans CORS_ALLOW_ORIGINS du .env.",
                stacklevel=2,
            )
            print(
                "\n⚠️  [CORS WARNING] '*' n'est pas autorisé avec allow_credentials=True. "
                "Utilisez le domaine EXACT : https://moncap.innovamind.tech dans CORS_ALLOW_ORIGINS\n",
                file=sys.stderr,
            )
            continue
        origins.append(s)
    # Ajouts implicites safe (localhost dev local) : jamais conflit avec Bearer en prod
    dev_localhost = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ]
    for lh in dev_localhost:
        if lh not in origins:
            origins.append(lh)
    return origins


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.api_title, lifespan=lifespan)

    install_exception_handlers(app)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(TimingMiddleware)

    cors_origins = _construire_cors_origins(settings)
    logger.info("CORS allow_origins = %s", cors_origins)
    app.add_middleware(
        CORSMiddleware,
        # RÈGLE CORS OBLIGATOIRE : jamais "*" quand credentials=True → sinon le Bearer JWT
        # est bloqué par le navigateur sur les endpoints protégés /mon-compte/*
        allow_origins=cors_origins,
        allow_origin_regex=(
            r"^https?://(localhost|127\.0\.0\.1):(5173|3000|8080)(/\S*)?$"
        ),
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=[
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ],
        allow_headers=[
            "Authorization",          # CRITIQUE : Permet le Bearer JWT header
            "Content-Type",
            "Accept",
            "Origin",
            "X-Requested-With",
            "X-Request-ID",
            "X-CSRF-Token",
            "Cache-Control",
            "Pragma",
        ],
        expose_headers=[
            "Content-Disposition",    # Pour les téléchargements (rapport CSV...)
            "X-Total-Count",          # Pour la pagination (list admin)
            "X-Response-Time-MS",     # Timing middleware
            "X-Request-ID",           # Debug request ID
        ],
        max_age=3600,                 # Cache OPTIONS preflight 1h → moins d'appels navigateur
    )

    app.mount(settings.public_files_path, StaticFiles(directory=settings.storage_dir, check_dir=False), name="files")
    app.include_router(api_v1_router, prefix="/api/v1")
    return app


app = create_app()
