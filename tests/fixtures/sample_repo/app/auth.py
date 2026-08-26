"""Password hashing and user authentication."""

from .db import User, get_user


def hash_password(password: str) -> str:
    # Placeholder scheme for the fixture; a real app would use bcrypt/argon2.
    return f"hash${password}"


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def authenticate_user(username: str, password: str) -> User | None:
    """Return the user when credentials are valid, else None."""
    user = get_user(username)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
