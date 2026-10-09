"""Official SDK transport behind bounded, provider-neutral tool contracts."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Protocol

import anyio
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp_types import PaginatedRequestParams
from pydantic import JsonValue

from twf.integrations.mcp.contracts import Code, Failure, ProviderConfig, Tool, ToolPolicy
from twf.integrations.mcp.http import HTTPFactory, SafeTransport, mapped
from twf.integrations.mcp.lifecycle import Operations, operation

Fence = Callable[[], Awaitable[None]]


def validate_schema_envelope(schema: dict[str, JsonValue]) -> None:
    """Bound discovery metadata without adopting an untrusted tool's schema."""

    def walk(value: JsonValue, depth: int = 0) -> None:
        if depth > 12:
            raise Failure(Code.SCHEMA_MISMATCH)
        if isinstance(value, dict):
            for child in value.values():
                walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                walk(child, depth + 1)

    try:
        if len(json.dumps(schema)) > 16384 or schema.get("type") != "object":
            raise Failure(Code.SCHEMA_MISMATCH)
        walk(schema)
        Draft202012Validator.check_schema(schema)
    except (SchemaError, ValueError, RecursionError):
        raise Failure(Code.SCHEMA_MISMATCH) from None


def validate_schema(schema: dict[str, JsonValue]) -> None:
    """Apply the strict, non-resolving policy to a server-allowed tool schema."""

    validate_schema_envelope(schema)

    def walk(value: JsonValue) -> None:
        if isinstance(value, dict):
            if any(
                key in value
                for key in ("$ref", "$dynamicRef", "$recursiveRef", "pattern", "patternProperties")
            ):
                raise Failure(Code.SCHEMA_MISMATCH)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(schema)


def allowed(
    tools: tuple[Tool, ...], policy: ToolPolicy, name: str, arguments: dict[str, JsonValue]
) -> None:
    if name not in policy.allowed:
        raise Failure(Code.TOOL_NOT_ALLOWED)
    tool = next((t for t in tools if t.name == name), None)
    if tool is None:
        raise Failure(Code.TOOL_NOT_FOUND)
    try:
        if len(json.dumps(arguments, allow_nan=False)) > 16384:
            raise ValueError
        Draft202012Validator(tool.input_schema).validate(arguments)
    except (ValidationError, ValueError, RecursionError):
        raise Failure(Code.INVALID_ARGUMENTS) from None


class ToolClient(Protocol):
    async def execute(
        self,
        config: ProviderConfig,
        headers: dict[str, str],
        fence: Fence,
        policy: ToolPolicy,
        name: str | None = None,
        arguments: dict[str, JsonValue] | None = None,
    ) -> tuple[tuple[Tool, ...], dict[str, JsonValue] | None]: ...


class SDKClient:
    def __init__(self, http: HTTPFactory) -> None:
        self.http = http
        self.operations = Operations()

    async def execute(
        self,
        config: ProviderConfig,
        headers: dict[str, str],
        fence: Fence,
        policy: ToolPolicy,
        name: str | None = None,
        arguments: dict[str, JsonValue] | None = None,
    ) -> tuple[tuple[Tool, ...], dict[str, JsonValue] | None]:
        return await self.operations.run(
            config.timeout_seconds,
            lambda: self._execute(config, headers, fence, policy, name, arguments),
        )

    async def _execute(
        self,
        config: ProviderConfig,
        headers: dict[str, str],
        fence: Fence,
        policy: ToolPolicy,
        name: str | None = None,
        arguments: dict[str, JsonValue] | None = None,
    ) -> tuple[tuple[Tool, ...], dict[str, JsonValue] | None]:
        if name is not None and name not in policy.allowed:
            raise Failure(Code.TOOL_NOT_ALLOWED)
        transport: SafeTransport | None = None
        scope = operation.get()
        assert scope is not None
        deadline = scope.deadline
        try:
            with anyio.fail_after(config.timeout_seconds):
                await fence()
                async with self.http.client(
                    config,
                    frozenset({config.endpoint}),
                    headers,
                    fence=fence,
                    deadline=deadline,
                ) as http:
                    assert isinstance(http._transport, SafeTransport)
                    transport = http._transport
                    async with streamable_http_client(
                        config.endpoint, http_client=http, terminate_on_close=False
                    ) as streams:
                        async with ClientSession(
                            *streams, read_timeout_seconds=config.timeout_seconds
                        ) as session:
                            try:
                                await session.initialize()
                            except RuntimeError:
                                raise Failure(Code.CONTRACT_MISMATCH) from None
                            tools: list[Tool] = []
                            cursor: str | None = None
                            seen: set[str] = set()
                            for _ in range(config.max_pages):
                                await fence()
                                page = await session.list_tools(
                                    params=PaginatedRequestParams(cursor=cursor)
                                )
                                for item in page.tools:
                                    if item.name in seen or len(tools) >= config.max_tools:
                                        raise Failure(Code.SCHEMA_MISMATCH)
                                    seen.add(item.name)
                                    tool = Tool(
                                        name=item.name,
                                        input_schema=item.input_schema,
                                        description=item.description,
                                    )
                                    validate_schema_envelope(tool.input_schema)
                                    if item.output_schema is not None:
                                        validate_schema_envelope(item.output_schema)
                                    if item.name in policy.allowed:
                                        validate_schema(tool.input_schema)
                                        if item.output_schema is not None:
                                            validate_schema(item.output_schema)
                                    tools.append(tool)
                                cursor = page.next_cursor
                                if cursor is None:
                                    break
                            else:
                                raise Failure(Code.SCHEMA_MISMATCH)
                            result: dict[str, JsonValue] | None = None
                            if name is not None:
                                allowed(tuple(tools), policy, name, arguments or {})
                                await fence()
                                try:
                                    reply = await session.call_tool(name, arguments or {})
                                except RuntimeError:
                                    raise Failure(Code.SCHEMA_MISMATCH) from None
                                # SDK types and remote error text stop here.
                                payload = reply.model_dump(mode="json", by_alias=True)
                                if payload.get("isError"):
                                    # A tool-error reply proves the transport responded.
                                    raise Failure(Code.TOOL_FAILED)
                                encoded = json.dumps(payload, allow_nan=False)
                                if len(encoded.encode()) > config.max_response_bytes:
                                    raise Failure(Code.SCHEMA_MISMATCH)
                                result = json.loads(encoded)
                            await fence()
                            # Termination belongs to the same deadline. The SDK's finally
                            # must not perform a second, potentially shielded DELETE.
                            if transport.session_id:
                                await http.delete(
                                    config.endpoint,
                                    headers={
                                        "Mcp-Session-Id": transport.session_id,
                                    },
                                )
                            return tuple(tools), result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if transport and transport.failure:
                raise transport.failure from None
            if asyncio.get_running_loop().time() >= deadline:
                raise Failure(Code.TIMEOUT) from None
            raise mapped(exc) from None
