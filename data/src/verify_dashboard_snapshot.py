"""Independently verify the ``dashboard/overview`` snapshot with the stdlib.

This verifier intentionally does not import the PySpark aggregation code.  It
re-reads only the selected CSV columns with :mod:`csv`, applies the documented
cleaning rules, and compares the resulting metrics and sections to the
generated dashboard payload.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.disease_rules import is_non_disease_diagnosis


FIELD = {
    "diagnosis": "CCSR Diagnosis Description",
    "year": "Discharge Year",
    "age": "Age Group",
    "payment": "Payment Typology 1",
    "facility": "Facility Name",
    "facility_id": "Permanent Facility Id",
    "severity": "APR Severity of Illness Description",
    "los": "Length of Stay",
    "charges": "Total Charges",
    "costs": "Total Costs",
    "emergency": "Emergency Department Indicator",
    "medical_surgical": "APR Medical Surgical Description",
}

FIELD_ALIASES = {"facility_id": ("Permanent Facility Id", "Facility ID")}


def text(row: dict[str, str | None], name: str) -> str:
    value = next(
        (row.get(column) for column in FIELD_ALIASES.get(name, (FIELD[name],)) if row.get(column) is not None),
        None,
    )
    return value.strip() if value is not None else ""


def nonnegative_decimal(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None
    if parsed < 0:
        return None
    return float(parsed)


def length_of_stay(value: str) -> int | None:
    if not value:
        return None
    if value == "120 +":
        return 120
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def average(values: list[float], decimals: int = 2) -> float:
    return round(sum(values) / len(values), decimals) if values else 0.0


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def counts(rows: list[dict[str, str | None]], field_name: str) -> list[dict[str, int | str]]:
    grouped: dict[str, int] = {}
    for row in rows:
        value = text(row, field_name)
        if value and not (field_name == "diagnosis" and is_non_disease_diagnosis(value)):
            grouped[value] = grouped.get(value, 0) + 1
    return [
        {"name": name, "value": value}
        for name, value in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))
    ]


def summarize(rows: list[dict[str, str | None]]) -> dict[str, Any]:
    denominator = len(rows)
    los_values = [
        parsed
        for parsed in (length_of_stay(text(row, "los")) for row in rows)
        if parsed is not None
    ]
    charges = [
        parsed
        for parsed in (nonnegative_decimal(text(row, "charges")) for row in rows)
        if parsed is not None
    ]
    costs = [
        parsed
        for parsed in (nonnegative_decimal(text(row, "costs")) for row in rows)
        if parsed is not None
    ]
    facility_ids = {text(row, "facility_id") for row in rows}
    facility_ids.discard("")
    severity_valid_count = sum(
        text(row, "severity") in {"Minor", "Moderate", "Major", "Extreme"}
        for row in rows
    )
    emergency_valid_count = sum(bool(text(row, "emergency")) for row in rows)
    surgical_valid_count = sum(bool(text(row, "medical_surgical")) for row in rows)

    metrics = {
        "record_count": denominator,
        "facility_count": len(facility_ids),
        "avg_los": average([float(value) for value in los_values]),
        "avg_charges": average(charges),
        "avg_costs": average(costs),
        "emergency_rate": rate(
            sum(text(row, "emergency") == "Y" for row in rows),
            emergency_valid_count,
        ),
        "surgical_rate": rate(
            sum("Surgical" in text(row, "medical_surgical") for row in rows),
            surgical_valid_count,
        ),
        "severe_rate": rate(
            sum(text(row, "severity") in {"Major", "Extreme"} for row in rows),
            severity_valid_count,
        ),
    }
    return {
        "metrics": metrics,
        "sections": {
            "age": counts(rows, "age"),
            "payment": counts(rows, "payment"),
            "disease_top10": counts(rows, "diagnosis")[:10],
            "hospital_top10": counts(rows, "facility")[:10],
            "severity": counts(rows, "severity"),
        },
    }


def summarize_stream(reader: csv.DictReader) -> tuple[dict[str, Any], int, int]:
    """Compute the dashboard expectation without retaining the raw rows."""

    grouped = {name: {} for name in ("age", "payment", "diagnosis", "facility", "severity")}
    facility_ids: set[str] = set()
    raw_rows = 0
    in_scope_rows = 0
    los_sum = 0.0
    los_count = 0
    charges_sum = Decimal("0")
    charges_count = 0
    costs_sum = Decimal("0")
    costs_count = 0
    emergency_yes = 0
    emergency_valid_count = 0
    surgical_yes = 0
    surgical_valid_count = 0
    severe_yes = 0
    severity_valid_count = 0

    for row in reader:
        raw_rows += 1
        if row.get(None) is not None:
            fail(f"CSV 存在结构异常行: {raw_rows}")
        if text(row, "year") != "2021":
            continue
        los = length_of_stay(text(row, "los"))
        if los is None:
            continue
        in_scope_rows += 1
        for name in grouped:
            value = text(row, name)
            if value and not (name == "diagnosis" and is_non_disease_diagnosis(value)):
                grouped[name][value] = grouped[name].get(value, 0) + 1
        facility_id = text(row, "facility_id")
        if facility_id:
            facility_ids.add(facility_id)
        los_sum += los
        los_count += 1
        charge = nonnegative_decimal(text(row, "charges"))
        if charge is not None:
            charges_sum += Decimal(str(charge))
            charges_count += 1
        cost = nonnegative_decimal(text(row, "costs"))
        if cost is not None:
            costs_sum += Decimal(str(cost))
            costs_count += 1
        emergency_yes += text(row, "emergency") == "Y"
        emergency_valid_count += bool(text(row, "emergency"))
        surgical_yes += "Surgical" in text(row, "medical_surgical")
        surgical_valid_count += bool(text(row, "medical_surgical"))
        severe_yes += text(row, "severity") in {"Major", "Extreme"}
        severity_valid_count += text(row, "severity") in {
            "Minor", "Moderate", "Major", "Extreme"
        }

    def average_total(total: Decimal | float, count: int) -> float:
        return round(float(total / count), 2) if count else 0.0

    def ordered(name: str) -> list[dict[str, int | str]]:
        return [
            {"name": name_value, "value": value}
            for name_value, value in sorted(
                grouped[name].items(), key=lambda item: (-item[1], item[0])
            )
        ]

    expected = {
        "metrics": {
            "record_count": in_scope_rows,
            "facility_count": len(facility_ids),
            "avg_los": round(los_sum / los_count, 2) if los_count else 0.0,
            "avg_charges": average_total(charges_sum, charges_count),
            "avg_costs": average_total(costs_sum, costs_count),
            "emergency_rate": rate(emergency_yes, emergency_valid_count),
            "surgical_rate": rate(surgical_yes, surgical_valid_count),
            "severe_rate": rate(severe_yes, severity_valid_count),
        },
        "sections": {
            "age": ordered("age"),
            "payment": ordered("payment"),
            "disease_top10": ordered("diagnosis")[:10],
            "hospital_top10": ordered("facility")[:10],
            "severity": ordered("severity"),
        },
    }
    return expected, raw_rows, in_scope_rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise AssertionError(message)


def compare(
    expected: dict[str, Any],
    snapshot: dict[str, Any],
    input_path: Path,
    raw_rows: int,
) -> None:
    records = snapshot.get("records")
    dashboard = next(
        (
            item
            for item in records or []
            if item.get("module_key") == "dashboard"
            and item.get("entity_key") == "overview"
        ),
        None,
    )
    if dashboard is None:
        fail("快照缺少 dashboard/overview")

    input_metadata = snapshot.get("input") or {}
    digest = sha256_file(input_path)
    if input_metadata.get("sha256") != digest:
        fail(
            "输入 SHA-256 不一致: "
            f"expected={digest!r}, actual={input_metadata.get('sha256')!r}"
        )
    if input_metadata.get("raw_rows") != raw_rows:
        fail(
            "原始记录数不一致: "
            f"expected={raw_rows!r}, actual={input_metadata.get('raw_rows')!r}"
        )

    actual_payload = dashboard.get("payload") or {}
    expected_payload_keys = {"title", "description", "metrics", "sections"}
    if set(actual_payload) != expected_payload_keys:
        fail(
            "dashboard payload 字段不一致: "
            f"expected={sorted(expected_payload_keys)!r}, actual={sorted(actual_payload)!r}"
        )
    actual_metrics = {
        item.get("key"): item.get("value")
        for item in actual_payload.get("metrics", [])
    }
    if set(actual_metrics) != set(expected["metrics"]):
        fail(
            "dashboard metrics key 不一致: "
            f"expected={sorted(expected['metrics'])!r}, actual={sorted(actual_metrics)!r}"
        )
    for key, expected_value in expected["metrics"].items():
        actual_value = actual_metrics.get(key)
        if isinstance(expected_value, float):
            if not isinstance(actual_value, (int, float)) or not math.isclose(
                float(actual_value), expected_value, abs_tol=1e-9
            ):
                fail(f"指标 {key} 不一致: expected={expected_value!r}, actual={actual_value!r}")
        elif actual_value != expected_value:
            fail(f"指标 {key} 不一致: expected={expected_value!r}, actual={actual_value!r}")

    actual_sections = {
        item.get("key"): item.get("items")
        for item in actual_payload.get("sections", [])
    }
    if set(actual_sections) != set(expected["sections"]):
        fail(
            "dashboard sections key 不一致: "
            f"expected={sorted(expected['sections'])!r}, actual={sorted(actual_sections)!r}"
        )
    for key, expected_items in expected["sections"].items():
        if actual_sections.get(key) != expected_items:
            fail(
                f"分组 {key} 不一致: "
                f"expected={expected_items!r}, actual={actual_sections.get(key)!r}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected, raw_rows, in_scope_rows = summarize_stream(reader)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    compare(expected, snapshot, args.input, raw_rows)

    dashboard = next(
        item
        for item in snapshot["records"]
        if item["module_key"] == "dashboard" and item["entity_key"] == "overview"
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "input": args.input.name,
                "raw_rows": raw_rows,
                "in_scope_rows": in_scope_rows,
                "data_version": snapshot["data_version"],
                "generated_at": snapshot["generated_at"],
                "metrics": expected["metrics"],
                "section_counts": {
                    key: len(value) for key, value in expected["sections"].items()
                },
                "snapshot_records": len(snapshot["records"]),
                "dashboard_payload_keys": sorted(dashboard["payload"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
