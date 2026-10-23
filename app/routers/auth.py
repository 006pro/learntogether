import logging
from pathlib import Path

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import AuthOptions, DevLogin
from app.security import get_csrf_token, get_current_user, start_session, verify_csrf

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = APIRouter(tags=["auth"])
# Registered only when development sign-in is active (see app.main.create_app).
dev_router = APIRouter(tags=["auth"])


def _upsert_user(db: Session, subject: str, name: str, email: str | None) -> User:
    user = db.scalar(select(User).where(User.subject == subject))
    if user is None:
        user = User(subject=subject, name=name, email=email)
        db.add(user)
    else:
        user.name = name
        user.email = email
    db.commit()
    db.refresh(user)
    return user


def _login_error(code: str) -> RedirectResponse:
    return RedirectResponse(f"/login?error={code}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", include_in_schema=False)
def login_page(user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse(STATIC_DIR / "login.html")


@router.get("/auth/options", response_model=AuthOptions)
def auth_options(request: Request) -> AuthOptions:
    settings = request.app.state.settings
    return AuthOptions(
        google_enabled=settings.google_configured,
        dev_login_enabled=settings.dev_auth_active,
        csrf_token=get_csrf_token(request),
    )


@router.get("/auth/google", include_in_schema=False)
async def google_login(request: Request):
    settings = request.app.state.settings
    if not settings.google_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    redirect_uri = settings.oauth_redirect_uri or str(request.url_for("auth_callback"))
    # Authlib generates state, nonce and a PKCE verifier and stores them in the session.
    return await request.app.state.oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback", name="auth_callback", include_in_schema=False)
async def google_callback(request: Request, db: Session = Depends(get_db)):
    if not request.app.state.settings.google_configured:
        return _login_error("not_configured")
    try:
        # Validates state against the session, exchanges the code and verifies the ID token (incl. nonce).
        token = await request.app.state.oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        logger.warning("Google sign-in failed: %s", exc)
        return _login_error("google")

    claims = token.get("userinfo") or {}
    subject = claims.get("sub")
    if not subject:
        return _login_error("google")
    if not claims.get("email_verified"):
        return _login_error("unverified")

    email = claims.get("email")
    name = claims.get("name") or email or "Google user"
    user = _upsert_user(db, subject=subject, name=name, email=email)
    start_session(request, user)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    verify_csrf(request)
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@dev_router.post("/auth/dev-login", status_code=status.HTTP_204_NO_CONTENT)
def dev_login(payload: DevLogin, request: Request, db: Session = Depends(get_db)) -> Response:
    """Development-only sign-in by display name. Never registered in production."""
    verify_csrf(request)
    user = _upsert_user(db, subject=f"dev:{payload.name.casefold()}", name=payload.name, email=None)
    start_session(request, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
