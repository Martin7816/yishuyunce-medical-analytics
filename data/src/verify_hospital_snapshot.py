"""Independently verify the ``hospitals`` snapshot with the stdlib.

The production task uses PySpark to aggregate a cached clean frame.  This
verifier deliberately does not import that aggregation code: it streams the
CSV once with :mod:`csv`, recomputes the hospital formulas, and compares the
index plus every published facility profile.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from analytics_metadata import build_data_version, sha256_file


FIELD = {
    "year": "Discharge Year",
    "diagnosis": "CCSR Diagnosis Description",
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
    """Return a trimmed source value using the frozen facility-id alias."""

    columns = FIELD_ALIASES.get(name, (FIELD[name],))
    for column in columns:
        value = row.get(column)
        if value is not None:
            return value.strip()
    return ""


def parse_decimal(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def nonnegative_decimal(value: str) -> Decimal | None:
    parsed = parse_decimal(value)
    return parsed if parsed is not None and parsed >= 0 else None


def length_of_stay(value: str) -> int | None:
    if not value:
        return None
    if value == "120 +":
        return 120
    try:
        # Match Spark's string-to-int cast.  Negative values remain in the
        # record denominator, while the average below excludes them.
        return int(value)
    except ValueError:
        return None


def rounded(value: Decimal | float | int | None, decimals: int = 2) -> float:
    if value is None:
        return 0.0
    return round(float(value), decimals)


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def empty_profile() -> dict[str, Any]:
    return {
        "label": "",
        "count": 0,
        "los": [],
        "charges": [],
        "costs": [],
        "emergency_yes": 0,
        "surgical_yes": 0,
        "severe_yes": 0,
        "diseases": Counter(),
        "medical_surgical": Counter(),
    }


def summarize_stream(
    reader: csv.DictReader,
) -> tuple[dict[str, Any], int, int]:
    profiles: dict[str, dict[str, Any]] = defaultdict(empty_profile)
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
        facility_id = text(row, "facility_id")
        if not facility_id:
            continue

        scoped_rows += 1
        profile = profiles[facility_id]
        profile["count"] += 1
        label = text(row, "facility")
        if label and (not profile["label"] or label < profile["label"]):
            profile["label"] = label
        if los >= 0:
            profile["los"].append(los)
        charges = nonnegative_decimal(text(row, "charges"))
        if charges is not None:
            profile["charges"].append(charges)
        costs = nonnegative_decimal(text(row, "costs"))
        if costs is not None:
            profile["costs"].append(costs)
        profile["emergency_yes"] += text(row, "emergency") == "Y"
        profile["surgical_yes"] += "Surgical" in text(row, "medical_surgical")
        profile["severe_yes"] += text(row, "severity") in {"Major", "Extreme"}

        diagnosis = text(row, "diagnosis")
        if diagnosis:
            profile["diseases"][diagnosis] += 1
        medical_surgical = text(row, "medical_surgical")
        if medical_surgical:
            profile["medical_surgical"][medical_surgical] += 1

    def ordered(counter: Counter[str], limit: int | None = None):
        values = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if limit is not None:
            values = values[:limit]
        return [{"name": name, "value": count} for name, count in values]

    def profile_metrics(profile: dict[str, Any]) -> dict[str, int | float]:
        return {
            "case_count": profile["count"],
            "avg_los": rounded(
                sum(profile["los"]) / len(profile["los"])
                if profile["los"]
                else None
            ),
            "avg_charges": rounded(
                sum(profile["charges"]) / len(profile["charges"])
                if profile["charges"]
                else None
            ),
            "avg_costs": rounded(
                sum(profile["costs"]) / len(profile["costs"])
                if profile["costs"]
                else None
            ),
            "emergency_rate": rate(profile["emergency_yes"], profile["count"]),
            "surgical_rate": rate(profile["surgical_yes"], profile["count"]),
            "severe_rate": rate(profile["severe_yes"], profile["count"]),
        }

    ranking = sorted(
        profiles.items(),
        key=lambda item: (-item[1]["count"], item[1]["label"] or item[0], item[0]),
    )
    expected = {
        "facility_count": len(profiles),
        "options": [
            {"value": facility_id, "label": profile["label"] or facility_id}
            for facility_id, profile in sorted(profiles.items())
        ],
        "ranking": [
            {
                "name": profile["label"] or facility_id,
                "value": profile["count"],
            }
            for facility_id, profile in ranking[:10]
        ],
        "profiles": {
            facility_id: {
                "metrics": profile_metrics(profile),
                "diseases": ordered(profile["diseases"], 5),
                "medical_surgical": ordered(profile["medical_surgical"]),
            }
            for facility_id, profile in profiles.items()
        },
    }
    return expected, raw_rows, scoped_rows


def metric_values(metrics: list[dict[str, Any]], field: str) -> dict[str, Any]:
    return {
        item.get("key"): item.get(field, item.get("value")) for item in metrics
    }


def compare(
    expected: dict[str, Any],
    snapshot: dict[str, Any],
    input_path: Path,
    raw_rows: int,
) -> dict[str, Any]:
    records = snapshot.get("records") or []
    hospitals = {
        item.get("entity_key"): item
        for item in records
        if item.get("module_key") == "hospitals"
    }
    if "index" not in hospitals:
        raise AssertionError("快照缺少 hospitals/index")

    digest = sha256_file(input_path)
    if (snapshot.get("input") or {}).get("sha256") != digest:
        raise AssertionError("输入 SHA-256 与快照不一致")
    if (snapshot.get("input") or {}).get("raw_rows") != raw_rows:
        raise AssertionError("快照 input.raw_rows 与输入不一致")
    if snapshot.get("data_version") != build_data_version(input_path, digest):
        raise AssertionError("data_version 与输入版本不一致")

    index_payload = hospitals["index"].get("payload") or {}
    options = (index_payload.get("options") or {}).get("facilities")
    if options != expected["options"]:
        raise AssertionError("医院 options.facilities 与独立核对不一致")
    index_metrics = metric_values(index_payload.get("metrics") or [], "value")
    if index_metrics.get("facility_count") != expected["facility_count"]:
        raise AssertionError("医院 facility_count 与独立核对不一致")
    sections = {
        item.get("key"): item.get("items")
        for item in index_payload.get("sections") or []
    }
    if sections.get("ranking") != expected["ranking"]:
        raise AssertionError("医院病例量排行与独立核对不一致")

    expected_profile_keys = {f"profile:{facility_id}" for facility_id in expected["profiles"]}
    actual_profile_keys = {key for key in hospitals if key != "index"}
    if actual_profile_keys != expected_profile_keys:
        raise AssertionError("医院 profile 快照键与 options 枚举不一致")

    for facility_id, profile_expected in expected["profiles"].items():
        payload = hospitals[f"profile:{facility_id}"].get("payload") or {}
        actual_metrics = metric_values(payload.get("metrics") or [], "value")
        if actual_metrics != profile_expected["metrics"]:
            raise AssertionError(
                f"医院 {facility_id} metrics 不一致: "
                f"expected={profile_expected['metrics']!r}, actual={actual_metrics!r}"
            )
        actual_sections = {
            item.get("key"): item.get("items")
            for item in payload.get("sections") or []
        }
        if actual_sections.get("diseases") != profile_expected["diseases"]:
            raise AssertionError(f"医院 {facility_id} 主要疾病 TOP5 不一致")
        if actual_sections.get("medical_surgical") != profile_expected["medical_surgical"]:
            raise AssertionError(f"医院 {facility_id} 内外科结构不一致")

    return {
        "status": "PASS",
        "module": "hospitals",
        "raw_rows": raw_rows,
        "scoped_rows_with_facility": sum(
            profile["metrics"]["case_count"]
            for profile in expected["profiles"].values()
        ),
        "facility_count": expected["facility_count"],
        "profile_count": len(expected["profiles"]),
        "empty_profile_count": 0,
        "top5": expected["ranking"][:5],
        "data_version": snapshot["data_version"],
        "generated_at": snapshot["generated_at"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, _ = summarize_stream(csv.DictReader(handle))
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    result = compare(expected, snapshot, args.input, raw_rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
