from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.core.errors import install_exception_handlers
from app.core.middleware import RequestIdMiddleware, TimingMiddleware
from app.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.api_title)

    install_exception_handlers(app)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(TimingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(x) for x in settings.cors_allow_origins],
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount(settings.public_files_path, StaticFiles(directory=settings.storage_dir, check_dir=False), name="files")
    app.include_router(api_v1_router, prefix="/api/v1")
    return app


app = create_app()
