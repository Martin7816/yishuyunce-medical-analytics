"""Compare the published ``payments`` rows with a snapshot artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.analytics_snapshot_contract import (
    normalize_utc_timestamp,
    validate_snapshot_document,
)


TABLE = "analysis_snapshot_result"


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
        raise ValueError("缺少 MySQL 环境变量: " + ", ".join(missing))
    return result


def mysql_timestamp(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")
    return str(value).replace("T", " ").removesuffix("Z")


def verify(snapshot_path: Path) -> dict[str, Any]:
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as error:
        raise RuntimeError("执行 MySQL 核对前请安装 PyMySQL") from error

    document = validate_snapshot_document(
        json.loads(snapshot_path.read_text(encoding="utf-8"))
    )
    expected_payments = {
        (record["module_key"], record["entity_key"]): record
        for record in document["records"]
        if record["module_key"] == "payments"
    }
    expected_timestamp = mysql_timestamp(
        normalize_utc_timestamp(document["generated_at"])
    )

    connection = pymysql.connect(
        **connection_options(),
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS n, COUNT(DISTINCT `data_version`) AS versions, "
                f"COUNT(DISTINCT `generated_at`) AS timestamps FROM `{TABLE}`"
            )
            totals = cursor.fetchone()
            cursor.execute(
                f"SELECT `module_key`, `entity_key`, `payload_json`, "
                f"`data_version`, `generated_at` FROM `{TABLE}` "
                f"WHERE `module_key` = %s ORDER BY `entity_key`",
                ("payments",),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    actual_payments = {
        (row["module_key"], row["entity_key"]): row for row in rows
    }
    missing = sorted(set(expected_payments) - set(actual_payments))
    extra = sorted(set(actual_payments) - set(expected_payments))
    mismatches = []
    for key in sorted(set(expected_payments) & set(actual_payments)):
        actual = actual_payments[key]
        try:
            actual_payload = json.loads(actual["payload_json"])
        except (TypeError, json.JSONDecodeError):
            mismatches.append(key)
            continue
        if (
            actual_payload != expected_payments[key]["payload"]
            or actual["data_version"] != document["data_version"]
            or mysql_timestamp(actual["generated_at"]) != expected_timestamp
        ):
            mismatches.append(key)

    result = {
        "status": "PASS"
        if not missing
        and not extra
        and not mismatches
        and totals["n"] == len(document["records"])
        and totals["versions"] == 1
        and totals["timestamps"] == 1
        else "FAIL",
        "total_rows": totals["n"],
        "expected_total_rows": len(document["records"]),
        "payment_rows": len(rows),
        "expected_payment_rows": len(expected_payments),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "payload_mismatch_count": len(mismatches),
        "distinct_data_versions": totals["versions"],
        "distinct_generated_at": totals["timestamps"],
        "data_version": document["data_version"],
        "generated_at": document["generated_at"],
        "empty_combination_count": sum(
            not record["payload"]["metrics"]
            for record in expected_payments.values()
        ),
    }
    if result["status"] != "PASS":
        raise AssertionError(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.snapshot), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
