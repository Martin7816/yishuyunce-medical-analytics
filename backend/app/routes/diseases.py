"""Disease TOP10 route. No metric computation belongs here."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..errors import InvalidRequestError


diseases_bp = Blueprint("diseases", __name__)


@diseases_bp.get("/api/v1/diseases/top10")
def get_disease_top10():
    if request.args:
        raise InvalidRequestError(
            code="INVALID_QUERY_PARAMETER",
            message="This endpoint does not accept query parameters.",
            details={"parameters": sorted(request.args.keys())},
        )

    if request.content_length:
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
