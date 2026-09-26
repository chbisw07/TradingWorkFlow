"""Dedicated credential ingestion and cookie-safe two-stage broker auth routes."""

import re
from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select
from starlette.responses import JSONResponse, RedirectResponse

from twf.api.auth import Database, get_current_user, require_origin
from twf.api.broker_foundation import invoke
from twf.auth import current_user, token_digest
from twf.broker_auth import BrokerAuth
from twf.broker_foundation import BrokerFoundationFailure
from twf.brokers.foundation_contracts import (
    BrokerAccountView,
    BrokerPermission,
    BrokerPermissionPolicy,
)
from twf.brokers.zerodha_auth import AuthProvider
from twf.infrastructure.broker_auth import (
    BrokerAuthAttempt,
    BrokerAuthConfiguration,
    BrokerSecretLifecycle,
)
from twf.infrastructure.broker_foundation import BrokerConnectionRecord
from twf.infrastructure.identity import User
from twf.secrets import SecretStore, SecretValue

router = APIRouter(prefix="/api/v1/broker-auth", tags=["Broker authentication"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    expected_generation: int = Field(ge=0)
    api_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    api_secret: SecretStr = Field(min_length=1, max_length=4096)


class Generation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_generation: int = Field(ge=0)


class ConnectionView(BaseModel):
    account: BrokerAccountView
    can_configure: bool
    can_connect: bool
    can_disconnect: bool
    unavailable_reason: str | None
    callback_url: str
    cleanup_pending: int
    bound_at: datetime | None
    last_auth_success_at: datetime | None


class Initiation(BaseModel):
    login_url: str


class Completion(BaseModel):
    broker_account_id: UUID


class CleanupResult(BaseModel):
    cleanup_pending: int


def compose(request: Request, session: Database, owner: UUID) -> BrokerAuth:
    return BrokerAuth(
        session,
        owner,
        cast(BrokerPermissionPolicy, request.app.state.broker_permission_policy),
        cast(SecretStore, request.app.state.secret_store),
        request.app.state.settings.environment,
        request.state.request_id,
        logger=request.app.state.logger,
    ).setup(request.app.state.settings, cast(AuthProvider, request.app.state.broker_auth_provider))


def service(
    request: Request, session: Database, user: Annotated[User, Depends(get_current_user)]
) -> BrokerAuth:
    return compose(request, session, user.id)


Use = Annotated[BrokerAuth, Depends(service)]


def session_hash(request: Request) -> str:
    return token_digest(request.cookies.get(request.app.state.settings.session_cookie_name, ""))


def nonce_cookie(request: Request) -> str:
    return (
        "__Host-twf_broker_finalize"
        if request.app.state.settings.environment == "production"
        else "twf_broker_finalize"
    )


@router.get("/accounts")
def accounts(use: Use, response: Response) -> list[ConnectionView]:
    response.headers["Cache-Control"] = "no-store"
    views = invoke(use.list_accounts)
    result = []
    for view in views:
        config = use.session.get(BrokerAuthConfiguration, view.broker_account_id)
        connection = use.session.get(BrokerConnectionRecord, view.broker_account_id)
        # Time-derived state stays honest without a background worker.
        if (
            connection
            and connection.expires_at
            and use._aware(connection.expires_at) <= datetime.now(UTC)
            and view.authentication_state == "CONNECTED"
        ):
            view = view.model_copy(update={"authentication_state": "REAUTH_REQUIRED"})
        if view.authentication_state == "AUTH_IN_PROGRESS":
            live_attempt = use.session.scalar(
                select(BrokerAuthAttempt.state_hash).where(
                    BrokerAuthAttempt.broker_account_id == view.broker_account_id,
                    BrokerAuthAttempt.status.in_(
                        ("CREATED", "EXCHANGING", "PENDING", "FINALIZING")
                    ),
                    BrokerAuthAttempt.expires_at > datetime.now(UTC),
                )
            )
            if not live_attempt:
                view = view.model_copy(update={"authentication_state": "AUTH_REQUIRED"})
        can_configure = use.policy.allows(
            use.actor_user_id, BrokerPermission.CONFIGURE, view.owner_user_id
        )
        can_disconnect = use.policy.allows(
            use.actor_user_id, BrokerPermission.DISCONNECT, view.owner_user_id
        )
        reason = (
            "An approved secret store and enabled broker deployment are required."
            if not use.available()
            else "Configure the API key and secret first."
            if not view.configured or config is None
            else "Enable this account before connecting."
            if not view.enabled
            else "Connection is already active or in progress."
            if view.authentication_state in {"CONNECTED", "AUTH_IN_PROGRESS"}
            else None
        )
        permitted = use.policy.allows(
            use.actor_user_id, BrokerPermission.CONNECT, view.owner_user_id
        )
        if not permitted:
            reason = "Broker connect permission is unavailable."
        view = view.model_copy(update={"connectable": reason is None and permitted})
        pending = len(
            list(
                use.session.scalars(
                    select(BrokerSecretLifecycle.reference).where(
                        BrokerSecretLifecycle.broker_account_id == view.broker_account_id,
                        BrokerSecretLifecycle.state == "REVOKED",
                    )
                )
            )
        )
        result.append(
            ConnectionView(
                account=view,
                can_configure=can_configure,
                can_connect=reason is None and permitted,
                can_disconnect=can_disconnect,
                unavailable_reason=reason,
                callback_url=use.settings.zerodha_callback_url,
                cleanup_pending=pending,
                bound_at=config.bound_at if config else None,
                last_auth_success_at=config.last_auth_success_at if config else None,
            )
        )
    return result


@router.post("/accounts/{account_id}/configure", dependencies=[Depends(require_origin)])
def configure(
    account_id: UUID, payload: Credentials, use: Use, response: Response
) -> dict[str, bool]:
    invoke(
        lambda: use.configure(
            account_id,
            payload.api_key,
            SecretValue(payload.api_secret.get_secret_value()),
            payload.expected_revision,
            payload.expected_generation,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return {"configured": True}


@router.post("/accounts/{account_id}/connect", dependencies=[Depends(require_origin)])
def connect(account_id: UUID, request: Request, use: Use, response: Response) -> Initiation:
    response.headers["Cache-Control"] = "no-store"
    return Initiation(login_url=invoke(lambda: use.initiate(account_id, session_hash(request))))


@router.get("/callback", include_in_schema=False)
def callback(request: Request, session: Database) -> RedirectResponse:
    # This is the only query-token exception. No page, analytics or token-reflecting error response.
    settings = request.app.state.settings
    response = RedirectResponse(
        settings.zerodha_web_origin + "/broker-auth/complete",
        status_code=303,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        },
    )
    response.delete_cookie(
        nonce_cookie(request),
        path="/",
        secure=settings.environment == "production",
        httponly=True,
        samesite="strict",
    )
    query = request.query_params
    state, token = query.get("state", ""), query.get("request_token", "")
    if (
        len(query.getlist("state")) != 1
        or len(query.getlist("request_token")) != 1
        or not re.fullmatch(r"[A-Za-z0-9_-]{43}", state)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", token)
        or any(key not in {"state", "request_token", "action", "status"} for key in query)
        or query.get("status", "success") != "success"
    ):
        return response
    attempt = session.get(BrokerAuthAttempt, token_digest(state))
    if attempt is None:
        return response
    owner = attempt.owner_user_id
    session.rollback()
    use = compose(request, session, owner)
    try:
        nonce = use.receive(state, SecretValue(token))
    except Exception:
        session.rollback()
        request.app.state.logger.warning("broker_callback_failed")
        return response
    response.set_cookie(
        nonce_cookie(request),
        nonce,
        max_age=300,
        httponly=True,
        secure=settings.environment == "production",
        samesite="strict",
        path="/",
    )
    return response


@router.post("/finalize", dependencies=[Depends(require_origin)], response_model=Completion)
def finalize(request: Request, session: Database) -> Response:
    settings = request.app.state.settings
    nonce = request.cookies.get(nonce_cookie(request), "")
    user = current_user(session, request.cookies.get(settings.session_cookie_name))
    try:
        if user is None:
            raise BrokerFoundationFailure(401)
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", nonce):
            raise BrokerFoundationFailure(409)
        use = compose(request, session, user.id)
        account_id = use.finalize(nonce, session_hash(request))
        response = JSONResponse({"broker_account_id": str(account_id)})
    except BrokerFoundationFailure as error:
        session.rollback()
        from http import HTTPStatus

        response = JSONResponse(
            {
                "error": {
                    "code": f"HTTP_{error.status}",
                    "message": HTTPStatus(error.status).phrase,
                    "request_id": request.state.request_id,
                    "details": None,
                }
            },
            status_code=error.status,
        )
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(
        nonce_cookie(request),
        path="/",
        secure=settings.environment == "production",
        httponly=True,
        samesite="strict",
    )
    return response


@router.post("/accounts/{account_id}/disconnect", dependencies=[Depends(require_origin)])
def disconnect(
    account_id: UUID, payload: Generation, use: Use, response: Response
) -> dict[str, bool]:
    invoke(lambda: use.disconnect(account_id, payload.expected_generation))
    response.headers["Cache-Control"] = "no-store"
    return {"disconnected": True}


@router.post("/accounts/{account_id}/cleanup", dependencies=[Depends(require_origin)])
def cleanup(account_id: UUID, use: Use, response: Response) -> CleanupResult:
    response.headers["Cache-Control"] = "no-store"
    return CleanupResult(cleanup_pending=invoke(lambda: use.cleanup(account_id)))
