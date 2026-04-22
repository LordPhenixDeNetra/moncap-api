from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def app(tmp_path) -> AsyncGenerator:
    os.environ["ENV"] = "test"
    os.environ["JWT_SECRET"] = "x" * 40
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    os.environ["REFRESH_COOKIE_SECURE"] = "false"
    os.environ["MAIL_ENABLED"] = "false"

    from app.core.settings import get_settings
    from app.db.session import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()

    import app.models
    from app.db.base import Base
    from app.main import create_app

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()
    yield application

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_session(app) -> AsyncGenerator:
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        yield session
        await session.rollback()
