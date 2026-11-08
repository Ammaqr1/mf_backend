from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schema import Credentials


async def get_credential_by_email(
    db: AsyncSession,
    email: str,
) -> Credentials | None:

    stmt = select(Credentials).where(
        Credentials.email == email.strip().lower()
    )

    result = await db.execute(stmt)

    return result.scalar_one_or_none()


async def create_credential(
    db: AsyncSession,
    name: str,
    email: str,
    password_hash: str,
) -> Credentials:

    credential = Credentials(
        name=name,
        email=email.strip().lower(),
        password=password_hash,
        is_admin=False,
    )

    db.add(credential)

    await db.flush()
    await db.refresh(credential)

    return credential


async def get_credential_by_id(
    db: AsyncSession,
    credential_id: str,
) -> Credentials | None:
    stmt = select(Credentials).where(
        Credentials.id == credential_id
    )

    result = await db.execute(stmt)

    return result.scalar_one_or_none()