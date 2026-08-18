"""Application liveness endpoint."""

from flask import Blueprint, g, jsonify


health_bp = Blueprint("health", __name__)


@health_bp.get("/api/v1/health")
def health():
    return jsonify(
        {
            "code": "OK",
            "message": "success",
            "data": {"status": "UP"},
            "trace_id": g.trace_id,
        }
    )
