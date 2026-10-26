"""Shared FastAPI helpers: current user, JSON body reading, error type."""
from fastapi import HTTPException, Request


class ApiError(HTTPException):
    def __init__(self, message: str, status: int = 400):
        super().__init__(status_code=status, detail=message)


def current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if user is None:
        raise ApiError("Nie si prihlásený.", 401)
    return user


def admin_user(request: Request) -> dict:
    user = current_user(request)
    if not user.get("is_admin"):
        raise ApiError("Toto môže len administrátor.", 403)
    return user


async def json_body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        raise ApiError("Očakávam JSON.") from None
    if not isinstance(data, dict):
        raise ApiError("Očakávam JSON objekt.")
    return data


def public_user(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"], "name": u["name"], "email": u.get("email", ""),
            "is_admin": bool(u.get("is_admin")), "active": bool(u.get("active", 1)),
            "invited": not u.get("password_hash"), "last_login_at": u.get("last_login_at"),
            "must_change_password": bool(u.get("must_change_password"))}
