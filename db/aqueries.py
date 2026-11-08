from datetime import datetime
import re
import bcrypt
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession



from schema import Credentials, User, MutualFundHolding, MutualFundTransaction


# ---------- helpers ----------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def normalize_email(email: str) -> str:
    return email.strip().lower()


# Used so a login for an unknown email takes the same time as a wrong password
_DUMMY_HASH = hash_password("dummy-password")


# ---------- CREATE ----------

async def create_credential(
    db: AsyncSession, name: str, email: str, password: str, is_admin: bool = False
) -> Credentials:
    cred = Credentials(
        name=name,
        email=normalize_email(email),
        password=hash_password(password),
        is_admin=is_admin,
    )
    db.add(cred)
    try:
        await db.commit()
        await db.refresh(cred)
    except IntegrityError:
        await db.rollback()
        raise ValueError("Email already registered")
    return cred


# ---------- READ ----------

async def get_credential_by_id(db: AsyncSession, cred_id: str) -> Credentials | None:
    return await db.get(Credentials, cred_id)



async def get_credential_by_email(db: AsyncSession, email: str) -> Credentials | None:
    stmt = select(Credentials).where(Credentials.email == normalize_email(email))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_credentials(db: AsyncSession, skip: int = 0, limit: int = 50) -> list[Credentials]:
    stmt = select(Credentials).order_by(Credentials.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())

# ---------- LOGIN ----------

async def authenticate(db: AsyncSession, email: str, password: str) -> Credentials:
    """Returns the credential on success, raises ValueError otherwise."""
    cred = await get_credential_by_email(db, email)

    if cred is None:
        verify_password(password, _DUMMY_HASH)  # timing protection
        raise ValueError("Invalid email or password")

    if not verify_password(password, cred.password):
        raise ValueError("Invalid email or password")

    if cred.is_banned:
        raise PermissionError("Account is banned")

    return cred


# ---------- UPDATE ----------

async def update_credential(
    db: AsyncSession,
    cred_id: str,
    name: str | None = None,
    email: str | None = None,
) -> Credentials:
    cred = await db.get(Credentials, cred_id)
    if cred is None:
        raise LookupError("Credential not found")

    if name is not None:
        cred.name = name
    if email is not None:
        new_email = normalize_email(email)
        if new_email != cred.email:
            cred.email = new_email
            cred.email_verified = False  # must re-verify the new address

    try:
        await db.commit()
        await db.refresh(cred)

    except IntegrityError:
        await db.rollback()
        raise ValueError("Email already registered")
    return cred


async def change_password(
    db: AsyncSession, cred_id: str, old_password: str, new_password: str
) -> None:
    cred = await db.get(Credentials, cred_id)
    if cred is None:
        raise LookupError("Credential not found")
    if not verify_password(old_password, cred.password):
        raise ValueError("Old password is incorrect")

    cred.password = hash_password(new_password)
    await db.commit()


async def set_ban(db: AsyncSession, cred_id: str) -> Credentials:
    cred = await db.get(Credentials, cred_id)
    if cred is None:
        raise LookupError("Credential not found")

    cred.is_banned = True
    await db.commit()
    await db.refresh(cred)
    return cred


async def mark_email_verified(db: AsyncSession, cred_id: str) -> None:
    cred = await db.get(Credentials, cred_id)
    if cred is None:
        raise LookupError("Credential not found")
    cred.email_verified = True
    await db.commit()


# ---------- DELETE ----------

async def delete_credential(db: AsyncSession, cred_id: str) -> None:
    cred = await db.get(Credentials, cred_id)
    if cred is None:
        raise LookupError("Credential not found")

    # users.credentials_id is a FK, so detach linked users before deleting
    await db.execute(
        update(User).where(User.credentials_id == cred_id).values(credentials_id=None)
    )
    await db.delete(cred)
    await db.commit()

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

# Fields that callers are allowed to change through update_user
UPDATABLE_FIELDS = {
    "name",
    "email",
    "phone_no",
    "pan",
    "address",
    "statement_from",
    "statement_to",
    "credentials_id",
}


