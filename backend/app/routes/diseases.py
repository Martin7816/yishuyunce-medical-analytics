"""Disease TOP10 route. No metric computation belongs here."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.exceptions import MethodNotAllowed

from ..errors import InvalidRequestError


diseases_bp = Blueprint("diseases", __name__)


def _request_has_body() -> bool:
    """Detect body data even when the client uses chunked transfer encoding."""
    if request.headers.get("Transfer-Encoding"):
        return True
    if request.content_length is not None:
        return request.content_length > 0
    if request.environ.get("wsgi.input_terminated"):
        return bool(request.get_data(cache=True))
    return False


@diseases_bp.route(
    "/api/v1/diseases/top10",
    methods=["GET"],
    provide_automatic_options=False,
)
def get_disease_top10():
    # Flask normally adds HEAD to every GET route. This endpoint's contract
    # is deliberately GET-only, so reject the implicit method explicitly.
    if request.method != "GET":
        raise MethodNotAllowed(valid_methods=["GET"])
    if request.args:
        raise InvalidRequestError(
            code="INVALID_QUERY_PARAMETER",
            message="This endpoint does not accept query parameters.",
            details={"parameters": sorted(request.args.keys())},
        )

    if _request_has_body():
        raise InvalidRequestError(
            code="INVALID_REQUEST_FORMAT",
            message="This GET endpoint does not accept a request body.",
        )

    result = current_app.extensions["disease_top10_service"].get_top10()
    return jsonify(
        {
            "code": "OK",
            "message": "success",
            "data": result,
            "trace_id": g.trace_id,
        }
    )
