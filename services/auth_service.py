from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from datetime import datetime , timezone

from  app.db.queries.credentials import (
    get_credential_by_email,
    create_credential,
    get_credential_by_id
)
from app.db.queries.refresh_token import create_refresh_token, get_refresh_token_for_update, revoke_token_family, get_refresh_token, revoke_refresh_token

from app.core.security import hash_password, verify_password, generate_refresh_token, hash_refresh_token, get_refresh_token_expiry, cuid_generator


async def signup(
    db: AsyncSession,
    name: str,
    email: str,
    password: str,
):
    email = email.strip().lower()

    # 1. Check whether email already exists
    existing_credential = await get_credential_by_email(
        db,
        email,
    )

    print("existing credentials")

    if existing_credential:
        raise ValueError("Email already registered")

    # 2. Hash password
    password_hash = hash_password(password)

    print("the password hash is ",password_hash)

    try:
        # 3. Create credential
        credential = await create_credential(
            db=db,
            name=name,
            email=email,
            password_hash=password_hash,
        )


        # 4. Commit transaction
        await db.commit()

        # 5. Refresh object
        await db.refresh(credential)

        print("the credentail",credential)
        return credential

    except IntegrityError:
        await db.rollback()
        raise ValueError("Email already registered")

    except Exception:
        await db.rollback()
        raise



async def login(
    db: AsyncSession,
    email: str,
    password: str,
):
    email = email.strip().lower()

    credential = await get_credential_by_email(db, email)

    # Generic failure for unknown email or incorrect password
    if not credential:
        return None

    if not verify_password(password, credential.password):
        return None

    # Reject banned accounts
    if credential.is_banned:
        return None
    # Generate a new refresh token
    try:
        # Generate a new refresh token
        raw_refresh_token = generate_refresh_token()

        token_hash = hash_refresh_token(raw_refresh_token)

        token_family_id = cuid_generator()

        expires_at = get_refresh_token_expiry()

        await create_refresh_token(
            db=db,
            credential_id=credential.id,
            token_hash=token_hash,
            token_family_id=token_family_id,
            expires_at=expires_at,
        )

        await db.commit()
        await db.refresh(credential)

        return credential, raw_refresh_token

    except Exception:
        await db.rollback()
        raise


async def refresh_session(
    db: AsyncSession,
    raw_refresh_token: str,
):
    token_hash = hash_refresh_token(raw_refresh_token)

    try:
        old_token = await get_refresh_token_for_update(
            db=db,
            token_hash=token_hash,
        )

        if not old_token:
            return None

        # Detect reuse of an already revoked token
        if old_token.revoked_at is not None:
            await revoke_token_family(
                db=db,
                token_family_id=old_token.token_family_id,
            )
            await db.commit()
            return None

        now = datetime.now(timezone.utc)

        # Check expiration
        if old_token.expires_at <= now:
            old_token.revoked_at = now
            await db.commit()
            return None

        credential = await get_credential_by_id(
            db=db,
            credential_id=old_token.credential_id,
        )

        if not credential or credential.is_banned:
            await revoke_token_family(
                db=db,
                token_family_id=old_token.token_family_id,
            )
            await db.commit()
            return None

        # Generate replacement token
        new_raw_token = generate_refresh_token()

        new_token = await create_refresh_token(
            db=db,
            credential_id=credential.id,
            token_hash=hash_refresh_token(new_raw_token),
            token_family_id=old_token.token_family_id,
            expires_at=get_refresh_token_expiry(),
        )

        # Revoke the old token
        old_token.revoked_at = now
        old_token.replaced_by_token_id = new_token.id

        await db.commit()

        return credential, new_raw_token

    except Exception:
        await db.rollback()
        raise

async def logout(
    db: AsyncSession,
    raw_refresh_token: str | None,
) -> None:

    if not raw_refresh_token:
        return

    token_hash = hash_refresh_token(raw_refresh_token)

    try:
        refresh_token = await get_refresh_token(
            db=db,
            token_hash=token_hash,
        )

        if refresh_token and refresh_token.revoked_at is None:
            await revoke_refresh_token(
                db=db,
                refresh_token=refresh_token,
            )

        await db.commit()

    except Exception:
        await db.rollback()
        raise