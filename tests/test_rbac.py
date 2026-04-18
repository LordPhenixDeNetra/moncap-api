from __future__ import annotations

from app.core.security import hash_password, normalize_email
from app.repositories.users import UserRepository


async def test_admin_routes_forbidden_without_admin_role(client, db_session):
    repo = UserRepository(db_session)
    await repo.create_user(email=normalize_email("user@test.com"), password_hash=hash_password("Password123!"))
    await db_session.commit()

    r = await client.post("/api/v1/auth/login", json={"email": "user@test.com", "password": "Password123!"})
    assert r.status_code == 200
    token = r.json()["data"]["accessToken"]

    r2 = await client.get("/api/v1/admin/adhesions", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 403

