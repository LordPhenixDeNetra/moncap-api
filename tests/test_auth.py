from __future__ import annotations

from app.core.security import hash_password, normalize_email
from app.models.enums import AppRole
from app.repositories.users import UserRepository


def _extract_cookie(set_cookie: str, name: str) -> str:
    parts = [p.strip() for p in set_cookie.split(";")]
    for p in parts:
        if p.startswith(f"{name}="):
            return p.split("=", 1)[1]
    raise AssertionError("cookie not found")


async def _seed_admin(db_session, *, email: str, password: str) -> None:
    repo = UserRepository(db_session)
    user = await repo.create_user(email=normalize_email(email), password_hash=hash_password(password))
    await repo.add_role(user_id=user.id, role=AppRole.admin)
    await db_session.commit()


async def test_login_refresh_rotation_and_reuse(client, db_session):
    await _seed_admin(db_session, email="admin@test.com", password="Password123!")

    r = await client.post("/api/v1/auth/login", json={"email": "admin@test.com", "password": "Password123!"})
    assert r.status_code == 200
    access1 = r.json()["data"]["accessToken"]
    set_cookie = r.headers.get("set-cookie")
    assert set_cookie
    refresh1 = _extract_cookie(set_cookie, "moncap_refresh")
    assert access1
    assert refresh1

    client.cookies.set("moncap_refresh", refresh1, path="/api/v1/auth")
    r2 = await client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200
    access2 = r2.json()["data"]["accessToken"]
    set_cookie2 = r2.headers.get("set-cookie")
    assert set_cookie2
    refresh2 = _extract_cookie(set_cookie2, "moncap_refresh")
    assert access2 and access2 != access1
    assert refresh2 and refresh2 != refresh1

    client.cookies.set("moncap_refresh", refresh1, path="/api/v1/auth")
    r3 = await client.post("/api/v1/auth/refresh")
    assert r3.status_code == 401

    client.cookies.set("moncap_refresh", refresh2, path="/api/v1/auth")
    r4 = await client.post("/api/v1/auth/refresh")
    assert r4.status_code == 401

