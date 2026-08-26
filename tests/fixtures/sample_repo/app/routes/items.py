"""A protected resource. Returns 401 unless a valid bearer token is supplied,
because it depends on `get_current_user` -> `verify_token`.
"""

from fastapi import APIRouter, Depends

from ..security import verify_token

router = APIRouter(prefix="/items", tags=["items"])

_ITEMS = [{"id": 1, "name": "widget"}, {"id": 2, "name": "gadget"}]


def _current_user(authorization: str | None = None):
    token = authorization[7:] if authorization else None
    return verify_token(token)


@router.get("")
def list_items(user=Depends(_current_user)):
    return {"items": _ITEMS, "owner": user.username}
