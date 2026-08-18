"""Read-only routes for the complete analytics product."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.exceptions import MethodNotAllowed

from ..errors import InvalidRequestError, ResultNotReadyError


analytics_bp = Blueprint("analytics", __name__)
HOSPITAL_METRIC_KEYS = frozenset(
    {
        "case_count",
        "avg_los",
        "avg_charges",
        "avg_costs",
        "emergency_rate",
        "severe_rate",
    }
)


def _request_has_body() -> bool:
    """Detect GET bodies even when a client uses chunked transfer encoding."""

    if request.headers.get("Transfer-Encoding"):
        return True
    if request.content_length is not None:
        return request.content_length > 0
    if request.environ.get("wsgi.input_terminated"):
        return bool(request.get_data(cache=True))
    return False


@analytics_bp.before_request
def _enforce_get_only() -> None:
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
    repeated = sorted(name for name, values in request.args.lists() if len(values) > 1)
    if unknown or repeated:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "One or more query parameters are not supported.",
            {"parameters": sorted(set(unknown + repeated))},
        )


def _get(module: str, entity: str):
    return current_app.extensions["analytics_snapshot_service"].get(module, entity)


def _option_values(payload: dict, option: str) -> set[str]:
    raw = payload.get("options", {}).get(option, [])
    values = set()
    for item in raw:
        values.add(str(item.get("value")) if isinstance(item, dict) else str(item))
    return values


def _validate_option(
    parameter: str,
    value: str | None,
    payload: dict,
    *,
    option_name: str | None = None,
) -> None:
    option_name = option_name or parameter
    if value is not None and value not in _option_values(payload, option_name):
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            f"The {parameter} value is not supported.",
            {"parameter": parameter},
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
        _validate_option(
            name,
            request.args.get(name),
            payload,
            option_name="facilities",
        )
    metric = request.args.get("metric")
    if metric is not None and metric not in HOSPITAL_METRIC_KEYS:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER", "The metric value is not supported.",
            {"parameter": "metric"},
        )

    selected = [request.args.get("facility_a"), request.args.get("facility_b")]
    if selected[0] and selected[0] == selected[1]:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "facility_a and facility_b must identify different facilities.",
            {"parameters": ["facility_a", "facility_b"]},
        )

    filters = {
        name: request.args[name]
        for name in ("facility_a", "facility_b", "metric")
        if request.args.get(name)
    }
    profiles = []
    for facility_id in filter(None, selected):
        try:
            profiles.append(_get("hospitals", f"profile:{facility_id}"))
        except ResultNotReadyError:
            # A valid facility can be enumerated before its profile is
            # published. That is a legal empty filter result, not a module
            # outage; the index itself was already available above.
            empty = {
                **payload,
                "filters": filters,
                "metrics": [],
                "sections": [],
                "comparison": [],
            }
            return _ok(empty)

    if not filters:
        return _ok(payload)

    result = {**payload, "filters": filters}
    if profiles:
        # Comparison is a response-only composition of complete snapshots;
        # metrics, ordering, units, and null semantics stay in the snapshots.
        result["comparison"] = profiles
    return _ok(result)


@analytics_bp.get("/api/v1/hospitals/<facility_id>")
def hospital_profile(facility_id: str):
    _reject_unknown(set())
    index = _get("hospitals", "index")
    _validate_option("facility_id", facility_id, index, option_name="facilities")
    return _ok(_get("hospitals", f"profile:{facility_id}"))


@analytics_bp.get("/api/v1/diseases")
def diseases_index():
    _reject_unknown(set())
    return _ok(_get("diseases", "index"))


@analytics_bp.route(
    "/api/v1/diseases/<diagnosis_code>",
    methods=["GET"],
    provide_automatic_options=False,
)
def disease_profile(diagnosis_code: str):
    _reject_unknown(set())
    index = _get("diseases", "index")
    _validate_option("diagnoses", diagnosis_code, index)
    return _ok(_get("diseases", f"profile:{diagnosis_code}"))


def _filtered_snapshot(module: str, base_entity: str, options: dict[str, str]):
    base = _get(module, base_entity)
    for parameter, option_name in options.items():
        _validate_option(parameter, request.args.get(parameter), base, option_name=option_name)
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
        _validate_option(
            "diagnosis_code",
            request.args["diagnosis_code"],
            _get("diseases", "index"),
            option_name="diagnoses",
        )
    if request.args.get("facility_id"):
        _validate_option(
            "facility_id",
            request.args["facility_id"],
            _get("hospitals", "index"),
            option_name="facilities",
        )
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
        _validate_option(
            "diagnosis_code",
            request.args["diagnosis_code"],
            _get("diseases", "index"),
            option_name="diagnoses",
        )
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
