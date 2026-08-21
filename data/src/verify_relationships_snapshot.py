"""Independently verify the three bounded relation sections.

The production job uses PySpark cubes over one cached cleaning frame.  This
checker streams the source CSV with the standard library and recomputes only
the published aggregates: facility points, age/severity cells, and the fixed
length-of-stay bins.  It never imports the production aggregation functions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analytics_metadata import build_data_version, sha256_file  # noqa: E402
from shared.analytics_snapshot_contract import (  # noqa: E402
    validate_snapshot_document,
)


FIELD = {
    "year": "Discharge Year",
    "diagnosis": "CCSR Diagnosis Description",
    "diagnosis_code": "CCSR Diagnosis Code",
    "age": "Age Group",
    "los": "Length of Stay",
    "charges": "Total Charges",
    "costs": "Total Costs",
    "facility": "Facility Name",
    "severity": "APR Severity of Illness Description",
}
FACILITY_ID_FIELDS = ("Permanent Facility Id", "Facility ID")
SEVERITIES = ("Minor", "Moderate", "Major", "Extreme")
HIGH_RISK = {"Major", "Extreme"}
MISSING_GROUP = "未分类"
LOS_BINS = (
    ("0-1天", 0, 2),
    ("2-3天", 2, 4),
    ("4-6天", 4, 7),
    ("7-13天", 7, 14),
    ("14-29天", 14, 30),
    ("30-59天", 30, 60),
    ("60-119天", 60, 120),
    ("120天及以上", 120, None),
)
LOS_ORDER = {label: index for index, (label, _, _) in enumerate(LOS_BINS)}
GROUP_ORDER = {value: index for index, value in enumerate((*SEVERITIES, MISSING_GROUP))}
WILDCARD = (None, None, None)


def text(row: dict[str, str | None], name: str) -> str:
    fields = FACILITY_ID_FIELDS if name == "facility_id" else (FIELD[name],)
    for field in fields:
        value = row.get(field)
        if value is not None:
            return value.strip()
    return ""


def parse_los(value: str) -> int | None:
    if not value:
        return None
    if value == "120 +":
        return 120
    try:
        return int(value)
    except ValueError:
        return None


def parse_money(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None
    if parsed < 0:
        return None
    return float(parsed)


def rounded(value: float | int | None) -> float:
    return 0.0 if value is None else round(float(value), 2)


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def los_bin(los: int) -> str | None:
    for label, lower, upper in LOS_BINS:
        if los >= lower and (upper is None or los < upper):
            return label
    return None


def relation_bucket() -> dict[str, float | int]:
    return {"count": 0, "los": 0.0, "charges": 0.0, "costs": 0.0, "high": 0}


def add_relation(
    bucket: dict[str, float | int],
    *,
    los: int,
    charges: float,
    costs: float,
    high_cost_threshold: float,
) -> None:
    bucket["count"] += 1
    bucket["los"] += los
    bucket["charges"] += charges
    bucket["costs"] += costs
    bucket["high"] += charges >= high_cost_threshold


def percentile_nearest(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return rounded(ordered[index])


def cost_keys(
    diagnosis_code: str | None,
    facility_id: str | None,
    severity: str | None,
) -> set[tuple[str | None, str | None, str | None]]:
    keys = {WILDCARD}
    if diagnosis_code:
        keys.add((diagnosis_code, None, None))
    if facility_id:
        keys.add((None, facility_id, None))
    if severity:
        keys.add((None, None, severity))
    if diagnosis_code and severity:
        keys.add((diagnosis_code, None, severity))
    if facility_id and severity:
        keys.add((None, facility_id, severity))
    return keys


def scan_source(
    input_path: Path,
    high_cost_threshold: float,
) -> tuple[dict[str, Any], int, int, list[float]]:
    facilities: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "label": "",
            "count": 0,
            "los": 0.0,
            "charges": 0.0,
            "severe": 0,
            "severity_valid": 0,
        }
    )
    risk_matrix: dict[tuple[str | None, str | None, str, str], dict[str, int]] = defaultdict(
        lambda: {"count": 0, "high": 0}
    )
    cost_relation: dict[
        tuple[str | None, str | None, str | None],
        dict[tuple[str, str], dict[str, float | int]],
    ] = defaultdict(lambda: defaultdict(relation_bucket))
    facility_options: dict[str, str] = {}
    facility_case_counts: dict[str, int] = defaultdict(int)
    age_options: set[str] = set()
    diagnosis_options: set[str] = set()
    charges_values: list[float] = []
    raw_rows = 0
    scoped_rows = 0

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_rows += 1
            if row.get(None) is not None:
                raise AssertionError(f"CSV 存在结构异常行: {raw_rows}")
            if text(row, "year") != "2021":
                continue
            los = parse_los(text(row, "los"))
            if los is None:
                continue
            scoped_rows += 1
            age = text(row, "age") or None
            diagnosis = text(row, "diagnosis")
            diagnosis_code = text(row, "diagnosis_code") or None
            facility_id = text(row, "facility_id") or None
            facility = text(row, "facility")
            severity = text(row, "severity") or None
            if age:
                age_options.add(age)
            if diagnosis and diagnosis_code:
                diagnosis_options.add(diagnosis_code)
            if facility_id:
                facility_case_counts[facility_id] += 1
                facility_options[facility_id] = min(
                    value for value in (facility_options.get(facility_id, facility), facility) if value
                )

            if age and severity in SEVERITIES:
                risk_keys = {(None, None), (age, None)}
                if diagnosis_code:
                    risk_keys.add((None, diagnosis_code))
                    risk_keys.add((age, diagnosis_code))
                for filter_key in risk_keys:
                    cell = risk_matrix[(filter_key[0], filter_key[1], age, severity)]
                    cell["count"] += 1
                    cell["high"] += severity in HIGH_RISK

            charges = parse_money(text(row, "charges"))
            costs = parse_money(text(row, "costs"))
            if charges is None or costs is None or los < 0:
                continue
            charges_values.append(charges)
            if facility_id:
                bucket = facilities[facility_id]
                bucket["label"] = min(
                    value
                    for value in (bucket["label"], facility)
                    if value
                ) if bucket["label"] or facility else ""
                bucket["count"] += 1
                bucket["los"] += los
                bucket["charges"] += charges
                bucket["severe"] += severity in HIGH_RISK
                bucket["severity_valid"] += severity in SEVERITIES
            bin_label = los_bin(los)
            if bin_label is None:
                continue
            group = severity if severity in SEVERITIES else MISSING_GROUP
            for key in cost_keys(diagnosis_code, facility_id, severity):
                add_relation(
                    cost_relation[key][(bin_label, group)],
                    los=los,
                    charges=charges,
                    costs=costs,
                    high_cost_threshold=high_cost_threshold,
                )

    return (
        {
            "facilities": facilities,
            "facility_options": facility_options,
            "facility_case_counts": facility_case_counts,
            "risk_matrix": risk_matrix,
            "cost_relation": cost_relation,
            "age_options": sorted(age_options),
            "diagnosis_options": sorted(diagnosis_options),
        },
        raw_rows,
        scoped_rows,
        charges_values,
    )


def metric_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {item["key"]: item["value"] for item in payload.get("metrics", [])}


def sections_by_key(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in payload.get("sections", [])}


def close_enough(actual: Any, expected: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=1e-7, abs_tol=0.01)
    return actual == expected


def compare(
    input_path: Path,
    snapshot: dict[str, Any],
    expected: dict[str, Any],
    raw_rows: int,
    scoped_rows: int,
    charges_values: list[float],
) -> dict[str, Any]:
    validate_snapshot_document(snapshot)
    digest = sha256_file(input_path)
    if snapshot["input"].get("sha256") != digest:
        raise AssertionError("快照输入 SHA-256 不一致")
    if snapshot["input"].get("raw_rows") != raw_rows:
        raise AssertionError("快照原始记录数不一致")
    if snapshot["data_version"] != build_data_version(input_path, digest):
        raise AssertionError("快照 data_version 不一致")

    computed_threshold = percentile_nearest(charges_values, 0.75) if charges_values else 0.0
    costs_record = next(
        record
        for record in snapshot["records"]
        if record["module_key"] == "costs"
        and record["entity_key"] == "diagnosis=*|facility=*|severity=*"
    )
    costs_metrics = metric_values(costs_record["payload"])
    if not math.isclose(computed_threshold, float(costs_metrics["p75_charges"]), rel_tol=0.001, abs_tol=0.01):
        raise AssertionError(
            f"收费 P75 不一致: expected={computed_threshold!r}, actual={costs_metrics['p75_charges']!r}"
        )

    hospitals_index = next(
        record
        for record in snapshot["records"]
        if record["module_key"] == "hospitals" and record["entity_key"] == "index"
    )
    relation = sections_by_key(hospitals_index["payload"])["facility_relation"]
    relation_items = []
    for facility_id, aggregate in sorted(
        expected["facilities"].items(),
        key=lambda item: (-item[1]["count"], item[0]),
    )[:50]:
        relation_items.append(
            {
                "name": aggregate["label"] or facility_id,
                "x": rounded(aggregate["los"] / aggregate["count"]),
                "y": rounded(aggregate["charges"] / aggregate["count"]),
                "size": aggregate["count"],
                "group": rate(aggregate["severe"], aggregate["severity_valid"]),
            }
        )
    if relation["items"] != relation_items:
        raise AssertionError("医院关系散点与独立核对不一致")

    grouped = sections_by_key(hospitals_index["payload"])["facility_metric_comparison"]
    first_two = sorted(expected["facility_options"])[:2]
    grouped_series = [
        {"key": f"facility_{index + 1}", "label": expected["facility_options"][facility_id], "value": expected["facility_case_counts"][facility_id]}
        for index, facility_id in enumerate(first_two)
    ]
    if grouped["items"] != ([{"category": "病例量", "series": grouped_series}] if grouped_series else []):
        raise AssertionError("医院 grouped_bar 与独立核对不一致")

    cost_relation = sections_by_key(costs_record["payload"])["cost_los_relation"]
    wanted_cost_items = []
    for (bin_label, group), aggregate in expected["cost_relation"][WILDCARD].items():
        count = int(aggregate["count"])
        wanted_cost_items.append(
            {
                "name": f"{bin_label} · {group}",
                "x": rounded(float(aggregate["los"]) / count),
                "y": rounded(float(aggregate["charges"]) / count),
                "size": count,
                "group": group,
                "cost": rounded(float(aggregate["costs"]) / count),
                "high_cost_rate": rate(int(aggregate["high"]), count),
            }
        )
    wanted_cost_items.sort(
        key=lambda item: (
            LOS_ORDER[item["name"].split(" · ", 1)[0]],
            GROUP_ORDER[item["group"]],
        )
    )
    if cost_relation["items"] != wanted_cost_items:
        raise AssertionError("费用×住院时长关系与独立核对不一致")

    risks = {
        record["entity_key"]: record
        for record in snapshot["records"]
        if record["module_key"] == "risks"
    }
    matrix_checked = 0
    for entity, record in risks.items():
        age_filter, diagnosis_filter = (
            segment.split("=", 1)[1]
            for segment in entity.split("|")
        )
        age_filter = None if age_filter == "*" else age_filter
        diagnosis_filter = None if diagnosis_filter == "*" else diagnosis_filter
        payload = record["payload"]
        if not payload.get("metrics"):
            continue
        matrix = sections_by_key(payload)["age_severity_matrix"]
        ages = [age_filter] if age_filter is not None else expected["age_options"]
        wanted = []
        for age in ages:
            for severity in SEVERITIES:
                aggregate = expected["risk_matrix"].get(
                    (age_filter, diagnosis_filter, age, severity), {"count": 0, "high": 0}
                )
                count = aggregate["count"]
                high = aggregate["high"]
                wanted.append(
                    {
                        "x_label": age,
                        "y_label": severity,
                        "value": count,
                        "unit": "条",
                        "numerator": high,
                        "denominator": count,
                        "high_risk_rate": rate(high, count),
                    }
                )
        if matrix["items"] != wanted:
            raise AssertionError(f"风险热力矩阵与独立核对不一致: {entity}")
        matrix_checked += 1

    return {
        "status": "PASS",
        "module": "relations",
        "raw_rows": raw_rows,
        "scoped_rows": scoped_rows,
        "facility_points": len(relation_items),
        "cost_points": len(wanted_cost_items),
        "risk_matrices": matrix_checked,
        "data_version": snapshot["data_version"],
        "generated_at": snapshot["generated_at"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    cost_record = next(
        record
        for record in snapshot["records"]
        if record["module_key"] == "costs"
        and record["entity_key"] == "diagnosis=*|facility=*|severity=*"
    )
    threshold = float(metric_values(cost_record["payload"])["p75_charges"])
    expected, raw_rows, scoped_rows, charges_values = scan_source(args.input, threshold)
    print(
        json.dumps(
            compare(args.input, snapshot, expected, raw_rows, scoped_rows, charges_values),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
