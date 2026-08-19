"""Independently verify the ``costs`` snapshot with the standard library.

The production job computes the legal filter matrix with a PySpark cube.  This
checker streams the CSV once, uses Decimal arithmetic for means and ratios, and
uses a small exact value list only for the wildcard quantiles.  It therefore
checks the public result without importing or calling the PySpark aggregation
implementation.
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
    "los": "Length of Stay",
    "charges": "Total Charges",
    "costs": "Total Costs",
    "facility": "Facility Name",
    "facility_id": ("Permanent Facility Id", "Facility ID"),
    "severity": "APR Severity of Illness Description",
}
COST_FIELDS = ("diagnosis_code", "facility_id", "severity")
WILDCARD = (None, None, None)
QUANTILES = (("p25", 0.25), ("p50", 0.5), ("p75", 0.75), ("p90", 0.9))
QUANTILE_RELATIVE_TOLERANCE = 0.001


def text(row: dict[str, str | None], name: str) -> str:
    field = FIELD[name]
    candidates = field if isinstance(field, tuple) else (field,)
    for candidate in candidates:
        value = row.get(candidate)
        if value is not None:
            return value.strip()
    return ""


def length_of_stay(value: str) -> int | None:
    if not value:
        return None
    if value == "120 +":
        return 120
    try:
        return int(value)
    except ValueError:
        return None


def nonnegative_decimal(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        parsed = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None
    return parsed if parsed >= 0 else None


def rounded(value: Decimal | float | int | None) -> float:
    return 0.0 if value is None else round(float(value), 2)


def percentile_approx(values: list[float], percentile: float) -> float:
    """Match the nearest-rank result for the small exact verifier sample."""

    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 2)


def empty_summary() -> dict[str, Any]:
    return {
        "count": 0,
        "charges_sum": Decimal("0"),
        "costs_sum": Decimal("0"),
        "gap_sum": Decimal("0"),
        "daily_charges_sum": Decimal("0"),
        "daily_costs_sum": Decimal("0"),
        "categories": {
            "diagnosis_code": defaultdict(lambda: [0, Decimal("0"), Decimal("0")]),
            "facility_id": defaultdict(lambda: [0, Decimal("0"), Decimal("0")]),
            "severity": defaultdict(lambda: [0, Decimal("0"), Decimal("0")]),
        },
        "charges_values": [],
        "costs_values": [],
    }


def add_row(
    summary: dict[str, Any],
    charges: Decimal,
    costs: Decimal,
    los: int,
    dimensions: dict[str, str | None],
    *,
    keep_quantiles: bool,
) -> None:
    summary["count"] += 1
    summary["charges_sum"] += charges
    summary["costs_sum"] += costs
    summary["gap_sum"] += charges - costs
    if los > 0:
        summary["daily_charges_sum"] += charges / Decimal(los)
        summary["daily_costs_sum"] += costs / Decimal(los)
    if keep_quantiles:
        summary["charges_values"].append(float(charges))
        summary["costs_values"].append(float(costs))

    for name in COST_FIELDS:
        value = dimensions[name]
        if not value:
            continue
        aggregate = summary["categories"][name][value]
        aggregate[0] += 1
        aggregate[1] += charges
        aggregate[2] += costs


def legal_keys(
    diagnosis_values: list[str],
    facility_values: list[str],
    severity_values: list[str],
) -> list[tuple[str | None, str | None, str | None]]:
    keys = [(None, None, severity) for severity in [None, *severity_values]]
    keys.extend(
        (diagnosis, None, severity)
        for diagnosis in diagnosis_values
        for severity in [None, *severity_values]
    )
    keys.extend(
        (None, facility, severity)
        for facility in facility_values
        for severity in [None, *severity_values]
    )
    return keys


def summarize_stream(
    reader: csv.DictReader,
) -> tuple[dict[str, Any], int, int]:
    aggregates: dict[tuple[str | None, str | None, str | None], dict[str, Any]] = defaultdict(
        empty_summary
    )
    diagnosis_labels: dict[str, str] = {}
    facility_labels: dict[str, str] = {}
    diagnosis_values: set[str] = set()
    facility_values: set[str] = set()
    severity_values: set[str] = set()
    raw_rows = 0
    scoped_rows = 0

    for row in reader:
        raw_rows += 1
        if row.get(None) is not None:
            raise AssertionError(f"CSV 存在结构异常行: {raw_rows}")
        if text(row, "year") != "2021":
            continue
        los = length_of_stay(text(row, "los"))
        if los is None:
            continue
        scoped_rows += 1

        diagnosis_code = text(row, "diagnosis_code") or None
        facility_id = text(row, "facility_id") or None
        severity = text(row, "severity") or None
        dimensions = {
            "diagnosis_code": diagnosis_code,
            "facility_id": facility_id,
            "severity": severity,
        }
        if diagnosis_code:
            diagnosis_values.add(diagnosis_code)
        if facility_id:
            facility_values.add(facility_id)
        if severity:
            severity_values.add(severity)

        if diagnosis_code:
            diagnosis_labels[diagnosis_code] = text(row, "diagnosis") or diagnosis_code
        if facility_id:
            facility_labels[facility_id] = text(row, "facility") or facility_id

        charges = nonnegative_decimal(text(row, "charges"))
        costs = nonnegative_decimal(text(row, "costs"))
        if charges is None or costs is None:
            continue

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
        for key in keys:
            aggregate = aggregates[key]
            add_row(
                aggregate,
                charges,
                costs,
                los,
                dimensions,
                keep_quantiles=key == WILDCARD,
            )

    sorted_diagnoses = sorted(diagnosis_values)
    sorted_facilities = sorted(facility_values)
    sorted_severities = sorted(severity_values)
    expected_keys = legal_keys(sorted_diagnoses, sorted_facilities, sorted_severities)
    return (
        {
            "aggregates": aggregates,
            "diagnosis_values": sorted_diagnoses,
            "facility_values": sorted_facilities,
            "severity_values": sorted_severities,
            "diagnosis_labels": diagnosis_labels,
            "facility_labels": facility_labels,
            "expected_keys": expected_keys,
        },
        raw_rows,
        scoped_rows,
    )


def metric_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {item["key"]: item["value"] for item in payload.get("metrics", [])}


def section_values(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {item["key"]: item["items"] for item in payload.get("sections", [])}


def expected_average(summary: dict[str, Any], field: str) -> float:
    count = summary["count"]
    return rounded(summary[field] / count if count else None)


def expected_category_items(
    summary: dict[str, Any],
    dimension: str,
    field: int,
    labels: dict[str, str],
) -> list[dict[str, Any]]:
    items = []
    for value, aggregate in summary["categories"][dimension].items():
        count, charges_sum, costs_sum = aggregate
        denominator = Decimal(count)
        items.append(
            {
                "name": labels.get(value, value),
                "value": rounded((charges_sum if field == 1 else costs_sum) / denominator),
            }
        )
    return sorted(items, key=lambda item: (-item["value"], item["name"]))[:10]


def expected_comparison_sections(
    summary: dict[str, Any],
    key: tuple[str | None, str | None, str | None],
    diagnosis_labels: dict[str, str],
    facility_labels: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    diagnosis, facility, _ = key
    expected: dict[str, list[dict[str, Any]]] = {}
    if diagnosis is None:
        expected["diagnosis_charges"] = expected_category_items(
            summary, "diagnosis_code", 1, diagnosis_labels
        )
        expected["diagnosis_costs"] = expected_category_items(
            summary, "diagnosis_code", 2, diagnosis_labels
        )
    if facility is None:
        expected["facility_charges"] = expected_category_items(
            summary, "facility_id", 1, facility_labels
        )
        expected["facility_costs"] = expected_category_items(
            summary, "facility_id", 2, facility_labels
        )
    expected["severity_charges"] = expected_category_items(
        summary, "severity", 1, {}
    )
    expected["severity_costs"] = expected_category_items(summary, "severity", 2, {})
    return expected


def expected_metric_values(
    summary: dict[str, Any],
    *,
    include_quantiles: bool,
) -> dict[str, Any]:
    values = {
        "record_count": summary["count"],
        "avg_charges": expected_average(summary, "charges_sum"),
        "avg_costs": expected_average(summary, "costs_sum"),
        "charge_cost_gap": expected_average(summary, "gap_sum"),
        "daily_charges": expected_average(summary, "daily_charges_sum"),
        "daily_costs": expected_average(summary, "daily_costs_sum"),
    }
    if include_quantiles:
        for name, percentile in QUANTILES:
            values[f"{name}_charges"] = percentile_approx(
                summary["charges_values"], percentile
            )
            values[f"{name}_costs"] = percentile_approx(
                summary["costs_values"], percentile
            )
        values["median_charges"] = values["p50_charges"]
        values["median_costs"] = values["p50_costs"]
        del values["p50_charges"]
        del values["p50_costs"]
    return values


def cost_entity_key(key: tuple[str | None, str | None, str | None]) -> str:
    diagnosis, facility, severity = key
    return (
        f"diagnosis={diagnosis if diagnosis is not None else '*'}|"
        f"facility={facility if facility is not None else '*'}|"
        f"severity={severity if severity is not None else '*'}"
    )


def compare(
    expected: dict[str, Any],
    snapshot: dict[str, Any],
    input_path: Path,
    raw_rows: int,
) -> dict[str, Any]:
    validate_snapshot_document(snapshot)
    digest = sha256_file(input_path)
    if snapshot["input"].get("sha256") != digest:
        raise AssertionError("快照输入 SHA-256 不一致")
    if snapshot["input"].get("raw_rows") != raw_rows:
        raise AssertionError("快照原始记录数不一致")
    if snapshot["data_version"] != build_data_version(input_path, digest):
        raise AssertionError("快照 data_version 不一致")

    actual = {
        record["entity_key"]: record
        for record in snapshot["records"]
        if record["module_key"] == "costs"
    }
    expected_keys = {cost_entity_key(key) for key in expected["expected_keys"]}
    if set(actual) != expected_keys:
        missing = sorted(expected_keys - set(actual))
        extra = sorted(set(actual) - expected_keys)
        raise AssertionError(f"costs 键集合不一致: missing={missing}, extra={extra}")

    nonempty = 0
    empty = 0

    def matches(name: str, wanted: Any, actual_value: Any) -> bool:
        if name in {
            "median_charges",
            "p25_charges",
            "p75_charges",
            "p90_charges",
            "median_costs",
            "p25_costs",
            "p75_costs",
            "p90_costs",
        } and raw_rows > 100:
            return math.isclose(
                float(actual_value),
                float(wanted),
                rel_tol=QUANTILE_RELATIVE_TOLERANCE,
                abs_tol=0.01,
            )
        return actual_value == wanted

    for key in expected["expected_keys"]:
        summary = expected["aggregates"].get(key)
        entity = cost_entity_key(key)
        record = actual[entity]
        payload = record["payload"]
        if not summary or not summary["count"]:
            empty += 1
            if payload["metrics"] or payload["sections"]:
                raise AssertionError(f"空组合未发布空 payload: {entity}")
            continue

        nonempty += 1
        actual_metrics = metric_values(payload)
        wanted_metrics = expected_metric_values(
            summary, include_quantiles=key == WILDCARD
        )
        for name, wanted in wanted_metrics.items():
            if not matches(name, wanted, actual_metrics.get(name)):
                raise AssertionError(
                    f"{entity} metric {name} 不一致: expected={wanted!r}, actual={actual_metrics.get(name)!r}"
                )

        actual_sections = section_values(payload)
        wanted_sections = expected_comparison_sections(
            summary, key, expected["diagnosis_labels"], expected["facility_labels"]
        )
        for name, wanted in wanted_sections.items():
            if actual_sections.get(name) != wanted:
                raise AssertionError(
                    f"{entity} section {name} 不一致: expected={wanted!r}, actual={actual_sections.get(name)!r}"
                )

        if key == WILDCARD:
            quantile_sections = {
                name: [
                    {"name": percentile_name.upper(), "value": value}
                    for percentile_name, value in (
                        (p, percentile_approx(summary[f"{field}_values"], q))
                        for p, q in QUANTILES
                    )
                ]
                for name, field in (
                    ("charges_quantiles", "charges"),
                    ("costs_quantiles", "costs"),
                )
            }
            for name, wanted in quantile_sections.items():
                actual_items = actual_sections.get(name)
                if not actual_items or len(actual_items) != len(wanted):
                    raise AssertionError(
                        f"{entity} section {name} 不一致: expected={wanted!r}, actual={actual_sections.get(name)!r}"
                    )
                for expected_item, actual_item in zip(wanted, actual_items):
                    metric_name = (
                        "median"
                        if expected_item["name"] == "P50"
                        else expected_item["name"].lower()
                    )
                    if expected_item["name"] != actual_item.get("name") or not matches(
                        f"{metric_name}_{name.split('_')[0]}",
                        expected_item["value"],
                        actual_item.get("value"),
                    ):
                        raise AssertionError(
                            f"{entity} section {name} 不一致: expected={wanted!r}, actual={actual_items!r}"
                        )

    wildcard = expected["aggregates"].get(WILDCARD, empty_summary())
    sample = next(
        (
            key
            for key in expected["expected_keys"]
            if key != WILDCARD and expected["aggregates"].get(key, {}).get("count", 0)
        ),
        None,
    )
    result = {
        "status": "PASS",
        "raw_rows": raw_rows,
        "scoped_rows": expected.get("scoped_rows", 0),
        "cost_key_count": len(expected["expected_keys"]),
        "nonempty_combination_count": nonempty,
        "empty_combination_count": empty,
        "option_counts": {
            "diagnosis_code": len(expected["diagnosis_values"]),
            "facility_id": len(expected["facility_values"]),
            "severity": len(expected["severity_values"]),
        },
        "wildcard_metrics": expected_metric_values(wildcard, include_quantiles=True),
        "data_version": snapshot["data_version"],
        "generated_at": snapshot["generated_at"],
    }
    if sample is not None:
        result["sample_finite_key"] = {
            "entity_key": cost_entity_key(sample),
            "metrics": expected_metric_values(
                expected["aggregates"][sample], include_quantiles=False
            ),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, scoped_rows = summarize_stream(csv.DictReader(handle))
    expected["scoped_rows"] = scoped_rows
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    print(json.dumps(compare(expected, snapshot, args.input, raw_rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
