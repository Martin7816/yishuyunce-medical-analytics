"""Read-only verification of the current MySQL snapshot against acceptance metadata."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.snapshot_acceptance import (  # noqa: E402
    DEFAULT_METADATA_PATH,
    active_snapshot_baseline,
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


def verify(metadata_path: Path | str | None = None) -> dict[str, Any]:
    """Check only metadata and read-only snapshot facts from MySQL."""

    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as error:
        raise RuntimeError("执行 MySQL 核对前请安装 PyMySQL") from error

    baseline = active_snapshot_baseline(metadata_path)
    options = connection_options()
    connection = pymysql.connect(
        **options,
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT VERSION() AS mysql_version, DATABASE() AS database_name, "
                f"COUNT(*) AS snapshot_rows, "
                f"COUNT(DISTINCT `data_version`) AS data_versions, "
                f"COUNT(DISTINCT `generated_at`) AS generated_timestamps, "
                f"MIN(`data_version`) AS min_data_version, "
                f"MAX(`data_version`) AS max_data_version "
                f"FROM `{TABLE}`"
            )
            totals = cursor.fetchone()
    finally:
        connection.close()

    actual_data_version = (
        totals["min_data_version"]
        if totals["data_versions"] == 1
        else None
    )
    database_match = totals["database_name"] == options["database"]
    row_count_match = totals["snapshot_rows"] == baseline["snapshot_rows"]
    data_version_match = actual_data_version == baseline["data_version"]
    passed = (
        database_match
        and row_count_match
        and totals["data_versions"] == 1
        and totals["generated_timestamps"] == 1
        and data_version_match
    )
    result = {
        "status": "PASS" if passed else "FAIL",
        "baseline_id": baseline["baseline_id"],
        "analytics_rules_version": baseline["analytics_rules_version"],
        "reason": baseline["reason"],
        "expected_snapshot_rows": baseline["snapshot_rows"],
        "actual_snapshot_rows": totals["snapshot_rows"],
        "row_count_match": row_count_match,
        "source_sha256": baseline["source_sha256"],
        "expected_data_version": baseline["data_version"],
        "actual_data_version": actual_data_version,
        "data_version_match": data_version_match,
        "distinct_data_versions": totals["data_versions"],
        "distinct_generated_at": totals["generated_timestamps"],
        "mysql_version": totals["mysql_version"],
        "database": totals["database_name"],
        "database_match": database_match,
    }
    if not passed:
        raise AssertionError(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only snapshot acceptance precheck"
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help="versioned snapshot acceptance metadata JSON",
    )
    args = parser.parse_args()
    print(json.dumps(verify(args.metadata), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
