"""Read-only routes for the complete analytics product."""

from __future__ import annotations

from collections.abc import Iterable

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.exceptions import MethodNotAllowed

from ..errors import InvalidRequestError, ResultNotReadyError
from .parameters import (
    query_value,
    reject_unknown_query_parameters,
    request_has_body,
    validate_option,
)


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
COST_FILTER_PARAMETERS = frozenset({"diagnosis_code", "facility_id", "severity"})
COST_ENTITY_DIMENSIONS = (
    ("diagnosis_code", "diagnosis"),
    ("facility_id", "facility"),
    ("severity", "severity"),
)
RISK_FILTER_PARAMETERS = frozenset({"age_group", "diagnosis_code"})
RISK_BASE_ENTITY = "age=*|diagnosis=*"
RISK_ENTITY_DIMENSIONS = (
    ("age_group", "age"),
    ("diagnosis_code", "diagnosis"),
)


def _ok(data: dict):
    return jsonify(
        {"code": "OK", "message": "success", "data": data, "trace_id": g.trace_id}
    )


@analytics_bp.before_request
def enforce_read_only_request() -> None:
    """Keep all analytics snapshot endpoints strictly GET-only."""

    if request.method != "GET":
        raise MethodNotAllowed(valid_methods=["GET"])
    if request_has_body():
        raise InvalidRequestError(
            "INVALID_REQUEST_FORMAT",
            "These read-only endpoints do not accept a request body.",
        )


def _reject_unknown(allowed: Iterable[str]) -> None:
    reject_unknown_query_parameters(allowed)


def _get(module: str, entity: str):
    return current_app.extensions["analytics_snapshot_service"].get(module, entity)


def _empty_result(base: dict, filters: dict[str, str]) -> dict:
    """Build a valid empty response from a published base snapshot."""

    result = dict(base)
    result["filters"] = dict(filters)
    result["metrics"] = []
    result["sections"] = []
    return result


def _get_or_empty(
    module: str,
    entity: str,
    base: dict,
    filters: dict[str, str],
) -> dict:
    try:
        return _get(module, entity)
    except ResultNotReadyError:
        # A known enum value with no published aggregate is a legal empty
        # result. A missing base snapshot is still a dependency error because
        # there is no metadata from which to form a stable response.
        return _empty_result(base, filters)


def _validate_option(
    parameter_name: str,
    value: str | None,
    payload: dict,
    *,
    option_name: str | None = None,
) -> None:
    validate_option(parameter_name, value, payload, option_name=option_name)


def _validate_metric(value: str | None) -> None:
    if value is not None and value not in HOSPITAL_METRIC_KEYS:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "The metric value is not supported.",
            {"parameter": "metric"},
        )


@analytics_bp.get("/api/v1/dashboard/overview")
def dashboard_overview():
    _reject_unknown(set())
    return _ok(_get("dashboard", "overview"))


@analytics_bp.get("/api/v1/hospitals")
def hospitals_index():
    _reject_unknown({"facility_a", "facility_b", "metric"})
    payload = _get("hospitals", "index")
    facility_a = query_value("facility_a")
    facility_b = query_value("facility_b")
    metric = query_value("metric")
    _validate_option("facility_a", facility_a, payload, option_name="facilities")
    _validate_option("facility_b", facility_b, payload, option_name="facilities")
    _validate_metric(metric)

    if facility_a and facility_a == facility_b:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "facility_a and facility_b must identify different facilities.",
            {"parameters": ["facility_a", "facility_b"]},
        )

    filters = {
        name: value
        for name, value in (
            ("facility_a", facility_a),
            ("facility_b", facility_b),
            ("metric", metric),
        )
        if value is not None
    }
    if not filters:
        return _ok(payload)

    profiles = []
    for facility_id in filter(None, (facility_a, facility_b)):
        try:
            profiles.append(_get("hospitals", f"profile:{facility_id}"))
        except ResultNotReadyError:
            # A valid facility can be enumerated before its profile is
            # published. The index remains a legal empty filter result.
            return _ok(
                {
                    **_empty_result(payload, filters),
                    "comparison": [],
                }
            )

    result = {**payload, "filters": filters}
    if profiles:
        # Comparison is response-only composition of complete snapshots;
        # metrics, ordering, units, and null semantics stay in the snapshots.
        result["comparison"] = profiles
    return _ok(result)


@analytics_bp.get("/api/v1/hospitals/<facility_id>")
def hospital_profile(facility_id: str):
    _reject_unknown(set())
    index = _get("hospitals", "index")
    _validate_option("facility_id", facility_id, index, option_name="facilities")
    return _ok(
        _get_or_empty(
            "hospitals",
            f"profile:{facility_id}",
            index,
            {"facility_id": facility_id},
        )
    )


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
    _validate_option(
        "diagnosis_code", diagnosis_code, index, option_name="diagnoses"
    )
    return _ok(
        _get_or_empty(
            "diseases",
            f"profile:{diagnosis_code}",
            index,
            {"diagnosis_code": diagnosis_code},
        )
    )


