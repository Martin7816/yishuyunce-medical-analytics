"""Flask application factory for the M1 read-only API."""

from __future__ import annotations

import logging
import uuid

from flask import Flask, g, jsonify
from werkzeug.exceptions import HTTPException

from .config import Config
from .errors import AppError
from .repositories.disease_top10 import build_repository
from .routes.diseases import diseases_bp
from .routes.health import health_bp
from .services.disease_top10 import DiseaseTop10Service


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


def create_app(config_override: dict | None = None, repository=None) -> Flask:
    """Create an application. Tests may inject a repository explicitly."""

    app = Flask(__name__)
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    selected_repository = repository or build_repository(app.config)
    app.extensions["disease_top10_service"] = DiseaseTop10Service(
        selected_repository
    )

    app.register_blueprint(health_bp)
    app.register_blueprint(diseases_bp)

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
