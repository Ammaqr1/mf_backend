from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schema import (
    Document,
    MutualFundHolding,
    MutualFundTransaction,
    User,
)


async def get_or_create_user(
    db: AsyncSession,
    credential_id: str,
    pan: str | None,
    profile: dict,
) -> User:
    """One user per (account, PAN). Folios without a PAN fall back to name."""
    stmt = select(User).where(User.credentials_id == credential_id)
    if pan:
        stmt = stmt.where(User.pan == pan)
    else:
        stmt = stmt.where(User.pan.is_(None), User.name == profile.get("name"))
    user = (await db.execute(stmt)).scalars().first()

    if user is None:
        user = User(credentials_id=credential_id, pan=pan)
        db.add(user)

    # refresh profile with the latest statement; keep old values if absent
    for field, value in profile.items():
        if value is not None:
            setattr(user, field, value)
    user.deleted_at = None
    await db.flush()
    return user


async def upsert_holding(
    db: AsyncSession,
    user_id: str,
    folio_no: str,
    isin: str | None,
    scheme_name: str,
    values: dict,
) -> MutualFundHolding:
    stmt = select(MutualFundHolding).where(
        MutualFundHolding.user_id == user_id,
        MutualFundHolding.folio_no == folio_no,
    )
    if isin:
        stmt = stmt.where(MutualFundHolding.isin == isin)
    else:  # no ISIN to key on; fall back to the scheme name
        stmt = stmt.where(
            MutualFundHolding.isin.is_(None),
            MutualFundHolding.scheme_name == scheme_name,
        )
    holding = (await db.execute(stmt)).scalars().first()

    if holding is None:
        holding = MutualFundHolding(
            user_id=user_id, folio_no=folio_no, isin=isin, scheme_name=scheme_name
        )
        db.add(holding)

    for field, value in values.items():
        setattr(holding, field, value)

        
    await db.flush()
    return holding


def _txn_key(date, description, amount, units, balance):
    return (date, description, amount, units, balance)


async def add_new_transactions(
    db: AsyncSession, holding_id: str, rows: list[dict]
) -> int:
    """Insert only transactions not already stored (statements overlap)."""
    existing = (
        await db.execute(
            select(
                MutualFundTransaction.date,
                MutualFundTransaction.description,
                MutualFundTransaction.amount_inr,
                MutualFundTransaction.units,
                MutualFundTransaction.balance,
            ).where(MutualFundTransaction.scheme_id == holding_id)
        )
    ).all()
    seen = {_txn_key(*row) for row in existing}

    added = 0
    for row in rows:
        key = _txn_key(
            row["date"], row["description"], row["amount_inr"], row["units"], row["balance"]
        )
        if key in seen:
            continue
        seen.add(key)
        db.add(MutualFundTransaction(scheme_id=holding_id, **row))
        added += 1
    await db.flush()
    return added


def mark_processing(document: Document) -> None:
    document.status = "processing"
    document.error_message = None


def mark_processed(
    document: Document, start: datetime | None, end: datetime | None
) -> None:
    document.status = "processed"
    document.statement_from = start
    document.statement_to = end
    document.processed_at = datetime.now()
    document.error_message = None


def mark_failed(document: Document, message: str) -> None:
    document.status = "failed"
    document.error_message = message[:500]