def _filtered_snapshot(
    module: str,
    base_entity: str,
    dimensions: tuple[tuple[str, str, str], ...],
):
    # Each dimension maps a query parameter and published option to a frozen
    # entity-key segment. The tuple order is server-owned.
    base = _get(module, base_entity)
    values = {parameter: query_value(parameter) for parameter, _, _ in dimensions}
    for parameter, option_name, _ in dimensions:
        _validate_option(parameter, values[parameter], base, option_name=option_name)
    selected = {
        parameter: value
        for parameter, value in values.items()
        if value is not None
    }
    if not selected:
        return base
    entity = "|".join(
        f"{entity_name}={selected.get(parameter, '*')}"
        for parameter, _, entity_name in dimensions
    )
    return _get_or_empty(module, entity, base, selected)


@analytics_bp.get("/api/v1/cohorts/summary")
def cohort_summary():
    dimensions = (
        ("age_group", "age_group", "age"),
        ("gender", "gender", "gender"),
        ("admission_type", "admission_type", "admission"),
    )
    _reject_unknown({parameter for parameter, _, _ in dimensions})
    return _ok(
        _filtered_snapshot(
            "cohorts",
            "age=*|gender=*|admission=*",
            dimensions,
        )
    )


@analytics_bp.get("/api/v1/costs/overview")
def cost_overview():
    _reject_unknown(COST_FILTER_PARAMETERS)
    diagnosis_code = query_value("diagnosis_code")
    facility_id = query_value("facility_id")
    severity = query_value("severity")
    if diagnosis_code is not None and facility_id is not None:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "diagnosis_code and facility_id are mutually exclusive.",
            {"parameters": ["diagnosis_code", "facility_id"]},
        )
    # Full whitelists are published by the disease and hospital modules.
    if diagnosis_code is not None:
        _validate_option(
            "diagnosis_code",
            diagnosis_code,
            _get("diseases", "index"),
            option_name="diagnoses",
        )
    if facility_id is not None:
        _validate_option(
            "facility_id",
            facility_id,
            _get("hospitals", "index"),
            option_name="facilities",
        )
    base = _get("costs", "diagnosis=*|facility=*|severity=*")
    _validate_option("severity", severity, base)
    selected = {
        parameter: value
        for parameter, value in (
            (parameter, query_value(parameter))
            for parameter, _ in COST_ENTITY_DIMENSIONS
        )
        if value is not None
    }
    if not selected:
        return _ok(base)
    entity = "|".join(
        f"{entity_name}={selected.get(parameter, '*')}"
        for parameter, entity_name in COST_ENTITY_DIMENSIONS
    )
    return _ok(_get_or_empty("costs", entity, base, selected))


@analytics_bp.get("/api/v1/risks/overview")
def risk_overview():
    _reject_unknown(RISK_FILTER_PARAMETERS)
    age_group = query_value("age_group")
    diagnosis_code = query_value("diagnosis_code")
    if diagnosis_code is not None:
        _validate_option(
            "diagnosis_code",
            diagnosis_code,
            _get("diseases", "index"),
            option_name="diagnoses",
        )
    base = _get("risks", RISK_BASE_ENTITY)
    _validate_option("age_group", age_group, base)
    selected = {
        name: value
        for name, value in (
            ("age_group", age_group),
            ("diagnosis_code", diagnosis_code),
        )
        if value is not None
    }
    if not selected:
        return _ok(base)
    entity = "|".join(
        f"{entity_name}={selected.get(parameter, '*')}"
        for parameter, entity_name in RISK_ENTITY_DIMENSIONS
    )
    return _ok(_get_or_empty("risks", entity, base, selected))


@analytics_bp.get("/api/v1/payments/overview")
def payment_overview():
    dimensions = (
        ("payment_type", "payment_type", "payment"),
        ("age_group", "age_group", "age"),
    )
    _reject_unknown({parameter for parameter, _, _ in dimensions})
    return _ok(
        _filtered_snapshot(
            "payments",
            "payment=*|age=*",
            dimensions,
        )
    )


@analytics_bp.get("/api/v1/data-quality/summary")
def data_quality_summary():
    _reject_unknown({"data_version"})
    payload = _get("data_quality", "summary")
    requested = query_value("data_version")
    if requested is not None and requested != payload["data_version"]:
        raise InvalidRequestError(
            "INVALID_QUERY_PARAMETER",
            "The data_version is not available.",
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
