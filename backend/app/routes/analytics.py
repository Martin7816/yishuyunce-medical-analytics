"""Read-only routes for the complete analytics product."""

from __future__ import annotations

import math
from copy import deepcopy
from collections.abc import Iterable

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.exceptions import MethodNotAllowed

from ..errors import InvalidRequestError, InvalidServiceResultError, ResultNotReadyError
from ..services.high_cost_model import FEATURES
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


def _required_section(payload: dict, key: str) -> dict:
    section = next(
        (item for item in payload.get("sections", []) if item.get("key") == key),
        None,
    )
    if section is None:
        raise InvalidServiceResultError()
    return deepcopy(section)


def _require_one_snapshot_version(payloads: list[dict]) -> tuple[str, str]:
    versions = {payload.get("data_version") for payload in payloads}
    timestamps = {payload.get("generated_at") for payload in payloads}
    if len(versions) != 1 or len(timestamps) != 1 or None in versions or None in timestamps:
        raise InvalidServiceResultError()
    return versions.pop(), timestamps.pop()


def _empty_result(base: dict, filters: dict[str, str]) -> dict:
    """Build a valid empty response from a published base snapshot."""

    result = dict(base)
    result["filters"] = dict(filters)
    result["metrics"] = []
    result["sections"] = []
    if "insights" in result:
        result["insights"] = []
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


def _hospital_comparison_section(
    profiles: list[dict], metric_key: str
) -> tuple[dict, dict]:
    """Compose a finite grouped bar from already-published profile metrics."""

    metric_items = []
    legend = []
    for index, profile in enumerate(profiles):
        item = next(
            (value for value in profile.get("metrics", []) if value.get("key") == metric_key),
            None,
        )
        if item is None:
            raise InvalidServiceResultError()
        series_key = f"facility_{index + 1}"
        metric_items.append(
            {
                "key": series_key,
                "label": profile["title"],
                "value": item["value"],
            }
        )
        legend.append({"key": series_key, "label": profile["title"], "style": "solid"})

    version = profiles[0]["data_version"]
    generated_at = profiles[0]["generated_at"]
    label = next(
        value["label"]
        for value in profiles[0].get("metrics", [])
        if value.get("key") == metric_key
    )
    unit = next(
        value["unit"]
        for value in profiles[0].get("metrics", [])
        if value.get("key") == metric_key
    )
    section_key = "facility_metric_comparison"
    summary = {
        "text": f"选定医疗机构的{label}来自已发布画像，用于并列比较；不表达机构导致结果。",
        "source_metric_keys": [metric_key],
        "source_section": section_key,
        "data_version": version,
        "generated_at": generated_at,
        "boundary": "选定医疗机构的已发布住院出院记录汇总",
        "related_not_causal": True,
    }
    section = {
        "key": section_key,
        "title": f"选定医疗机构的{label}对照",
        "type": "grouped_bar",
        "visual": {
            "question": f"选定医疗机构的{label}如何对照？",
            "x_label": "医疗机构",
            "y_label": f"{label}（{unit}）",
            "unit": unit,
            "legend": legend,
            "tooltip_fields": ["category", "series_label", "value", "unit"],
            "summary": summary,
            "fallback": {"type": "table", "columns": ["category", "series_label", "value", "unit"]},
            "empty": {"title": "暂无机构对照数据", "text": "请调整已发布的医疗机构筛选。"},
        },
        "items": [{"category": label, "series": metric_items}],
    }
    insight = {
        "key": "facility_metric_comparison",
        "title": f"{label}对照",
        "summary": summary["text"],
        "level": "info",
        "source_section": section_key,
        "source_metric_keys": [metric_key],
        "data_version": version,
        "generated_at": generated_at,
        "boundary": summary["boundary"],
        "related_not_causal": True,
    }
    return section, insight


@analytics_bp.get("/api/v1/dashboard/overview")
def dashboard_overview():
    _reject_unknown(set())
    return _ok(_get("dashboard", "overview"))


@analytics_bp.get("/api/v1/dashboard/screen")
def dashboard_screen():
    """Compose one atomic operating story from already-published snapshots."""

    _reject_unknown(set())
    overview = _get("dashboard", "overview")
    hospitals = _get("hospitals", "index")
    diseases = _get("diseases", "index")
    costs = _get("costs", "diagnosis=*|facility=*|severity=*")
    risks = _get("risks", RISK_BASE_ENTITY)
    quality = _get("data_quality", "summary")
    data_version, generated_at = _require_one_snapshot_version(
        [overview, hospitals, diseases, costs, risks, quality]
    )

    payment = _required_section(overview, "payment")
    payment["type"] = "pie"
    storage = _required_section(quality, "storage")
    storage_statuses = {
        item.get("name"): item.get("value") for item in storage.get("items", [])
    }
    quality_status = storage_statuses.get("PySpark任务")
    if not isinstance(quality_status, str) or not quality_status:
        raise InvalidServiceResultError()
    facilities = hospitals.get("options", {}).get("facilities")
    diagnoses = diseases.get("options", {}).get("diagnoses")
    if not isinstance(facilities, list) or not isinstance(diagnoses, list):
        raise InvalidServiceResultError()

    sections = [
        _required_section(overview, "age"),
        payment,
        _required_section(overview, "disease_top10"),
        _required_section(overview, "hospital_top10"),
        _required_section(costs, "cost_los_relation"),
        _required_section(risks, "age_severity_matrix"),
        _required_section(costs, "continuous_correlations"),
        storage,
    ]
    included_keys = {section["key"] for section in sections}
    insights = [
        deepcopy(insight)
        for payload in (costs, risks)
        for insight in payload.get("insights", [])
        if insight.get("source_section") in included_keys
    ]
    return _ok(
        {
            "title": "医疗运营指挥中心",
            "description": (
                "从住院出院记录规模、费用、疾病、医院与严重程度结构观察运营全景。"
            ),
            "options": {
                "quality_status": quality_status,
                "facilities": deepcopy(facilities),
                "diagnoses": deepcopy(diagnoses),
            },
            "metrics": deepcopy(overview.get("metrics", [])),
            "sections": sections,
            "insights": insights,
            "data_version": data_version,
            "generated_at": generated_at,
        }
    )


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
        comparison_section, comparison_insight = _hospital_comparison_section(
            profiles, metric or "case_count"
        )
        result["sections"] = [
            section
            for section in result.get("sections", [])
            if section.get("key") != "facility_metric_comparison"
        ] + [comparison_section]
        result["insights"] = [
            insight
            for insight in result.get("insights", [])
            if insight.get("key") != "facility_metric_comparison"
        ] + [comparison_insight]
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
    if (
        not isinstance(metadata, dict)
        or not isinstance(metadata.get("model_version"), str)
        or not metadata["model_version"].strip()
        or not isinstance(metadata.get("feature_names"), list)
        or metadata["feature_names"] != list(FEATURES)
        or not isinstance(metadata.get("threshold_amount"), (int, float))
        or isinstance(metadata["threshold_amount"], bool)
        or not math.isfinite(float(metadata["threshold_amount"]))
        or metadata["threshold_amount"] < 0
    ):
        raise InvalidServiceResultError()
    result = dict(payload)
    for name in ("model_version", "threshold_amount", "feature_names"):
        if name in metadata:
            result[name] = metadata[name]
    return _ok(result)
