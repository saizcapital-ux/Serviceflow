"""Security primitives: password hashing, JWT tokens, and API keys."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_api_key(key: str) -> str:
    """API keys are high-entropy, so a fast SHA-256 (not bcrypt) is appropriate."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, hashed_key). The full key is shown to the user once."""
    full = "sf_" + secrets.token_urlsafe(32)
    return full, full[:11], hash_api_key(full)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, extra: dict | None = None) -> str:
    """Create a signed JWT. `subject` is the user id; `extra` adds claims."""
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_min),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
