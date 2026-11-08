from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Text,
    BigInteger,
    Float,
    Boolean,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from cuid2 import Cuid


class Base(DeclarativeBase):
    pass


CUID_LEN = 32



_CUID = Cuid(length=24)


def generate_cuid() -> str:
    return _CUID.generate()



# software account credentials
class Credentials(Base):
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(
        String(CUID_LEN), primary_key=True, default=generate_cuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # store a password hash here, never the plain password
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    is_banned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    users: Mapped[list["User"]] = relationship(back_populates="credential")

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="credential",
        cascade="all, delete-orphan",
    )

class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(
        String(CUID_LEN), primary_key=True, default=generate_cuid
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=False, index=True
    )
    phone_no: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address: Mapped[str | None] = mapped_column(
        String(455), nullable=True, unique=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    statement_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    statement_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

    credentials_id: Mapped[str | None] = mapped_column(
        String(CUID_LEN), ForeignKey("credentials.id"), nullable=True
    )
    credential: Mapped["Credentials | None"] = relationship(back_populates="users")
    holdings: Mapped[list["MutualFundHolding"]] = relationship(
        back_populates="user"
    )


class MutualFundHolding(Base):
    __tablename__ = "mutual_fund_holdings"
    __table_args__ = (
        UniqueConstraint("user_id", "folio_no", "isin", name="uq_holding_user_folio_isin"),
    )

    id: Mapped[str] = mapped_column(
        String(CUID_LEN), primary_key=True, default=generate_cuid
    )
    user_id: Mapped[str] = mapped_column(
        String(CUID_LEN), ForeignKey("user.id"), nullable=False, index=True
    )

    amc_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    folio_no: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    holder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    scheme_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scheme_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scheme_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sub_scheme_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheme_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    nav_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    nav_inr: Mapped[float | None] = mapped_column(Float, nullable=True)

    isin: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)

    closing_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_value_inr: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    user: Mapped["User"] = relationship(back_populates="holdings")

    transactions: Mapped[list["MutualFundTransaction"]] = relationship(
        back_populates="holding"
    )

class MutualFundTransaction(Base):
    __tablename__ = "mutual_fund_transactions"

    transaction_id: Mapped[str] = mapped_column(
        String(CUID_LEN), primary_key=True, default=generate_cuid
    )
    scheme_id: Mapped[str] = mapped_column(
        String(CUID_LEN),
        ForeignKey("mutual_fund_holdings.id"),
        nullable=False,
        index=True,
    )

    date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    units: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_balance: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    holding: Mapped["MutualFundHolding"] = relationship(back_populates="transactions")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(
        String(CUID_LEN),
        primary_key=True,
        default=generate_cuid,
    )

    credential_id: Mapped[str] = mapped_column(
        String(CUID_LEN),
        ForeignKey("credentials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    token_family_id: Mapped[str] = mapped_column(
        String(CUID_LEN),
        nullable=False,
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    replaced_by_token_id: Mapped[str | None] = mapped_column(
        String(CUID_LEN),
        ForeignKey("refresh_tokens.id"),
        nullable=True,
        )
        
    credential: Mapped["Credentials"] = relationship(
        back_populates="refresh_tokens",
    )
