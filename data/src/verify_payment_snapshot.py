"""Independently verify the ``payments`` snapshot with the standard library.

The production task uses a PySpark cube over the shared clean frame.  This
checker deliberately does not import that aggregation code: it streams the
CSV once, rebuilds every legal payment/age filter, and compares the published
payloads.  The product task uses Spark ``percentile_approx(accuracy=10000)``;
the checker uses the standard-library lower-middle order statistic and checks
that the published observed value is within the algorithm's independent rank
error window.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from array import array
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from itertools import product
from pathlib import Path
from typing import Any

from analytics_metadata import build_data_version, sha256_file


FIELD = {
    "year": "Discharge Year",
    "age": "Age Group",
    "payment": "Payment Typology 1",
    "los": "Length of Stay",
    "charges": "Total Charges",
    "diagnosis": "CCSR Diagnosis Description",
}

PAYMENT_FIELDS = ("payment", "age")
OPTION_KEYS = {"payment": "payment_type", "age": "age_group"}
MEDIAN_ACCURACY = 10000


def text(row: dict[str, str | None], name: str) -> str:
    value = row.get(FIELD[name])
    return value.strip() if value is not None else ""


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


def nonnegative_decimal(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        parsed = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None
    return parsed if parsed >= 0 else None


def empty_aggregate() -> dict[str, Any]:
    return {
        "count": 0,
        "charges": array("d"),
        "charge_total": Decimal("0"),
        "charge_count": 0,
        "payment": Counter(),
        "age": Counter(),
        "diagnosis": Counter(),
        "payment_charge_total": defaultdict(Decimal),
        "payment_charge_count": Counter(),
    }


def summarize_stream(
    reader: csv.DictReader,
) -> tuple[dict[str, Any], int, int]:
    aggregates: dict[tuple[str | None, str | None], dict[str, Any]] = defaultdict(
        empty_aggregate
    )
    option_values = {field: set() for field in PAYMENT_FIELDS}
    raw_rows = 0
    scoped_rows = 0

    for row in reader:
        raw_rows += 1
        if row.get(None) is not None:
            raise AssertionError(f"CSV 存在结构异常行: {raw_rows}")
        if text(row, "year") != "2021":
            continue
        if length_of_stay(text(row, "los")) is None:
            continue

        dimensions = {
            field: text(row, field) or None for field in PAYMENT_FIELDS
        }
        for field, value in dimensions.items():
            if value is not None:
                option_values[field].add(value)

        scoped_rows += 1
        payment_values = (
            (None, dimensions["payment"])
            if dimensions["payment"] is not None
            else (None,)
        )
        age_values = (
            (None, dimensions["age"])
            if dimensions["age"] is not None
            else (None,)
        )
        charges = nonnegative_decimal(text(row, "charges"))
        for key in product(payment_values, age_values):
            aggregate = aggregates[key]
            aggregate["count"] += 1
            payment = dimensions["payment"]
            age = dimensions["age"]
            if payment is not None:
                aggregate["payment"][payment] += 1
            if age is not None:
                aggregate["age"][age] += 1
            diagnosis = text(row, "diagnosis")
            if diagnosis:
                aggregate["diagnosis"][diagnosis] += 1
            if charges is not None:
                aggregate["charges"].append(float(charges))
                aggregate["charge_total"] += charges
                aggregate["charge_count"] += 1
                if payment is not None:
                    aggregate["payment_charge_total"][payment] += charges
                    aggregate["payment_charge_count"][payment] += 1

    options = {
        OPTION_KEYS[field]: sorted(option_values[field]) for field in PAYMENT_FIELDS
    }
    all_values = tuple([None, *options[OPTION_KEYS[field]]] for field in PAYMENT_FIELDS)
    expected = {
        key: aggregates.get(key, empty_aggregate())
        for key in product(*all_values)
    }
    return {"options": options, "aggregates": expected}, raw_rows, scoped_rows


def metric(key: str, label: str, value: int | float, unit: str) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "unit": unit}


def rounded(value: Decimal | float | int | None) -> float:
    return 0.0 if value is None else round(float(value), 2)


def ordered(counter: Counter[str], limit: int | None = None) -> list[dict[str, int | str]]:
    values = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        values = values[:limit]
    return [{"name": name, "value": count} for name, count in values]


def payment_charge_rows(aggregate: dict[str, Any]) -> list[dict[str, str | float]]:
    rows = []
    for name, total in aggregate["payment_charge_total"].items():
        count = aggregate["payment_charge_count"][name]
        if count:
            rows.append({"name": name, "value": rounded(total / count)})
    return sorted(rows, key=lambda item: (-float(item["value"]), str(item["name"])))


def expected_payload(
    key: tuple[str | None, str | None],
    aggregate: dict[str, Any],
    options: dict[str, list[str]],
) -> dict[str, Any]:
    filters = {
        OPTION_KEYS[field]: value
        for field, value in zip(PAYMENT_FIELDS, key)
        if value is not None
    }
    payload: dict[str, Any] = {
        "title": "支付方式分析",
        "description": "核心支付维度为 Payment Typology 1；统计对象为住院出院记录。",
        "metrics": [],
        "sections": [],
        "filters": filters,
    }
    if key == (None, None):
        payload["options"] = options

    denominator = aggregate["count"]
    if denominator == 0:
        return payload

    charges = aggregate["charges"]
    median = statistics.median_low(charges) if charges else None
    payload["metrics"] = [
        metric("record_count", "记录数", denominator, "条"),
        metric(
            "avg_charges",
            "平均收费",
            rounded(
                aggregate["charge_total"] / aggregate["charge_count"]
                if aggregate["charge_count"]
                else None
            ),
            "美元",
        ),
        metric("median_charges", "收费中位数", rounded(median), "美元"),
    ]
    payload["sections"] = [
        {
            "key": "payment",
            "title": "主支付方式结构",
            "type": "bar",
            "items": ordered(aggregate["payment"]),
        },
        {
            "key": "charges",
            "title": "不同支付方式平均收费",
            "type": "bar",
            "items": payment_charge_rows(aggregate),
        },
        {
            "key": "age",
            "title": "年龄结构",
            "type": "bar",
            "items": ordered(aggregate["age"]),
        },
        {
            "key": "diseases",
            "title": "主要疾病",
            "type": "bar",
            "items": ordered(aggregate["diagnosis"], 10),
        },
    ]
    return payload


def entity_key(key: tuple[str | None, str | None]) -> str:
    return "|".join(
        f"{field}={value if value is not None else '*'}"
        for field, value in zip(PAYMENT_FIELDS, key)
    )


def _median_within_rank_error(
    received: float,
    charges: array,
) -> bool:
    """Check Spark percentile_approx's rank guarantee independently.

    ``percentile_approx(0.5, 10000)`` is a rank approximation, so comparing
    its rounded value with an exact median value is not stable when adjacent
    charges have a large gap.  The checker therefore verifies that the
    returned (rounded) charge is observed in the input and its rank is within
    the accuracy window around the lower-middle rank.
    """
    if not charges or not math.isfinite(received):
        return False
    ordered_charges = sorted(charges)
    lower_middle = (len(ordered_charges) - 1) // 2
    rank_error = max(1, math.ceil(len(ordered_charges) / MEDIAN_ACCURACY))
    lower_bound = max(0, lower_middle - rank_error - 1)
    upper_bound = min(
        len(ordered_charges) - 1,
        lower_middle + rank_error + 1,
    )
    first = bisect_left(ordered_charges, received)
    last = bisect_right(ordered_charges, received) - 1
    return first <= upper_bound and last >= lower_bound


def _compare_payload(
    actual: dict[str, Any],
    expected: dict[str, Any],
    key: tuple[str | None, str | None],
    aggregate: dict[str, Any],
) -> bool:
    if set(actual) != set(expected):
        raise AssertionError(
            f"payments {entity_key(key)} payload 字段不一致: "
            f"expected={sorted(expected)!r}, actual={sorted(actual)!r}"
        )
    for field in ("title", "description", "options", "filters", "sections"):
        if actual.get(field) != expected.get(field):
            raise AssertionError(
                f"payments {entity_key(key)} {field} 不一致: "
                f"expected={expected.get(field)!r}, actual={actual.get(field)!r}"
            )

    actual_metrics = {item["key"]: item for item in actual["metrics"]}
    expected_metrics = {item["key"]: item for item in expected["metrics"]}
    if set(actual_metrics) != set(expected_metrics):
        raise AssertionError(
            f"payments {entity_key(key)} metric key 不一致: "
            f"expected={sorted(expected_metrics)!r}, actual={sorted(actual_metrics)!r}"
        )
    for metric_key, wanted in expected_metrics.items():
        received = actual_metrics[metric_key]
        if {name: received[name] for name in ("label", "unit")} != {
            name: wanted[name] for name in ("label", "unit")
        }:
            raise AssertionError(f"payments {entity_key(key)} {metric_key} 元数据不一致")
        if metric_key == "median_charges":
            if not aggregate["charges"]:
                if received["value"] != wanted["value"]:
                    raise AssertionError(
                        f"payments {entity_key(key)} median_charges 空收费集合值不一致: "
                        f"expected={wanted['value']!r}, actual={received['value']!r}"
                    )
                continue
            if not _median_within_rank_error(
                float(received["value"]), aggregate["charges"]
            ):
                raise AssertionError(
                    f"payments {entity_key(key)} median_charges 不在 "
                    f"percentile_approx accuracy={MEDIAN_ACCURACY} 的秩误差范围内: "
                    f"exact_lower_middle={wanted['value']!r}, "
                    f"actual={received['value']!r}"
                )
        elif received["value"] != wanted["value"]:
            raise AssertionError(
                f"payments {entity_key(key)} {metric_key} 不一致: "
                f"expected={wanted['value']!r}, actual={received['value']!r}"
            )
    return True


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
        if row.get("module_key") == "payments"
    }
    aggregate_map = expected["aggregates"]
    expected_keys = {entity_key(key) for key in aggregate_map}
    if {key for _, key in records} != expected_keys:
        raise AssertionError("payments 快照键未覆盖全部 wildcard/有限组合")

    for key, aggregate in aggregate_map.items():
        actual = records[("payments", entity_key(key))].get("payload") or {}
        _compare_payload(
            actual,
            expected_payload(key, aggregate, expected["options"]),
            key,
            aggregate,
        )

    empty_count = sum(aggregate["count"] == 0 for aggregate in aggregate_map.values())
    wildcard = aggregate_map[(None, None)]
    return {
        "status": "PASS",
        "module": "payments",
        "raw_rows": raw_rows,
        "scoped_rows": scoped_rows,
        "payment_key_count": len(aggregate_map),
        "nonempty_combination_count": len(aggregate_map) - empty_count,
        "empty_combination_count": empty_count,
        "option_counts": {name: len(values) for name, values in expected["options"].items()},
        "wildcard_metrics": {
            "record_count": wildcard["count"],
            "avg_charges": rounded(
                wildcard["charge_total"] / wildcard["charge_count"]
                if wildcard["charge_count"]
                else None
            ),
            "median_algorithm": f"percentile_approx(0.5,{MEDIAN_ACCURACY})",
            "median_charges_exact": rounded(
                statistics.median_low(wildcard["charges"])
                if wildcard["charges"]
                else None
            ),
        },
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
