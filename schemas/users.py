from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InvestorSummary(BaseModel):
    id: str
    name: str | None
    email: str | None
    pan: str | None
    phone_no: int | None
    statement_from: datetime | None
    statement_to: datetime | None
    holdings_count: int
    total_cost: float
    market_value: float


class HoldingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    amc_name: str | None
    folio_no: str | None
    scheme_name: str | None
    scheme_type: str | None
    scheme_category: str | None
    sub_scheme_category: str | None
    isin: str | None
    nav_date: datetime | None
    nav_inr: float | None
    closing_units: float | None
    total_cost: float | None
    market_value: float | None


class TransactionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    scheme_id: str
    date: datetime | None
    description: str | None
    amount_inr: float | None
    units: float | None
    nav: float | None
    type: str | None


class InvestorDetail(InvestorSummary):
    address: str | None
    holdings: list[HoldingItem]
    transactions: list[TransactionItem]
