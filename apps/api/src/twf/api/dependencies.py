from typing import cast

from fastapi import Request

from twf.config.settings import Settings


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_request_id(request: Request) -> str | None:
    return cast(str | None, getattr(request.state, "request_id", None))
