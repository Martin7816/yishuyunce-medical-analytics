"""Independently verify the ``risks`` snapshot with the standard library.

The production task uses PySpark cubes over the shared clean frame.  This
checker deliberately does not import that aggregation code: it streams the
CSV once, rebuilds every legal age/diagnosis filter, and compares the
published metrics and sections.
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
    "age": "Age Group",
    "diagnosis_code": "CCSR Diagnosis Code",
    "diagnosis": "CCSR Diagnosis Description",
    "los": "Length of Stay",
    "charges": "Total Charges",
    "costs": "Total Costs",
    "severity": "APR Severity of Illness Description",
    "mortality": "APR Risk of Mortality",
    "disposition": "Patient Disposition",
}

RISK_FIELDS = ("age", "diagnosis_code")
RISK_ENTITY_FIELDS = ("age", "diagnosis")
OPTION_KEYS = {"age": "age_group", "diagnosis_code": "diagnosis_code"}


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
        "severity_valid_count": 0,
        "high_risk_count": 0,
        "los_sum": Decimal("0"),
        "los_count": 0,
        "charges_sum": Decimal("0"),
        "charges_count": 0,
        "costs_sum": Decimal("0"),
        "costs_count": 0,
        "severity": Counter(),
        "mortality": Counter(),
        "disposition": Counter(),
        "age": Counter(),
        "diagnosis": Counter(),
    }


def summarize_stream(
    reader: csv.DictReader,
) -> tuple[dict[str, Any], int, int]:
    aggregates: dict[tuple[str | None, str | None], dict[str, Any]] = defaultdict(
        empty_aggregate
    )
    option_values = {field: set() for field in RISK_FIELDS}
    diagnosis_labels: dict[str, str] = {}
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

        diagnosis = text(row, "diagnosis")
        raw_diagnosis_code = text(row, "diagnosis_code")
        dimensions = {
            "age": text(row, "age") or None,
            "diagnosis_code": (
                raw_diagnosis_code if raw_diagnosis_code and diagnosis else None
            ),
        }
        diagnosis_code = dimensions["diagnosis_code"]
        if diagnosis_code is not None:
            option_values["diagnosis_code"].add(diagnosis_code)
            if diagnosis:
                diagnosis_labels[diagnosis_code] = min(
                    diagnosis, diagnosis_labels.get(diagnosis_code, diagnosis)
                )
        if dimensions["age"] is not None:
            option_values["age"].add(dimensions["age"])

        scoped_rows += 1
        age_values = (
            (None, dimensions["age"]) if dimensions["age"] else (None,)
        )
        diagnosis_values = (
            (None, dimensions["diagnosis_code"])
            if dimensions["diagnosis_code"]
            else (None,)
        )
        high_risk = text(row, "severity") in {"Major", "Extreme"}
        severity_valid = text(row, "severity") in {
            "Minor", "Moderate", "Major", "Extreme"
        }
        charges = nonnegative_decimal(text(row, "charges"))
        costs = nonnegative_decimal(text(row, "costs"))
        for key in product(age_values, diagnosis_values):
            aggregate = aggregates[key]
            aggregate["count"] += 1
            aggregate["severity_valid_count"] += severity_valid

            severity = text(row, "severity")
            if severity:
                aggregate["severity"][severity] += 1
            mortality = text(row, "mortality")
            if mortality:
                aggregate["mortality"][mortality] += 1

            if not high_risk:
                continue
            aggregate["high_risk_count"] += 1
            if los >= 0:
                aggregate["los_sum"] += los
                aggregate["los_count"] += 1
            if charges is not None:
                aggregate["charges_sum"] += charges
                aggregate["charges_count"] += 1
            if costs is not None:
                aggregate["costs_sum"] += costs
                aggregate["costs_count"] += 1

            disposition = text(row, "disposition")
            if disposition:
                aggregate["disposition"][disposition] += 1
            age = text(row, "age")
            if age:
                aggregate["age"][age] += 1
            if diagnosis:
                aggregate["diagnosis"][diagnosis] += 1

    options = {
        "age_group": sorted(option_values["age"]),
        "diagnosis_code": [
            {"value": code, "label": diagnosis_labels.get(code, code)}
            for code in sorted(option_values["diagnosis_code"])
        ],
    }
    age_values = (None, *options["age_group"])
    diagnosis_codes = tuple(item["value"] for item in options["diagnosis_code"])
    diagnosis_values = (None, *diagnosis_codes)
    expected = {
        key: aggregates.get(key, empty_aggregate())
        for key in product(age_values, diagnosis_values)
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
    key: tuple[str | None, str | None],
    aggregate: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    filters = {
        OPTION_KEYS[field]: value
        for field, value in zip(RISK_FIELDS, key)
        if value is not None
    }
    payload: dict[str, Any] = {
        "title": "病情严重程度与风险分析",
        "description": "Major/Extreme比例以严重程度可判定记录为统计总体；群体统计不构成诊断、治疗或因果判断。",
        "metrics": [],
        "sections": [],
        "filters": filters,
    }
    if key == (None, None):
        payload["options"] = options

    record_count = aggregate["count"]
    if record_count == 0:
        return payload

    severity_denominator = aggregate["severity_valid_count"]
    high_risk_count = aggregate["high_risk_count"]
    payload["metrics"] = [
        metric(
            "severity_valid_count",
            "可判定风险记录",
            severity_denominator,
            "条",
        ),
        metric(
            "high_risk_count",
            "Major/Extreme记录数",
            high_risk_count,
            "条",
        ),
        metric(
            "high_risk_rate",
            "Major/Extreme比例",
            rate(high_risk_count, severity_denominator),
            "%",
        ),
    ]
    if high_risk_count:
        payload["metrics"].extend(
            [
                metric(
                    "avg_los",
                    "高风险平均住院时长",
                    rounded(
                        aggregate["los_sum"] / aggregate["los_count"]
                        if aggregate["los_count"]
                        else None
                    ),
                    "天",
                ),
                metric(
                    "avg_charges",
                    "高风险平均收费",
                    rounded(
                        aggregate["charges_sum"] / aggregate["charges_count"]
                        if aggregate["charges_count"]
                        else None
                    ),
                    "美元",
                ),
                metric(
                    "avg_costs",
                    "高风险平均成本",
                    rounded(
                        aggregate["costs_sum"] / aggregate["costs_count"]
                        if aggregate["costs_count"]
                        else None
                    ),
                    "美元",
                ),
            ]
        )
    payload["sections"] = [
        {
            "key": "severity",
            "title": "严重程度分布",
            "type": "bar",
            "items": ordered(aggregate["severity"]),
        },
        {
            "key": "mortality",
            "title": "死亡风险分布",
            "type": "bar",
            "items": ordered(aggregate["mortality"]),
        },
        {
            "key": "disposition",
            "title": "高风险记录离院去向",
            "type": "bar",
            "items": ordered(aggregate["disposition"]),
        },
        {
            "key": "age",
            "title": "高风险年龄结构",
            "type": "bar",
            "items": ordered(aggregate["age"]),
        },
        {
            "key": "diseases",
            "title": "高风险疾病 TOP10",
            "type": "bar",
            "items": ordered(aggregate["diagnosis"], 10),
        },
    ]
    return payload


def entity_key(key: tuple[str | None, str | None]) -> str:
    return "|".join(
        f"{field}={value if value is not None else '*'}"
        for field, value in zip(RISK_ENTITY_FIELDS, key)
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
        if row.get("module_key") == "risks"
    }
    aggregate_map = expected["aggregates"]
    expected_keys = {entity_key(key) for key in aggregate_map}
    if set(key for _, key in records) != expected_keys:
        raise AssertionError("risks 快照键未覆盖全部 wildcard/有限组合")

    for key, aggregate in aggregate_map.items():
        actual = records[("risks", entity_key(key))].get("payload") or {}
        wanted = expected_payload(key, aggregate, expected["options"])
        if actual != wanted:
            raise AssertionError(
                f"risks {entity_key(key)} 与独立核对不一致: "
                f"expected={wanted!r}, actual={actual!r}"
            )

    empty_count = sum(aggregate["count"] == 0 for aggregate in aggregate_map.values())
    wildcard = aggregate_map[(None, None)]
    return {
        "status": "PASS",
        "module": "risks",
        "raw_rows": raw_rows,
        "scoped_rows": scoped_rows,
        "risk_key_count": len(aggregate_map),
        "nonempty_combination_count": len(aggregate_map) - empty_count,
        "empty_combination_count": empty_count,
        "option_counts": {
            name: len(values) for name, values in expected["options"].items()
        },
        "wildcard_record_count": wildcard["count"],
        "wildcard_severity_valid_count": wildcard["severity_valid_count"],
        "wildcard_high_risk_count": wildcard["high_risk_count"],
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
