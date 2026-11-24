from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependecies import get_current_user
from app.db.db import get_db
from app.db.schema import Credentials
from app.schemas.common import Page, PageParams, make_page

router = APIRouter(prefix="/admin", tags=["Admin"])


async def require_admin(current_user=Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return current_user


class AccountOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    email_verified: bool
    is_admin: bool
    is_banned: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminUpdate(BaseModel):
    is_admin: bool


@router.get("/accounts", response_model=Page[AccountOut])
async def list_accounts(
    params: PageParams = Depends(),
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total = (
        await db.execute(select(func.count()).select_from(Credentials))
    ).scalar_one()
    rows = await db.execute(
        select(Credentials)
        .order_by(Credentials.created_at, Credentials.id)
        .limit(params.per_page)
        .offset(params.offset)
    )
    return make_page(list(rows.scalars().all()), params, total)


@router.patch("/accounts/{account_id}", response_model=AccountOut)
async def set_admin(
    account_id: str,
    body: AdminUpdate,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if account_id == str(admin.id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You can't change your own admin access"
        )
    account = (
        await db.execute(select(Credentials).where(Credentials.id == account_id))
    ).scalar_one_or_none()
    if not account:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    account.is_admin = body.is_admin
    await db.commit()
    await db.refresh(account)
    return account
