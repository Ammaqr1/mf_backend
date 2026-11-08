from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schema import RefreshToken


async def create_refresh_token(
    db: AsyncSession,
    credential_id: str,
    token_hash: str,
    token_family_id: str,
    expires_at: datetime,
) -> RefreshToken:

    refresh_token = RefreshToken(
        credential_id=credential_id,
        token_hash=token_hash,
        token_family_id=token_family_id,
        expires_at=expires_at,
    )

    db.add(refresh_token)
    await db.flush()

    return refresh_token


async def get_refresh_token(
    db: AsyncSession,
    token_hash: str,
) -> RefreshToken | None:

    stmt = select(RefreshToken).where(
        RefreshToken.token_hash == token_hash
    )

    result = await db.execute(stmt)

    return result.scalar_one_or_none()


async def revoke_refresh_token(
    db: AsyncSession,
    refresh_token: RefreshToken,
) -> None:

    refresh_token.revoked_at = datetime.now(timezone.utc)

    await db.flush()


async def revoke_token_family(
    db: AsyncSession,
    token_family_id: str,
) -> None:

    stmt = select(RefreshToken).where(
        RefreshToken.token_family_id == token_family_id,
        RefreshToken.revoked_at.is_(None),
    )

    result = await db.execute(stmt)

    tokens = result.scalars().all()

    now = datetime.now(timezone.utc)

    for token in tokens:
        token.revoked_at = now

    await db.flush()

async def get_refresh_token_for_update(
    db: AsyncSession,
    token_hash: str,
) -> RefreshToken | None:

    stmt = (
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )

    result = await db.execute(stmt)

    return result.scalar_one_or_none()