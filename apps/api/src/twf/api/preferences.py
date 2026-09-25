from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from twf.api.auth import Database, get_current_user, require_origin
from twf.infrastructure.identity import User
from twf.preferences import Preferences, SettingsFailure
from twf.schemas import ErrorResponse
from twf.settings_contracts import (
    DEFINITIONS,
    ApplyInput,
    Definition,
    FoundationPolicy,
    PreferenceValues,
    ProfileEdit,
    ProfileInput,
    ProfileView,
    RevisionInput,
    SettingsView,
    ValuesInput,
)

router = APIRouter(
    prefix="/api/v1/settings",
    tags=["Personal settings"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422)},
)


def service(
    request: Request,
    response: Response,
    session: Database,
    user: Annotated[User, Depends(get_current_user)],
) -> Preferences:
    response.headers["Cache-Control"] = "no-store"
    return Preferences(
        session, user.id, FoundationPolicy(), getattr(request.state, "request_id", None)
    )


UseCases = Annotated[Preferences, Depends(service)]


@router.get("/definitions")
def definitions(use: UseCases) -> list[Definition]:
    use.authorize()
    return list(DEFINITIONS)


@router.get("/values")
def values(use: UseCases) -> SettingsView:
    return use.read()


@router.put("/values", dependencies=[Depends(require_origin)])
def update_values(payload: ValuesInput, use: UseCases) -> SettingsView:
    return use.write(payload.revision, payload.values)


@router.post("/reset", dependencies=[Depends(require_origin)])
def reset(payload: RevisionInput, use: UseCases) -> SettingsView:
    return use.write(payload.revision, PreferenceValues(), "RESET")


@router.post("/deactivate", dependencies=[Depends(require_origin)])
def deactivate(payload: RevisionInput, use: UseCases) -> SettingsView:
    return use.write(payload.revision, use.read().overrides, "DEACTIVATE")


@router.get("/profiles")
def profiles(use: UseCases) -> list[ProfileView]:
    return use.profiles()


@router.post("/profiles", dependencies=[Depends(require_origin)], status_code=201)
def create_profile(payload: ProfileInput, use: UseCases) -> ProfileView:
    return use.save_profile(payload)


@router.put("/profiles/{profile_id}", dependencies=[Depends(require_origin)])
def edit_profile(profile_id: UUID, payload: ProfileEdit, use: UseCases) -> ProfileView:
    return use.save_profile(payload, profile_id, payload.revision)


@router.post("/profiles/{profile_id}/apply", dependencies=[Depends(require_origin)])
def apply_profile(profile_id: UUID, payload: ApplyInput, use: UseCases) -> SettingsView:
    return use.apply_profile(profile_id, payload.revision, payload.profile_revision)


async def settings_error(request: Request, exc: Exception) -> Response:
    from twf.api.errors import http_error

    assert isinstance(exc, SettingsFailure)
    return await http_error(request, HTTPException(exc.status))
