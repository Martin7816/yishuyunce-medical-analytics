"""Compare the published #71 data-quality row with a snapshot artifact."""

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

from shared.analytics_snapshot_contract import validate_snapshot_document


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
    expected_rows = [
        row
        for row in document["records"]
        if row["module_key"] == "data_quality"
        and row["entity_key"] == "summary"
    ]
    if len(expected_rows) != 1:
        raise ValueError("工件必须且只能包含一个 data_quality / summary")
    expected = expected_rows[0]
    expected_timestamp = mysql_timestamp(document["generated_at"])

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
                f"WHERE `module_key` = %s AND `entity_key` = %s",
                ("data_quality", "summary"),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    payload_match = False
    version_match = False
    timestamp_match = False
    if len(rows) == 1:
        actual = rows[0]
        payload_match = json.loads(actual["payload_json"]) == expected["payload"]
        version_match = actual["data_version"] == document["data_version"]
        timestamp_match = (
            mysql_timestamp(actual["generated_at"]) == expected_timestamp
        )

    passed = (
        totals["n"] == len(document["records"])
        and totals["versions"] == 1
        and totals["timestamps"] == 1
        and len(rows) == 1
        and payload_match
        and version_match
        and timestamp_match
    )
    result = {
        "status": "PASS" if passed else "FAIL",
        "total_rows": totals["n"],
        "expected_total_rows": len(document["records"]),
        "distinct_data_versions": totals["versions"],
        "distinct_generated_at": totals["timestamps"],
        "data_quality_rows": len(rows),
        "expected_data_quality_rows": 1,
        "payload_match": payload_match,
        "data_version_match": version_match,
        "generated_at_match": timestamp_match,
        "data_version": document["data_version"],
        "generated_at": document["generated_at"],
    }
    if not passed:
        raise AssertionError(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.snapshot), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
