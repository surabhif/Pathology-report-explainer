"""Auth routes: redeem invite token → session."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.auth import redeem_invite
from app.config import get_settings
from app.deps import CurrentUser, DbDep
from app.schemas import RedeemInviteRequest, SessionOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/redeem", response_model=SessionOut)
def redeem(body: RedeemInviteRequest, db: DbDep, response: Response) -> SessionOut:
    user, session = redeem_invite(db, body.token)
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
    )
    return SessionOut(
        session_token=session.token,
        expires_at=session.expires_at,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/logout")
def logout(response: Response) -> dict:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name)
    return {"ok": True}
