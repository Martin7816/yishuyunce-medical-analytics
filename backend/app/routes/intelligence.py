"""High-cost prediction and AI assistant routes."""

import json

from flask import Blueprint, Response, current_app, g, jsonify, request, stream_with_context

from ..errors import AppError


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


@intelligence_bp.route("/api/v1/ai/chat", methods=["POST"], provide_automatic_options=False)
def ai_chat():
    return _ok(current_app.extensions["ai_assistant_service"].chat(request.get_json(silent=True)))


def _sse(event_type: str, data: dict) -> str:
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


@intelligence_bp.route("/api/v1/ai/chat/stream", methods=["POST"], provide_automatic_options=False)
def ai_chat_stream():
    service = current_app.extensions["ai_assistant_service"]
    payload = request.get_json(silent=True)
    service.validate_document(payload)

    def generate():
        try:
            for event_type, data in service.stream_chat(payload):
                yield _sse(event_type, data)
        except GeneratorExit:
            return
        except (BrokenPipeError, ConnectionError, OSError):
            # The browser may have stopped generation or left the page. Closing
            # the generator also closes the upstream response context.
            return
        except AppError as error:
            yield _sse(
                "error",
                {"code": error.code, "message": error.message, "trace_id": g.trace_id},
            )
        except Exception:
            current_app.logger.exception("Unhandled AI stream error trace_id=%s", g.trace_id)
            yield _sse(
                "error",
                {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred.",
                    "trace_id": g.trace_id,
                },
            )

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
