"""Flask application factory for the M1 read-only API."""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

from flask import Flask, g, jsonify
from werkzeug.exceptions import HTTPException


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from .config import Config
from .errors import AppError
from .repositories.disease_top10 import build_repository
from .repositories.analytics_snapshot import build_analytics_repository
from .routes.analytics import analytics_bp
from .routes.diseases import diseases_bp
from .routes.health import health_bp
from .routes.intelligence import intelligence_bp
from .services.ai_assistant import AIAssistantService, DeepSeekChatClient
from .services.disease_top10 import DiseaseTop10Service
from .services.analytics_snapshot import AnalyticsSnapshotService
from .services.high_cost_model import HighCostModelService


def _error_payload(error: AppError) -> dict:
    payload = {
        "code": error.code,
        "message": error.message,
        "data": None,
        "trace_id": g.trace_id,
    }
    if error.details is not None:
        payload["details"] = error.details
    return payload


def create_app(
    config_override: dict | None = None,
    repository=None,
    analytics_repository=None,
    high_cost_model_service=None,
    ai_client=None,
) -> Flask:
    """Create an application. Tests may inject a repository explicitly."""

    app = Flask(__name__)
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    selected_repository = (
        repository if repository is not None else build_repository(app.config)
    )
    app.extensions["disease_top10_service"] = DiseaseTop10Service(
        selected_repository
    )
    selected_analytics_repository = (
        analytics_repository
        if analytics_repository is not None
        else build_analytics_repository(app.config)
    )
    app.extensions["analytics_snapshot_service"] = AnalyticsSnapshotService(
        selected_analytics_repository
    )
    model_path = app.config.get("HIGH_COST_MODEL_PATH")
    if not model_path and app.config.get("ANALYTICS_DATA_SOURCE") == "fixture":
        model_path = app.config["APP_ROOT"] / "fixtures" / "high_cost_model.json"
    app.extensions["high_cost_model_service"] = (
        high_cost_model_service
        if high_cost_model_service is not None
        else HighCostModelService(model_path)
    )
    selected_ai_client = (
        ai_client
        if ai_client is not None
        else DeepSeekChatClient(
            app.config.get("DEEPSEEK_API_KEY"),
            app.config["DEEPSEEK_BASE_URL"],
            app.config["DEEPSEEK_MODEL"],
            app.config["DEEPSEEK_TIMEOUT_SECONDS"],
        )
    )
    app.extensions["ai_assistant_service"] = AIAssistantService(
        app.extensions["analytics_snapshot_service"], selected_ai_client
    )

    app.register_blueprint(health_bp)
    app.register_blueprint(diseases_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(intelligence_bp)

    @app.before_request
    def assign_trace_id() -> None:
        g.trace_id = str(uuid.uuid4())

    @app.after_request
    def attach_trace_id(response):
        response.headers["X-Trace-ID"] = g.trace_id
        return response

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify(_error_payload(error)), error.status_code

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        code_by_status = {
            400: "INVALID_REQUEST_FORMAT",
            404: "RESOURCE_NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
        }
        public_message_by_status = {
            400: "The request format is invalid.",
            404: "The requested resource does not exist.",
            405: "The HTTP method is not allowed for this endpoint.",
        }
        app_error = AppError(
            status_code=error.code or 500,
            code=code_by_status.get(error.code, "HTTP_ERROR"),
            message=public_message_by_status.get(
                error.code, "The request could not be processed."
            ),
        )
        return jsonify(_error_payload(app_error)), app_error.status_code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.error(
            "Unhandled API error trace_id=%s",
            g.trace_id,
            exc_info=error,
        )
        app_error = AppError(
            status_code=500,
            code="INTERNAL_ERROR",
            message="An internal error occurred.",
        )
        return jsonify(_error_payload(app_error)), 500

    if not app.debug:
        logging.basicConfig(level=logging.INFO)

    return app
