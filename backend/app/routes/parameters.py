"""Shared request validation helpers for read-only analytics routes."""

from __future__ import annotations

from collections.abc import Iterable

from flask import request

from ..errors import InvalidRequestError


def reject_unknown_query_parameters(allowed: Iterable[str]) -> None:
    """Reject unknown and repeated query parameters."""

    allowed_names = set(allowed)
    unknown = sorted(set(request.args) - allowed_names)
    if unknown:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "One or more query parameters are not supported.",
            {"parameters": unknown},
        )

    repeated = sorted(
        name
        for name in set(request.args) & allowed_names
        if len(request.args.getlist(name)) > 1
    )
    if repeated:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "Each query parameter may be supplied only once.",
            {"parameters": repeated},
        )


def query_value(name: str) -> str | None:
    """Return a single query value for a known parameter."""

    values = request.args.getlist(name)
    if len(values) > 1:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "Each query parameter may be supplied only once.",
            {"parameters": [name]},
        )
    return values[0] if values else None


def option_values(payload: dict, option_name: str) -> set[str]:
    """Extract published enum values from an options array."""

    raw = payload.get("options", {}).get(option_name, [])
    if not isinstance(raw, list):
        return set()
    return {
        str(item.get("value")) if isinstance(item, dict) else str(item)
        for item in raw
    }


def validate_option(
    parameter_name: str,
    value: str | None,
    payload: dict,
    *,
    option_name: str | None = None,
) -> None:
    """Validate a query/path value against a snapshot-published enum."""

    if value is None:
        return
    published_name = option_name or parameter_name
    if value not in option_values(payload, published_name):
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            f"The {parameter_name} value is not supported.",
            {"parameter": parameter_name},
        )


def request_has_body() -> bool:
    """Detect request data, including chunked bodies without a length."""

    if request.headers.get("Transfer-Encoding"):
        return True
    if request.content_length is not None:
        return request.content_length > 0
    if request.environ.get("wsgi.input_terminated"):
        return bool(request.get_data(cache=True))
    return False
