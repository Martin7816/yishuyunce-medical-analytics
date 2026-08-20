"""High-cost prediction and AI assistant routes."""

from flask import Blueprint, current_app, g, jsonify, request


intelligence_bp = Blueprint("intelligence", __name__)


def _ok(data: dict):
    return jsonify({"code": "OK", "message": "success", "data": data, "trace_id": g.trace_id})


@intelligence_bp.route(
    "/api/v1/models/high-cost/predict",
    methods=["POST"],
    provide_automatic_options=False,
)
def predict_high_cost():
    return _ok(current_app.extensions["high_cost_model_service"].predict(request.get_json(silent=True)))


@intelligence_bp.post("/api/v1/ai/chat")
def ai_chat():
    return _ok(current_app.extensions["ai_assistant_service"].chat(request.get_json(silent=True)))
