"""Application wiring: login, current-user dependency, and routes."""

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .auth import authenticate_user
from .routes.items import router as items_router
from .security import create_access_token, verify_token

app = FastAPI(title="Sample Service")


def get_current_user(authorization: str | None = Header(default=None)):
    """FastAPI dependency: extract the bearer token and verify it.

    Returns the authenticated user or raises 401 (via verify_token).
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    return verify_token(token)


@app.post("/login")
def login(username: str, password: str):
    user = authenticate_user(username, password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    return {"access_token": create_access_token(user), "token_type": "bearer"}


@app.get("/me")
def read_me(user=Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "email": user.email}


app.include_router(items_router)
