# security.py

import secrets
import jwt
import hashlib

from cuid2 import cuid_wrapper
from datetime import datetime, timedelta, timezone
from pwdlib import PasswordHash
import bcrypt

from dotenv import load_dotenv
import os

load_dotenv()

password_hasher = PasswordHash.recommended()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
REFRESH_TOKEN_EXPIRE_DAYS = 7

if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is not configured")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15


# ---------- PASSWORD ----------

def hash_password(password: str) -> str:
    return password_hasher.hash(password)




def verify_password(password: str, hashed_password: str) -> bool:
    try:
        if hashed_password.startswith("$2"):
            return bcrypt.checkpw(
                password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )

        return password_hasher.verify(password, hashed_password)

    except Exception:
        return False



def cuid_generator() -> str:
    create_cuid = cuid_wrapper()
    return  create_cuid()
    



# ---------- JWT ACCESS TOKEN ----------

def create_access_token(user_id: str) -> str:

    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_urlsafe(16),
        "type": "access",
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:

    payload = jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "iat", "sub", "jti", "type"]},
    )

    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")

    return payload


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )