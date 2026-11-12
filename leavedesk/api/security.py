"""Password hashing (Argon2id) and JWT access tokens."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from leavedesk.api.settings import Settings

_hasher = PasswordHasher()  # Argon2id with the library's recommended cost settings

# Used when an email doesn't exist, so a failed login takes the same time either way.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


class AuthenticationError(Exception):
    """Missing, invalid or expired credentials (HTTP 401)."""


@dataclass(frozen=True)
class TokenData:
    employee_id: str
    role: str


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """True only if a real hash exists and matches. Always does the full hash work."""
    try:
        matches = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return matches and password_hash is not None


def create_access_token(employee_id: str, role: str, settings: Settings) -> tuple[str, int]:
    """Return a signed token and its lifetime in seconds."""
    now = datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": employee_id, "role": role, "iat": now, "exp": now + lifetime}
    token = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> TokenData:
    """Check the signature and expiry; raise AuthenticationError on any problem."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],  # never trust the algorithm named in the token
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.PyJWTError as error:
        raise AuthenticationError("Invalid or expired token.") from error
    return TokenData(employee_id=str(payload["sub"]), role=str(payload.get("role", "")))
