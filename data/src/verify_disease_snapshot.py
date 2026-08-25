"""Independently verify the ``diseases`` snapshot with the stdlib.

The production task aggregates a cached PySpark clean frame.  This verifier
deliberately streams the CSV with :mod:`csv` and recomputes the disease
formulas without importing the production aggregation code.  It checks both
the wildcard index and every finite ``profile:{diagnosis_code}`` snapshot.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analytics_metadata import build_data_version, sha256_file
from shared.disease_rules import is_non_disease_diagnosis
from shared.analytics_snapshot_contract import (
    normalize_utc_timestamp,
    validate_snapshot_document,
)


FIELD = {
    "year": "Discharge Year",
    "diagnosis": "CCSR Diagnosis Description",
    "diagnosis_code": "CCSR Diagnosis Code",
    "age": "Age Group",
    "gender": "Gender",
    "severity": "APR Severity of Illness Description",
    "mortality": "APR Risk of Mortality",
    "los": "Length of Stay",
    "charges": "Total Charges",
    "costs": "Total Costs",
    "emergency": "Emergency Department Indicator",
    "medical_surgical": "APR Medical Surgical Description",
    "procedure": "CCSR Procedure Description",
    "facility": "Facility Name",
}


def text(row: dict[str, str | None], name: str) -> str:
    value = row.get(FIELD[name])
    return value.strip() if value is not None else ""


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
        "emergency_valid_count": 0,
        "surgical_yes": 0,
        "surgical_valid_count": 0,
        "severe_yes": 0,
        "severity_valid_count": 0,
        "age": Counter(),
        "gender": Counter(),
        "severity": Counter(),
        "mortality": Counter(),
        "procedures": Counter(),
        "hospitals": Counter(),
    }


def ordered(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    values = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        values = values[:limit]
    return [{"name": name, "value": value} for name, value in values]


def profile_metrics(profile: dict[str, Any]) -> dict[str, int | float]:
    return {
        "record_count": profile["count"],
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
        "emergency_rate": rate(
            profile["emergency_yes"], profile["emergency_valid_count"]
        ),
        "surgical_rate": rate(
            profile["surgical_yes"], profile["surgical_valid_count"]
        ),
        "severe_rate": rate(
            profile["severe_yes"], profile["severity_valid_count"]
        ),
    }


def summarize_stream(
    reader: csv.DictReader,
) -> tuple[dict[str, Any], int, int]:
    profiles: dict[str, dict[str, Any]] = defaultdict(empty_profile)
    diagnosis_counts: Counter[str] = Counter()
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
        diagnosis = text(row, "diagnosis")
        diagnosis_code = text(row, "diagnosis_code")
        if not diagnosis_code or not diagnosis or is_non_disease_diagnosis(diagnosis):
            continue
        diagnosis_counts[diagnosis] += 1
        profile = profiles[diagnosis_code]
        profile["count"] += 1
        if diagnosis and (not profile["label"] or diagnosis < profile["label"]):
            profile["label"] = diagnosis
        if los >= 0:
            profile["los"].append(los)
        charges = nonnegative_decimal(text(row, "charges"))
        if charges is not None:
            profile["charges"].append(charges)
        costs = nonnegative_decimal(text(row, "costs"))
        if costs is not None:
            profile["costs"].append(costs)
        profile["emergency_yes"] += text(row, "emergency") == "Y"
        profile["emergency_valid_count"] += bool(text(row, "emergency"))
        profile["surgical_yes"] += "Surgical" in text(row, "medical_surgical")
        profile["surgical_valid_count"] += bool(text(row, "medical_surgical"))
        severity = text(row, "severity")
        profile["severe_yes"] += severity in {"Major", "Extreme"}
        profile["severity_valid_count"] += severity in {
            "Minor", "Moderate", "Major", "Extreme"
        }

        for key, counter_name in (
            ("age", "age"),
            ("gender", "gender"),
            ("severity", "severity"),
            ("mortality", "mortality"),
            ("procedure", "procedures"),
            ("facility", "hospitals"),
        ):
            value = text(row, key)
            if value:
                profile[counter_name][value] += 1

    profile_results = {
        diagnosis_code: {
            "metrics": profile_metrics(profile),
            "sections": {
                "age": ordered(profile["age"]),
                "gender": ordered(profile["gender"]),
                "severity": ordered(profile["severity"]),
                "mortality": ordered(profile["mortality"]),
                "procedures": ordered(profile["procedures"], 5),
                "hospitals": ordered(profile["hospitals"], 5),
            },
        }
        for diagnosis_code, profile in profiles.items()
    }
    expected = {
        "diagnosis_count": len(profiles),
        "options": [
            {
                "value": diagnosis_code,
                "label": profile["label"] or diagnosis_code,
            }
            for diagnosis_code, profile in sorted(profiles.items())
        ],
        "ranking": ordered(diagnosis_counts, 10),
        "profiles": profile_results,
    }
    return expected, raw_rows, scoped_rows


def metric_values(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return {item["key"]: item["value"] for item in metrics}


def section_values(sections: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {item["key"]: item["items"] for item in sections}


def compare(
    expected: dict[str, Any],
    snapshot: dict[str, Any],
    input_path: Path,
    raw_rows: int,
) -> dict[str, Any]:
    validate_snapshot_document(snapshot)
    records = snapshot["records"]
    diseases = {
        item["entity_key"]: item
        for item in records
        if item["module_key"] == "diseases"
    }
    if "index" not in diseases:
        raise AssertionError("快照缺少 diseases/index")

    digest = sha256_file(input_path)
    if snapshot["input"].get("sha256") != digest:
        raise AssertionError("输入 SHA-256 与快照不一致")
    if snapshot["input"].get("raw_rows") != raw_rows:
        raise AssertionError("快照 input.raw_rows 与输入不一致")
    if snapshot["data_version"] != build_data_version(input_path, digest):
        raise AssertionError("data_version 与输入版本不一致")

    index_payload = diseases["index"]["payload"]
    actual_options = index_payload.get("options", {}).get("diagnoses")
    if actual_options != expected["options"]:
        raise AssertionError("疾病 options.diagnoses 与独立核对不一致")
    actual_index_metrics = metric_values(index_payload["metrics"])
    if actual_index_metrics.get("diagnosis_count") != expected["diagnosis_count"]:
        raise AssertionError("疾病 diagnosis_count 与独立核对不一致")
    actual_index_sections = section_values(index_payload["sections"])
    if actual_index_sections.get("top10") != expected["ranking"]:
        raise AssertionError("疾病病例量 TOP10 与独立核对不一致")

    expected_profile_keys = {
        f"profile:{diagnosis_code}" for diagnosis_code in expected["profiles"]
    }
    actual_profile_keys = {key for key in diseases if key != "index"}
    if actual_profile_keys != expected_profile_keys:
        raise AssertionError("疾病 profile 快照键与 options 枚举不一致")

    for diagnosis_code, profile_expected in expected["profiles"].items():
        payload = diseases[f"profile:{diagnosis_code}"]["payload"]
        actual_metrics = metric_values(payload["metrics"])
        if actual_metrics != profile_expected["metrics"]:
            raise AssertionError(
                f"疾病 {diagnosis_code} metrics 不一致: "
                f"expected={profile_expected['metrics']!r}, actual={actual_metrics!r}"
            )
        actual_sections = section_values(payload["sections"])
        if actual_sections != profile_expected["sections"]:
            raise AssertionError(f"疾病 {diagnosis_code} sections 不一致")

    sample_code = expected["options"][0]["value"] if expected["options"] else None
    sample = expected["profiles"].get(sample_code) if sample_code else None
    return {
        "status": "PASS",
        "module": "diseases",
        "raw_rows": raw_rows,
        "diagnosis_count": expected["diagnosis_count"],
        "profile_count": len(expected["profiles"]),
        "empty_profile_count": 0,
        "index_top10": expected["ranking"],
        "sample_profile": (
            {
                "diagnosis_code": sample_code,
                "metrics": sample["metrics"],
                "section_counts": {
                    key: len(items) for key, items in sample["sections"].items()
                },
            }
            if sample is not None
            else None
        ),
        "data_version": snapshot["data_version"],
        "generated_at": snapshot["generated_at"],
    }


def connection_options() -> dict[str, Any]:
    result = {
        "host": os.getenv("MYSQL_HOST"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE"),
    }
    missing = [name for name in ("host", "user", "database") if not result[name]]
    if missing:
        raise ValueError("缺少 MySQL 环境变量: " + ", ".join(name.upper() for name in missing))
    return result


def compare_mysql(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as error:
        raise RuntimeError("执行 --mysql 前请安装 PyMySQL") from error

    expected = {
        (record["module_key"], record["entity_key"]): record
        for record in snapshot["records"]
        if record["module_key"] == "diseases"
    }
    connection = pymysql.connect(
        **connection_options(),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT module_key, entity_key, payload_json, data_version, generated_at "
                "FROM `analysis_snapshot_result` WHERE module_key = %s "
                "ORDER BY entity_key",
                ("diseases",),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    actual_keys = {(row["module_key"], row["entity_key"]) for row in rows}
    if actual_keys != set(expected):
        raise AssertionError("MySQL diseases 主键集合与快照不一致")

    payload_mismatches = 0
    versions: set[str] = set()
    timestamps: set[str] = set()
    for row in rows:
        key = (row["module_key"], row["entity_key"])
        payload_json = row["payload_json"]
        if isinstance(payload_json, bytes):
            payload_json = payload_json.decode("utf-8")
        if json.loads(payload_json) != expected[key]["payload"]:
            payload_mismatches += 1
        versions.add(row["data_version"])
        timestamps.add(normalize_utc_timestamp(row["generated_at"]))

    expected_timestamp = normalize_utc_timestamp(snapshot["generated_at"])
    if payload_mismatches or versions != {snapshot["data_version"]} or timestamps != {expected_timestamp}:
        raise AssertionError(
            "MySQL diseases 发布一致性失败: "
            f"payload_mismatches={payload_mismatches}, versions={sorted(versions)}, "
            f"timestamps={sorted(timestamps)}"
        )
    return {
        "status": "PASS",
        "module": "diseases",
        "mysql_rows": len(rows),
        "payload_mismatches": payload_mismatches,
        "data_versions": sorted(versions),
        "generated_at": sorted(timestamps),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--mysql", action="store_true")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, scoped_rows = summarize_stream(csv.DictReader(handle))
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    result = compare(expected, snapshot, args.input, raw_rows)
    result["scoped_rows"] = scoped_rows
    if args.mysql:
        result["mysql"] = compare_mysql(snapshot)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
