"""Read-only routes for the complete analytics product."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.exceptions import MethodNotAllowed
from werkzeug.exceptions import MethodNotAllowed

from ..errors import InvalidRequestError, ResultNotReadyError


analytics_bp = Blueprint("analytics", __name__)


def _request_has_body() -> bool:
    """Detect GET body data, including chunked requests without a length."""
    if request.headers.get("Transfer-Encoding"):
        return True
    if request.content_length is not None:
        return request.content_length > 0
    if request.environ.get("wsgi.input_terminated"):
        return bool(request.get_data(cache=True))
    return False


@analytics_bp.before_request
def enforce_read_only_request_contract() -> None:
    """Keep every analytics snapshot endpoint strictly GET-only."""
    # Flask adds HEAD and OPTIONS automatically to GET routes. They are not
    # part of the frozen API contract and must not execute a snapshot read.
    if request.method != "GET":
        raise MethodNotAllowed(valid_methods=["GET"])
    if _request_has_body():
        raise InvalidRequestError(
            "INVALID_REQUEST_FORMAT",
            "This GET endpoint does not accept a request body.",
        )


def _ok(data: dict):
    return jsonify(
        {"code": "OK", "message": "success", "data": data, "trace_id": g.trace_id}
    )


def _reject_unknown(allowed: set[str]) -> None:
    unknown = sorted(set(request.args) - allowed)
    if unknown:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "One or more query parameters are not supported.",
            {"parameters": unknown},
        )


def _request_has_body() -> bool:
    """Detect request data even when a client uses chunked transfer encoding."""

    if request.headers.get("Transfer-Encoding"):
        return True
    if request.content_length is not None:
        return request.content_length > 0
    if request.environ.get("wsgi.input_terminated"):
        return bool(request.get_data(cache=True))
    return False


def _reject_non_get_or_body() -> None:
    """Keep snapshot reads strictly GET-only and body-free."""

    if request.method != "GET":
        raise MethodNotAllowed(valid_methods=["GET"])
    if _request_has_body():
        raise InvalidRequestError(
            "INVALID_REQUEST_FORMAT",
            "This GET endpoint does not accept a request body.",
        )


def _get(module: str, entity: str):
    return current_app.extensions["analytics_snapshot_service"].get(module, entity)


def _option_values(payload: dict, option: str) -> set[str]:
    raw = payload.get("options", {}).get(option, [])
    values = set()
    for item in raw:
        values.add(str(item.get("value")) if isinstance(item, dict) else str(item))
    return values


def _validate_option(name: str, value: str | None, payload: dict) -> None:
    if value is not None and value not in _option_values(payload, name):
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            f"The {name} value is not supported.",
            {"parameter": name},
        )


@analytics_bp.get("/api/v1/dashboard/overview")
def dashboard_overview():
    _reject_unknown(set())
    return _ok(_get("dashboard", "overview"))


@analytics_bp.get("/api/v1/hospitals")
def hospitals_index():
    _reject_unknown({"facility_a", "facility_b", "metric"})
    payload = _get("hospitals", "index")
    for name in ("facility_a", "facility_b"):
        _validate_option("facilities", request.args.get(name), payload)
    metric = request.args.get("metric")
    allowed_metrics = {
        "case_count", "avg_los", "avg_charges", "avg_costs",
        "emergency_rate", "severe_rate",
    }
    if metric is not None and metric not in allowed_metrics:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER", "The metric value is not supported.",
            {"parameter": "metric"},
        )
    selected = [request.args.get("facility_a"), request.args.get("facility_b")]
    profiles = []
    for facility_id in filter(None, selected):
        profiles.append(_get("hospitals", f"profile:{facility_id}"))
    if profiles:
        payload["comparison"] = profiles
    return _ok(payload)


@analytics_bp.get("/api/v1/hospitals/<facility_id>")
def hospital_profile(facility_id: str):
    _reject_unknown(set())
    index = _get("hospitals", "index")
    _validate_option("facilities", facility_id, index)
    return _ok(_get("hospitals", f"profile:{facility_id}"))


@analytics_bp.route(
    "/api/v1/diseases",
    methods=["GET"],
    provide_automatic_options=False,
)
def diseases_index():
    _reject_non_get_or_body()
    _reject_unknown(set())
    return _ok(_get("diseases", "index"))


@analytics_bp.route(
    "/api/v1/diseases/<diagnosis_code>",
    methods=["GET"],
    provide_automatic_options=False,
)
def disease_profile(diagnosis_code: str):
    _reject_non_get_or_body()
    _reject_unknown(set())
    index = _get("diseases", "index")
    _validate_option("diagnoses", diagnosis_code, index)
    try:
        payload = _get("diseases", f"profile:{diagnosis_code}")
    except ResultNotReadyError:
        # The enum is published by the index, but this concrete profile may
        # still be absent while the data task is being published. Keep that
        # distinction as a legal 200 empty result; a missing index remains a
        # real RESULT_NOT_READY dependency failure.
        payload = dict(index)
        payload["filters"] = {"diagnosis_code": diagnosis_code}
        payload["metrics"] = []
        payload["sections"] = []
    return _ok(payload)


def _filtered_snapshot(module: str, base_entity: str, options: dict[str, str]):
    base = _get(module, base_entity)
    for parameter, option_name in options.items():
        _validate_option(option_name, request.args.get(parameter), base)
    selected = {key: value for key in options if (value := request.args.get(key))}
    if not selected:
        return base
    parts = []
    for parameter in options:
        value = selected.get(parameter, "*")
        parts.append(f"{parameter.replace('_group', '').replace('_type', '')}={value}")
    entity = "|".join(parts)
    try:
        return _get(module, entity)
    except ResultNotReadyError:
        # A valid filter without a published aggregate is a legal empty result.
        result = dict(base)
        result["filters"] = selected
        result["metrics"] = []
        result["sections"] = []
        return result


@analytics_bp.get("/api/v1/cohorts/summary")
def cohort_summary():
    allowed = {"age_group", "gender", "admission_type"}
    _reject_unknown(allowed)
    return _ok(
        _filtered_snapshot(
            "cohorts",
            "age=*|gender=*|admission=*",
            {"age_group": "age_group", "gender": "gender", "admission_type": "admission_type"},
        )
    )


@analytics_bp.get("/api/v1/costs/overview")
def cost_overview():
    allowed = {"diagnosis_code", "facility_id", "severity"}
    _reject_unknown(allowed)
    if request.args.get("diagnosis_code") and request.args.get("facility_id"):
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "diagnosis_code and facility_id are mutually exclusive.",
        )
    # Full whitelists are published by the disease and hospital modules.
    if request.args.get("diagnosis_code"):
        _validate_option("diagnoses", request.args["diagnosis_code"], _get("diseases", "index"))
    if request.args.get("facility_id"):
        _validate_option("facilities", request.args["facility_id"], _get("hospitals", "index"))
    base = _get("costs", "diagnosis=*|facility=*|severity=*")
    _validate_option("severity", request.args.get("severity"), base)
    selected = {
        name: request.args[name]
        for name in ("diagnosis_code", "facility_id", "severity")
        if request.args.get(name)
    }
    if not selected:
        return _ok(base)
    entity = "diagnosis={}|facility={}|severity={}".format(
        selected.get("diagnosis_code", "*"),
        selected.get("facility_id", "*"),
        selected.get("severity", "*"),
    )
    try:
        payload = _get("costs", entity)
    except ResultNotReadyError:
        payload = {**base, "filters": selected, "metrics": [], "sections": []}
    return _ok(payload)


@analytics_bp.get("/api/v1/risks/overview")
def risk_overview():
    allowed = {"age_group", "diagnosis_code"}
    _reject_unknown(allowed)
    if request.args.get("diagnosis_code"):
        _validate_option("diagnoses", request.args["diagnosis_code"], _get("diseases", "index"))
    base = _get("risks", "age=*|diagnosis=*")
    _validate_option("age_group", request.args.get("age_group"), base)
    selected = {
        name: request.args[name]
        for name in ("age_group", "diagnosis_code")
        if request.args.get(name)
    }
    if not selected:
        return _ok(base)
    entity = "age={}|diagnosis={}".format(
        selected.get("age_group", "*"), selected.get("diagnosis_code", "*")
    )
    try:
        payload = _get("risks", entity)
    except ResultNotReadyError:
        payload = {**base, "filters": selected, "metrics": [], "sections": []}
    return _ok(payload)


@analytics_bp.get("/api/v1/payments/overview")
def payment_overview():
    allowed = {"payment_type", "age_group"}
    _reject_unknown(allowed)
    return _ok(
        _filtered_snapshot(
            "payments", "payment=*|age=*", {"payment_type": "payment_type", "age_group": "age_group"}
        )
    )


@analytics_bp.get("/api/v1/data-quality/summary")
def data_quality_summary():
    _reject_unknown({"data_version"})
    payload = _get("data_quality", "summary")
    requested = request.args.get("data_version")
    if requested and requested != payload["data_version"]:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER", "The data_version is not available.",
            {"parameter": "data_version"},
        )
    return _ok(payload)


@analytics_bp.get("/api/v1/models/high-cost/metrics")
def high_cost_metrics():
    _reject_unknown(set())
    payload = _get("high_cost_model", "metrics")
    # Model metadata lives under the snapshot's allowed `options` object;
    # expose the established response shape without widening payload_json.
    metadata = payload.get("options", {})
    result = dict(payload)
    for name in ("model_version", "threshold_amount", "feature_names"):
        if name in metadata:
            result[name] = metadata[name]
    return _ok(result)
