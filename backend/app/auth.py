"""Invite-token authentication and session helpers.

Flow:
1. Admin creates a User with an invite_token (or seed provides DEMO_* tokens).
2. Client POSTs /api/auth/redeem with that token.
3. Server issues a SessionToken (cookie + response body).
4. Subsequent requests send cookie or X-Session-Token header.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SessionToken, User, UserRole, utcnow


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def redeem_invite(db: Session, invite_token: str) -> tuple[User, SessionToken]:
    """Exchange an invite token for a session. Invite remains reusable for MVP demos."""
    user = db.query(User).filter(User.invite_token == invite_token).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid invite token")

    settings = get_settings()
    session = SessionToken(
        token=generate_token(),
        user_id=user.id,
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return user, session


def get_user_by_session_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = db.query(SessionToken).filter(SessionToken.token == token).first()
    if not row:
        return None
    # Compare timezone-aware
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < utcnow():
        return None
    return db.query(User).filter(User.id == row.user_id).first()


def require_roles(user: User, *roles: UserRole | str) -> None:
    allowed = {r.value if isinstance(r, UserRole) else r for r in roles}
    if user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' not permitted; requires one of {sorted(allowed)}",
        )


def create_invite_user(
    db: Session,
    *,
    email: str,
    name: str,
    role: str,
    invite_token: str | None = None,
) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=email,
        name=name,
        role=role,
        invite_token=invite_token or generate_token(16),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
