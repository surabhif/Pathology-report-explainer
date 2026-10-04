"""FastAPI dependencies: DB session, current user, role gates."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_user_by_session_token, require_roles
from app.config import get_settings
from app.db import get_db
from app.models import User, UserRole


def _extract_session_token(
    x_session_token: Annotated[str | None, Header()] = None,
    pathology_session: Annotated[str | None, Cookie()] = None,
) -> str | None:
    """Prefer explicit header; fall back to session cookie."""
    settings = get_settings()
    if x_session_token:
        return x_session_token
    # Cookie name is configurable; FastAPI binds the parameter name, so we also
    # accept the default cookie via pathology_session and remap if renamed.
    if pathology_session:
        return pathology_session
    # If cookie name was customized, Cookie() above won't bind — callers can
    # still use the header. For MVP the default name matches.
    _ = settings.session_cookie_name
    return None


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Depends(_extract_session_token)] = None,
) -> User:
    user = get_user_by_session_token(db, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


def get_optional_user(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Depends(_extract_session_token)] = None,
) -> User | None:
    return get_user_by_session_token(db, token)


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    require_roles(user, UserRole.admin)
    return user


def require_annotator(user: Annotated[User, Depends(get_current_user)]) -> User:
    require_roles(user, UserRole.annotator, UserRole.admin)
    return user


def require_clinician(user: Annotated[User, Depends(get_current_user)]) -> User:
    require_roles(user, UserRole.clinician, UserRole.admin)
    return user


DbDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
AnnotatorUser = Annotated[User, Depends(require_annotator)]
ClinicianUser = Annotated[User, Depends(require_clinician)]