# ---------- helpers ----------

def normalize_pan(pan: str | None) -> str | None:
    if pan is None:
        return None
    pan = pan.strip().upper()
    if not PAN_REGEX.match(pan):
        raise ValueError(f"Invalid PAN: {pan}")
    return pan


def normalize_email(email: str | None) -> str | None:
    return email.strip().lower() if email else None


# ---------- CREATE ----------

def create_user(
    db: AsyncSession,
    id : str | None = None,
    name: str | None = None,
    email: str | None = None,
    phone_no: int | None = None,
    pan: str | None = None,
    address: str | None = None,
    statement_from: datetime | None = None,
    statement_to: datetime | None = None,
    credentials_id: str | None = None,
) -> User:
    user = User(
        id = id,
        name=name,
        email=normalize_email(email),
        phone_no=phone_no,
        pan=normalize_pan(pan),
        address=address,
        statement_from=statement_from,
        statement_to=statement_to,
        credentials_id=credentials_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------- READ ----------

def get_user_by_id(
    db: AsyncSession, user_id: str, include_deleted: bool = False
) -> User | None:
    user = db.get(User, user_id)
    if user is None or (user.deleted_at is not None and not include_deleted):
        return None
    return user


def get_user_by_pan(db: AsyncSession, pan: str) -> User | None:
    stmt = select(User).where(
        User.pan == normalize_pan(pan), User.deleted_at.is_(None)
    )
    return db.execute(stmt).scalars().first()


def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(
        User.email == normalize_email(email), User.deleted_at.is_(None)
    )
    return db.execute(stmt).scalars().first()


def list_users(
    db: AsyncSession, skip: int = 0, limit: int = 50, include_deleted: bool = False
) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    if not include_deleted:
        stmt = stmt.where(User.deleted_at.is_(None))
    return list(db.execute(stmt).scalars())


# ---------- UPDATE ----------

def update_user(db: AsyncSession, user_id: str, **fields) -> User:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise LookupError("User not found")

    unknown = set(fields) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"Cannot update fields: {', '.join(sorted(unknown))}")

    if "pan" in fields:
        fields["pan"] = normalize_pan(fields["pan"])
    if "email" in fields:
        fields["email"] = normalize_email(fields["email"])

    for key, value in fields.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


# ---------- SAVE (create or update) ----------

def save_user(db: AsyncSession, pan: str, **fields) -> tuple[User, bool]:
    """
    Find a user by PAN and update them, or create a new one.
    Handy when importing a statement. Returns (user, created).
    """
    existing = get_user_by_pan(db, pan)
    if existing:
        return update_user(db, existing.id, **fields), False

    return create_user(db, pan=pan, **fields), True


# ---------- DELETE ----------

def soft_delete_user(db: AsyncSession, user_id: str) -> None:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise LookupError("User not found")
    user.deleted_at = datetime.now()
    db.commit()


def restore_user(db: AsyncSession, user_id: str) -> User:
    user = get_user_by_id(db, user_id, include_deleted=True)
    if user is None:
        raise LookupError("User not found")
    user.deleted_at = None
    db.commit()
    db.refresh(user)
    return user


# Fields that callers are allowed to change through update_scheme
UPDATABLE_FIELDS = {
    "amc_name",
    "folio_no",
    "holder_name",
    "scheme_name",
    "scheme_type",
    "scheme_category",
    "sub_scheme_category",
    "scheme_code",
    "nav_date",
    "nav_inr",
    "isin",
    "pan",
    "closing_units",
    "total_cost_value_inr",
}
 
 
# ---------- CREATE ----------
 
