"""Independently verify the published ``cohorts`` snapshot.

The production task uses PySpark cubes over its cached clean frame.  This
checker deliberately uses only the standard library and streams the input CSV
once, recomputing the cohort denominator, metrics and sections for every
wildcard/finite filter combination.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from itertools import product
from pathlib import Path
from typing import Any

from analytics_metadata import build_data_version, sha256_file


FIELD = {
    "year": "Discharge Year",
    "diagnosis": "CCSR Diagnosis Description",
    "age": "Age Group",
    "gender": "Gender",
    "admission": "Type of Admission",
    "los": "Length of Stay",
    "charges": "Total Charges",
    "costs": "Total Costs",
    "emergency": "Emergency Department Indicator",
    "severity": "APR Severity of Illness Description",
    "medical_surgical": "APR Medical Surgical Description",
}

COHORT_FIELDS = ("age", "gender", "admission")
OPTION_KEYS = {
    "age": "age_group",
    "gender": "gender",
    "admission": "admission_type",
}


def text(row: dict[str, str | None], name: str) -> str:
    value = row.get(FIELD[name])
    return value.strip() if value is not None else ""


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


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def empty_aggregate() -> dict[str, Any]:
    return {
        "count": 0,
        "los": [],
        "charges": [],
        "costs": [],
        "emergency_yes": 0,
        "surgical_yes": 0,
        "severe_yes": 0,
        "diagnosis": Counter(),
        "severity": Counter(),
        "age": Counter(),
        "gender": Counter(),
    }


def summarize_stream(
    reader: csv.DictReader,
) -> tuple[dict[str, Any], int, int]:
    aggregates: dict[tuple[str | None, str | None, str | None], dict[str, Any]] = defaultdict(
        empty_aggregate
    )
    option_values = {field: set() for field in COHORT_FIELDS}
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

        dimensions = {
            field: text(row, field) or None for field in COHORT_FIELDS
        }
        for field, value in dimensions.items():
            if value is not None:
                option_values[field].add(value)

        scoped_rows += 1
        age_values = (None, dimensions["age"]) if dimensions["age"] else (None,)
        gender_values = (
            (None, dimensions["gender"]) if dimensions["gender"] else (None,)
        )
        admission_values = (
            (None, dimensions["admission"])
            if dimensions["admission"]
            else (None,)
        )
        for key in product(age_values, gender_values, admission_values):
            aggregate = aggregates[key]
            aggregate["count"] += 1
            if los >= 0:
                aggregate["los"].append(los)

            charges = nonnegative_decimal(text(row, "charges"))
            if charges is not None:
                aggregate["charges"].append(charges)
            costs = nonnegative_decimal(text(row, "costs"))
            if costs is not None:
                aggregate["costs"].append(costs)

            aggregate["emergency_yes"] += text(row, "emergency") == "Y"
            aggregate["surgical_yes"] += "Surgical" in text(row, "medical_surgical")
            aggregate["severe_yes"] += text(row, "severity") in {"Major", "Extreme"}

            for field in ("diagnosis", "severity", "age", "gender"):
                value = text(row, field)
                if value:
                    aggregate[field][value] += 1

    options = {
        OPTION_KEYS[field]: sorted(option_values[field]) for field in COHORT_FIELDS
    }
    all_values = tuple([None, *options[OPTION_KEYS[field]]] for field in COHORT_FIELDS)
    expected = {
        key: aggregates.get(key, empty_aggregate())
        for key in product(*all_values)
    }
    return {"options": options, "aggregates": expected}, raw_rows, scoped_rows


def metric(key: str, label: str, value: int | float, unit: str) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "unit": unit}


def ordered(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    values = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        values = values[:limit]
    return [{"name": name, "value": count} for name, count in values]


def expected_payload(
    key: tuple[str | None, str | None, str | None], aggregate: dict[str, Any], options: dict[str, list[str]]
) -> dict[str, Any]:
    filters = {
        OPTION_KEYS[field]: value
        for field, value in zip(COHORT_FIELDS, key)
        if value is not None
    }
    payload: dict[str, Any] = {
        "title": "住院记录群体分析",
        "description": "有限白名单群体筛选；记录不按患者去重。",
        "metrics": [],
        "sections": [],
        "filters": filters,
    }
    if key == (None, None, None):
        payload["options"] = options

    denominator = aggregate["count"]
    if denominator == 0:
        return payload

    payload["metrics"] = [
        metric("record_count", "住院出院记录", denominator, "条"),
        metric(
            "avg_los",
            "平均住院时长",
            rounded(sum(aggregate["los"]) / len(aggregate["los"]) if aggregate["los"] else None),
            "天",
        ),
        metric(
            "avg_charges",
            "平均收费",
            rounded(sum(aggregate["charges"]) / len(aggregate["charges"]) if aggregate["charges"] else None),
            "美元",
        ),
        metric(
            "avg_costs",
            "平均成本",
            rounded(sum(aggregate["costs"]) / len(aggregate["costs"]) if aggregate["costs"] else None),
            "美元",
        ),
        metric("emergency_rate", "急诊率", rate(aggregate["emergency_yes"], denominator), "%"),
        metric("surgical_rate", "外科率", rate(aggregate["surgical_yes"], denominator), "%"),
        metric("severe_rate", "重症率", rate(aggregate["severe_yes"], denominator), "%"),
    ]
    payload["sections"] = [
        {
            "key": "diseases",
            "title": "主要疾病",
            "type": "bar",
            "items": ordered(aggregate["diagnosis"], 10),
        },
        {
            "key": "severity",
            "title": "严重程度",
            "type": "bar",
            "items": ordered(aggregate["severity"], 10),
        },
        {
            "key": "age",
            "title": "年龄结构",
            "type": "bar",
            "items": ordered(aggregate["age"]),
        },
        {
            "key": "gender",
            "title": "性别结构",
            "type": "bar",
            "items": ordered(aggregate["gender"]),
        },
    ]
    return payload


def entity_key(key: tuple[str | None, str | None, str | None]) -> str:
    return "|".join(
        f"{field}={value if value is not None else '*'}"
        for field, value in zip(COHORT_FIELDS, key)
    )


def compare(
    expected: dict[str, Any],
    snapshot: dict[str, Any],
    input_path: Path,
    raw_rows: int,
    scoped_rows: int,
) -> dict[str, Any]:
    digest = sha256_file(input_path)
    snapshot_input = snapshot.get("input") or {}
    if snapshot_input.get("sha256") != digest:
        raise AssertionError("输入 SHA-256 与快照不一致")
    if snapshot_input.get("raw_rows") != raw_rows:
        raise AssertionError("快照 input.raw_rows 与输入不一致")
    if snapshot.get("data_version") != build_data_version(input_path, digest):
        raise AssertionError("data_version 与输入版本不一致")

    records = {
        (row.get("module_key"), row.get("entity_key")): row
        for row in snapshot.get("records") or []
        if row.get("module_key") == "cohorts"
    }
    aggregate_map = expected["aggregates"]
    expected_keys = {entity_key(key) for key in aggregate_map}
    if set(key for _, key in records) != expected_keys:
        raise AssertionError("cohorts 快照键未覆盖全部 wildcard/有限组合")

    for key, aggregate in aggregate_map.items():
        actual = records[("cohorts", entity_key(key))].get("payload") or {}
        wanted = expected_payload(key, aggregate, expected["options"])
        if actual != wanted:
            raise AssertionError(
                f"cohorts {entity_key(key)} 与独立核对不一致: "
                f"expected={wanted!r}, actual={actual!r}"
            )

    empty_count = sum(aggregate["count"] == 0 for aggregate in aggregate_map.values())
    return {
        "status": "PASS",
        "module": "cohorts",
        "raw_rows": raw_rows,
        "scoped_rows": scoped_rows,
        "cohort_key_count": len(aggregate_map),
        "nonempty_combination_count": len(aggregate_map) - empty_count,
        "empty_combination_count": empty_count,
        "option_counts": {name: len(values) for name, values in expected["options"].items()},
        "data_version": snapshot["data_version"],
        "generated_at": snapshot["generated_at"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, scoped_rows = summarize_stream(csv.DictReader(handle))
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    result = compare(expected, snapshot, args.input, raw_rows, scoped_rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
