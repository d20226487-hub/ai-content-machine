"""Bootstrap an initial admin user.

Idempotent: re-running won't duplicate or overwrite anything. To rotate the
admin password, change BOOTSTRAP_ADMIN_PASSWORD in .env and re-run with
BOOTSTRAP_ADMIN_RESET_PASSWORD=true.

Usage:
    docker compose exec api python -m app.seed
"""
import asyncio
import os
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import Role, User
from app.db.session import SessionLocal


async def main() -> None:
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    full_name = os.getenv("BOOTSTRAP_ADMIN_NAME", "Admin")
    reset = os.getenv("BOOTSTRAP_ADMIN_RESET_PASSWORD", "false").lower() == "true"

    if not email or not password:
        print(
            "ERROR: BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD must be set in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    async with SessionLocal() as db:
        admin_role = (
            await db.execute(select(Role).where(Role.name == "admin"))
        ).scalar_one_or_none()
        if admin_role is None:
            print(
                "ERROR: 'admin' role not found. Run 'alembic upgrade head' first.",
                file=sys.stderr,
            )
            sys.exit(1)

        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        if existing is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                is_active=True,
                role_id=admin_role.id,
            )
            db.add(user)
            await db.commit()
            print(f"Created admin user: {email}")
        elif reset:
            existing.password_hash = hash_password(password)
            existing.is_active = True
            await db.commit()
            print(f"Reset password for: {email}")
        else:
            print(
                f"Admin user already exists: {email} "
                "(set BOOTSTRAP_ADMIN_RESET_PASSWORD=true to rotate)"
            )


if __name__ == "__main__":
    asyncio.run(main())
