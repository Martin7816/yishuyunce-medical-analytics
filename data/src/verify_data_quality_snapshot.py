"""Independently verify the #71 data-quality snapshot with the stdlib only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


KNOWN_SOURCE_NAME = (
    "Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv"
)
REQUIRED_COLUMNS = {
    "CCSR Diagnosis Description",
    "Discharge Year",
    "Length of Stay",
    "Total Charges",
    "Total Costs",
}
METRIC_KEYS = (
    "raw_rows",
    "valid_rows",
    "out_of_scope_rows",
    "money_parse_or_negative",
    "missing_los",
    "diagnosis_missing",
    "los_capped",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_data_version(path: Path, digest: str) -> str:
    if path.name == KNOWN_SOURCE_NAME:
        version = f"sparcs_2021_20231012_sha256_{digest}"
    else:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._-")
        version = f"{safe_name or 'sparcs_input'}_sha256_{digest}"
    if any(part.lower() == "fixtures" for part in path.parts):
        return f"fixture:{version}"
    return version


def parse_money(value: str | None) -> Decimal | None:
    text = (value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def parse_los(value: str | None) -> tuple[int | None, bool]:
    text = (value or "").strip()
    if text == "120 +":
        return 120, True
    if not text:
        return None, False
    try:
        return int(text), False
    except ValueError:
        return None, False


def summarize_csv(path: Path) -> dict[str, int]:
    metrics = {key: 0 for key in METRIC_KEYS}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError("CSV 缺少必要字段: " + ", ".join(sorted(missing)))

        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"CSV 第 {row_number} 行存在多余字段")
            metrics["raw_rows"] += 1

            in_scope = (row.get("Discharge Year") or "").strip() == "2021"
            if not in_scope:
                metrics["out_of_scope_rows"] += 1
                continue

            los, capped = parse_los(row.get("Length of Stay"))
            if los is None:
                metrics["missing_los"] += 1
            else:
                metrics["valid_rows"] += 1
            if capped:
                metrics["los_capped"] += 1

            diagnosis = (row.get("CCSR Diagnosis Description") or "").strip()
            if not diagnosis:
                metrics["diagnosis_missing"] += 1

            charges = parse_money(row.get("Total Charges"))
            costs = parse_money(row.get("Total Costs"))
            if (
                charges is None
                or costs is None
                or charges < 0
                or costs < 0
            ):
                metrics["money_parse_or_negative"] += 1
    return metrics


def load_quality_record(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    records = [
        row
        for row in document.get("records", [])
        if row.get("module_key") == "data_quality"
        and row.get("entity_key") == "summary"
    ]
    if len(records) != 1:
        raise ValueError(
            "必须且只能存在一个 data_quality / summary，"
            f"实际数量={len(records)}"
        )
    return document, records[0]


def check(name: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "check": name,
        "expected": expected,
        "actual": actual,
        "status": "PASS" if actual == expected else "FAIL",
    }


def verify(input_path: Path, snapshot_path: Path) -> dict[str, Any]:
    expected_metrics = summarize_csv(input_path)
    digest = sha256_file(input_path)
    document, quality = load_quality_record(snapshot_path)
    metric_items = quality.get("payload", {}).get("metrics", [])
    metric_keys = [item.get("key") for item in metric_items]
    if len(metric_keys) != len(set(metric_keys)):
        raise ValueError("data_quality metrics 存在重复 key")
    actual_metrics = {item.get("key"): item.get("value") for item in metric_items}
    actual_units = {item.get("key"): item.get("unit") for item in metric_items}

    metric_results = [
        {
            "metric": key,
            "expected": expected_metrics[key],
            "actual": actual_metrics.get(key),
            "status": (
                "PASS"
                if actual_metrics.get(key) == expected_metrics[key]
                else "FAIL"
            ),
        }
        for key in METRIC_KEYS
    ]
    checks = [
        check("metric_keys", sorted(METRIC_KEYS), sorted(actual_metrics)),
        check(
            "metric_units",
            {key: "条" for key in METRIC_KEYS},
            {key: actual_units.get(key) for key in METRIC_KEYS},
        ),
        check("input.file_name", input_path.name, document.get("input", {}).get("file_name")),
        check("input.sha256", digest, document.get("input", {}).get("sha256")),
        check(
            "input.raw_rows",
            expected_metrics["raw_rows"],
            document.get("input", {}).get("raw_rows"),
        ),
        check(
            "data_version",
            expected_data_version(input_path, digest),
            document.get("data_version"),
        ),
    ]

    generated_at = document.get("generated_at")
    generated_at_valid = False
    if isinstance(generated_at, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", generated_at
    ):
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            generated_at_valid = True
        except ValueError:
            pass
    checks.append(check("generated_at_format", True, generated_at_valid))

    if any(part.lower() == "fixtures" for part in input_path.parts):
        storage_sections = [
            item
            for item in quality.get("payload", {}).get("sections", [])
            if item.get("key") == "storage"
        ]
        if len(storage_sections) != 1:
            raise ValueError("fixture 必须且只能包含一个 storage section")
        storage = storage_sections[0]
        statuses = {
            item.get("name"): item.get("value") for item in storage.get("items", [])
        }
        checks.extend(
            [
                check("storage.type", "status", storage.get("type")),
                check(
                    "fixture_statuses",
                    {
                        "HDFS": "CHECK_REQUIRED",
                        "Hive": "CHECK_REQUIRED",
                        "MySQL": "CHECK_REQUIRED",
                        "PySpark任务": "FIXTURE_ONLY",
                    },
                    statuses,
                ),
            ]
        )

    passed = all(item["status"] == "PASS" for item in metric_results + checks)
    return {
        "status": "PASS" if passed else "FAIL",
        "input_file": input_path.name,
        "sha256": digest,
        "data_version": document.get("data_version"),
        "generated_at": generated_at,
        "metrics": metric_results,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = verify(args.input.resolve(), args.snapshot.resolve())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        result = {"status": "FAIL", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
