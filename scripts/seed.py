"""
Seed script — creates default tenant and admin user if they don't exist.
Run: python -m scripts.seed
"""

import asyncio
import sys
import os

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import async_session_factory
from sqlalchemy import select

# Import ALL models to register them with SQLAlchemy metadata
import app.tenants.models  # noqa: F401
import app.users.models  # noqa: F401
import app.turfs.models  # noqa: F401
import app.bookings.models  # noqa: F401
import app.teams.models  # noqa: F401
import app.tournaments.models  # noqa: F401
import app.payments.models  # noqa: F401
import app.coupons.models  # noqa: F401

from app.tenants.models import Tenant
from app.users.models import User


async def seed():
    async with async_session_factory() as session:
        # Check if default tenant exists
        result = await session.execute(
            select(Tenant).where(Tenant.slug == "default")
        )
        tenant = result.scalar_one_or_none()

        if tenant:
            print(f"Tenant already exists: {tenant.name} (id={tenant.id})")
            return

        # Create default tenant
        tenant = Tenant(
            name="Signal Shift Arena",
            slug="default",
            config={"timezone": "Asia/Kolkata", "contact_email": "admin@signalshift.in"},
            is_active=True,
        )
        session.add(tenant)
        await session.flush()
        print(f"Created tenant: {tenant.name} (id={tenant.id})")

        # Create default admin user
        admin = User(
            tenant_id=tenant.id,
            email="admin@signalshift.in",
            full_name="Admin",
            role="super_admin",
            is_active=True,
        )
        session.add(admin)
        await session.flush()
        print(f"Created admin user: {admin.email} (id={admin.id})")

        await session.commit()
        print("Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
