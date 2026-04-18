from __future__ import annotations

import argparse
import asyncio

from app.core.security import hash_password, normalize_email
from app.db.session import get_sessionmaker
from app.models.enums import AppRole
from app.repositories.users import UserRepository


async def _run(email: str, password: str) -> None:
    async with get_sessionmaker()() as session:
        repo = UserRepository(session)
        norm_email = normalize_email(email)
        existing = await repo.get_by_email(norm_email)
        if existing:
            return
        user = await repo.create_user(email=norm_email, password_hash=hash_password(password))
        await repo.add_role(user_id=user.id, role=AppRole.admin)
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    asyncio.run(_run(email=args.email, password=args.password))


if __name__ == "__main__":
    main()
