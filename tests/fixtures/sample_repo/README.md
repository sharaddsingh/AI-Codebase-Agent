# Sample Service

A tiny FastAPI service used as a fixture for the AI Codebase Engineering Agent.
It has a realistic token-based authentication flow so agent questions like
"how does authentication work?" and "why might this endpoint return 401?" have
real answers to cite.

- `app/main.py` — app wiring, `/login`, `/me`, and the `get_current_user` dependency
- `app/auth.py` — password hashing + user authentication
- `app/security.py` — access-token creation and verification (raises 401)
- `app/routes/items.py` — a protected endpoint
- `app/db.py` — in-memory user store
