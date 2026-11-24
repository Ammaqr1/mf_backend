from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependecies import get_current_user
from app.db.db import get_db
from app.db.schema import MutualFundHolding, MutualFundTransaction, User
from app.schemas.common import Page, PageParams, make_page
from app.schemas.users import InvestorDetail, InvestorSummary

router = APIRouter(prefix="/users", tags=["Users"])


def _summary(user: User, count: int, cost: float, value: float) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "pan": user.pan,
        "phone_no": user.phone_no,
        "statement_from": user.statement_from,
        "statement_to": user.statement_to,
        "holdings_count": count,
        "total_cost": cost,
        "market_value": value,
    }


@router.get("", response_model=Page[InvestorSummary])
async def list_investors(
    params: PageParams = Depends(),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # admins see every investor; everyone else only their own
    conds = [User.deleted_at.is_(None)]
    if not current_user.is_admin:
        conds.append(User.credentials_id == str(current_user.id))

    total = (
        await db.execute(select(func.count()).select_from(User).where(*conds))
    ).scalar_one()

    stmt = (
        select(
            User,
            func.count(MutualFundHolding.id),
            func.coalesce(func.sum(MutualFundHolding.total_cost), 0.0),
            func.coalesce(func.sum(MutualFundHolding.market_value), 0.0),
        )
        .outerjoin(MutualFundHolding, MutualFundHolding.user_id == User.id)
        .where(*conds)
        .group_by(User.id)
        .order_by(User.name, User.id)
        .limit(params.per_page)
        .offset(params.offset)
    )
    rows = (await db.execute(stmt)).all()
    items = [_summary(u, int(c), float(cost), float(val)) for u, c, cost, val in rows]
    return make_page(items, params, total)


@router.get("/{user_id}", response_model=InvestorDetail)
async def get_investor(
    user_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conds = [User.id == user_id, User.deleted_at.is_(None)]
    if not current_user.is_admin:
        conds.append(User.credentials_id == str(current_user.id))
    user = (await db.execute(select(User).where(*conds))).scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investor not found")

    holdings = (
        (
            await db.execute(
                select(MutualFundHolding)
                .where(MutualFundHolding.user_id == user.id)
                .order_by(MutualFundHolding.market_value.desc().nulls_last())
            )
        )
        .scalars()
        .all()
    )
    ids = [h.id for h in holdings]
    transactions = []
    if ids:
        transactions = (
            (
                await db.execute(
                    select(MutualFundTransaction)
                    .where(MutualFundTransaction.scheme_id.in_(ids))
                    .order_by(MutualFundTransaction.date)
                )
            )
            .scalars()
            .all()
        )

    cost = sum(h.total_cost or 0 for h in holdings)
    value = sum(h.market_value or 0 for h in holdings)
    return {
        **_summary(user, len(holdings), cost, value),
        "address": user.address,
        "holdings": holdings,
        "transactions": transactions,
    }
