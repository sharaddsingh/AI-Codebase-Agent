"""In-memory user store (fixture only)."""

from dataclasses import dataclass


@dataclass
class User:
    id: int
    username: str
    # bcrypt-style placeholder hash; see app.auth.verify_password
    password_hash: str
    email: str


# Password hashes below correspond to the password "s3cret" (fixture only).
_USERS = {
    "alice": User(id=1, username="alice", password_hash="hash$s3cret", email="alice@example.com"),
    "bob": User(id=2, username="bob", password_hash="hash$s3cret", email="bob@example.com"),
}


def get_user(username: str) -> User | None:
    return _USERS.get(username)