def create_scheme(
    db: AsyncSession,
    user_id: str,
    id : str | None = None,
    amc_name: str | None = None,
    folio_no: str | None = None,
    holder_name: str | None = None,
    scheme_name: str | None = None,
    scheme_type: str | None = None,
    scheme_category: str | None = None,
    sub_scheme_category: str | None = None,
    scheme_code: str | None = None,
    nav_date: datetime | None = None,
    nav_inr: float | None = None,
    isin: str | None = None,
    pan: str | None = None,
    closing_units: float | None = None,
    total_cost_value_inr: float | None = None,
) -> MutualFundHolding:
    if db.get(User, user_id) is None:
        raise LookupError("User not found")
 
    scheme = MutualFundHolding(
        id = id,
        user_id=user_id,
        amc_name=amc_name,
        folio_no=folio_no,
        holder_name=holder_name,
        scheme_name=scheme_name,
        scheme_type=scheme_type,
        scheme_category=scheme_category,
        sub_scheme_category=sub_scheme_category,
        scheme_code=scheme_code,
        nav_date=nav_date,
        nav_inr=nav_inr,
        isin=isin,
        pan=pan.strip().upper() if pan else None,
        closing_units=closing_units,
        total_cost_value_inr=total_cost_value_inr,
    )
    db.add(scheme)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Scheme already exists for this user (same folio_no and isin)")
    db.refresh(scheme)
    return scheme
 
 
# ---------- READ ----------
 
def get_scheme_by_id(db: AsyncSession, scheme_id: str) -> MutualFundHolding | None:
    return db.get(MutualFundHolding, scheme_id)
 
 
def get_scheme_by_folio_isin(
    db: AsyncSession, user_id: str, folio_no: str, isin: str
) -> MutualFundHolding | None:
    stmt = select(MutualFundHolding).where(
        MutualFundHolding.user_id == user_id,
        MutualFundHolding.folio_no == folio_no,
        MutualFundHolding.isin == isin,
    )
    return db.execute(stmt).scalars().first()
 
 
def list_schemes_by_user(
    db: AsyncSession, user_id: str, skip: int = 0, limit: int = 100
) -> list[MutualFundHolding]:
    stmt = (
        select(MutualFundHolding)
        .where(MutualFundHolding.user_id == user_id)
        .order_by(MutualFundHolding.scheme_name)
        .offset(skip)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())
 
 
# ---------- UPDATE ----------
 
def update_scheme(db: AsyncSession, scheme_id: str, **fields) -> MutualFundHolding:
    scheme = db.get(MutualFundHolding, scheme_id)
    if scheme is None:
        raise LookupError("Scheme not found")
 
    unknown = set(fields) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"Cannot update fields: {', '.join(sorted(unknown))}")
 
    if fields.get("pan"):
        fields["pan"] = fields["pan"].strip().upper()
 
    for key, value in fields.items():
        setattr(scheme, key, value)
 
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Another scheme already has this folio_no and isin")
    db.refresh(scheme)
    return scheme
 
 
# ---------- SAVE (create or update) ----------
 
def save_scheme(
    db: AsyncSession, user_id: str, folio_no: str, isin: str, **fields
) -> tuple[MutualFundHolding, bool]:
    """
    Find a scheme by (user, folio_no, isin) and update it, or create it.
    Returns (scheme, created).
    """
    existing = get_scheme_by_folio_isin(db, user_id, folio_no, isin)
    if existing:
        return update_scheme(db, existing.id, **fields), False
 
    return create_scheme(db, user_id, folio_no=folio_no, isin=isin, **fields), True
 
 
# ---------- DELETE ----------
 
def delete_scheme(db: AsyncSession, scheme_id: str) -> None:
    scheme = db.get(MutualFundHolding, scheme_id)
    if scheme is None:
        raise LookupError("Scheme not found")
 
    # transactions have an FK to this scheme, so remove them first
    db.execute(
        delete(MutualFundTransaction).where(
            MutualFundTransaction.scheme_id == scheme_id
        )
    )
    db.delete(scheme)
    db.commit()
 

if __name__ == "__main__":
    with SessionLocal() as db:
        user = create_credential(
            db,
            name="Alex",
            email="alex@example.com",
            password="password",
            is_admin=True,
        )
        print("the user data is ", user.id)



