"""Access-token creation and verification.

Tokens are signed with SECRET_KEY. `verify_token` is the single place that
decides whether a request is authenticated; it raises HTTP 401 on any failure,
which is why protected endpoints return 401 for missing/expired/invalid tokens.
"""

import os
import time

from fastapi import HTTPException, status

from .db import User, get_user

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
TOKEN_TTL_SECONDS = 3600


def create_access_token(user: User) -> str:
    issued = int(time.time())
    # Toy token format for the fixture: "<username>.<issued>.<secret-tag>".
    return f"{user.username}.{issued}.{SECRET_KEY[:4]}"


def verify_token(token: str | None) -> User:
    """Return the User for a valid token, else raise 401."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = token.split(".")
    if len(parts) != 3 or parts[2] != SECRET_KEY[:4]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )
    username, issued_str, _ = parts
    try:
        issued = int(issued_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    if int(time.time()) - issued > TOKEN_TTL_SECONDS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    user = get_user(username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return user
