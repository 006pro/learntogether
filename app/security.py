import secrets

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

SESSION_USER_KEY = "user_id"
SESSION_CSRF_KEY = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def get_csrf_token(request: Request) -> str:
    token = request.session.get(SESSION_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF_KEY] = token
    return token


def verify_csrf(request: Request) -> None:
    expected = request.session.get(SESSION_CSRF_KEY)
    provided = request.headers.get(CSRF_HEADER)
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your session token is missing or out of date. Refresh the page and try again.",
        )


def start_session(request: Request, user: User) -> None:
    # Start from a clean session so nothing from before sign-in carries over.
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.id
    request.session[SESSION_CSRF_KEY] = secrets.token_urlsafe(32)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get(SESSION_USER_KEY)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None:
        request.session.clear()
    return user


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    return user


def require_writer(request: Request, user: User = Depends(require_user)) -> User:
    """Authenticated user making a state-changing request with a valid CSRF token."""
    verify_csrf(request)
    return user
