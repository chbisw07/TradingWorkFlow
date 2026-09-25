from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from twf import auth
from twf.api.dependencies import get_db_session
from twf.config.settings import Settings
from twf.infrastructure.identity import User
from twf.schemas import ErrorResponse

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
Database = Annotated[Session, Depends(get_db_session)]


class LoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128, repr=False)

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        return auth.normalize_username(value)


class CurrentUser(BaseModel):
    id: UUID
    username: str
    display_name: str


class LogoutResult(BaseModel):
    logged_out: bool = True


def require_origin(request: Request) -> None:
    settings: Settings = request.app.state.settings
    origins = request.headers.getlist("origin")
    if len(origins) != 1 or origins[0] not in settings.allowed_origins:
        raise HTTPException(403)


def require_login_budget(request: Request) -> None:
    peer = request.client.host if request.client else "unknown"
    if not request.app.state.login_limit.allow(peer):
        raise HTTPException(429, headers={"Retry-After": "60"})


def get_current_user(request: Request, session: Database) -> User:
    settings: Settings = request.app.state.settings
    user = auth.current_user(session, request.cookies.get(settings.session_cookie_name))
    if user is None:
        raise HTTPException(401)
    return user


def public_user(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, username=user.username, display_name=user.display_name)


@router.post(
    "/login",
    dependencies=[Depends(require_origin), Depends(require_login_budget)],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 429)},
)
def login(
    payload: LoginInput, request: Request, response: Response, session: Database
) -> CurrentUser:
    settings: Settings = request.app.state.settings
    user = auth.authenticate(
        session, payload.username, payload.password, request.app.state.auth_dummy_hash
    )
    if user is None or not user.is_active:
        event = "auth_inactive_rejected" if user else "auth_login_failed"
        request.app.state.logger.info(event)
        raise HTTPException(401)
    token = auth.establish_session(
        session,
        user,
        settings.session_ttl_seconds,
        request.cookies.get(settings.session_cookie_name),
    )
    session.commit()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.environment == "production",
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    request.app.state.logger.info("auth_login_succeeded", extra={"user_id": str(user.id)})
    return public_user(user)


@router.post(
    "/logout", dependencies=[Depends(require_origin)], responses={403: {"model": ErrorResponse}}
)
def logout(request: Request, response: Response, session: Database) -> LogoutResult:
    settings: Settings = request.app.state.settings
    auth.revoke_session(session, request.cookies.get(settings.session_cookie_name))
    session.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.environment == "production",
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    request.app.state.logger.info("auth_logout")
    return LogoutResult()


@router.get("/me", responses={401: {"model": ErrorResponse}})
def me(response: Response, user: Annotated[User, Depends(get_current_user)]) -> CurrentUser:
    response.headers["Cache-Control"] = "no-store"
    return public_user(user)
