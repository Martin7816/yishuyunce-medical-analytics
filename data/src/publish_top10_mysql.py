"""Validate and publish a generated TOP10 service-result artifact to MySQL.

The script never reads the raw CSV and never computes the metric.  The only
input is the small JSON artifact produced by ``run_sparcs_top10_pyspark.py``.
By default it performs validation only; ``--apply`` is required for the
transactional MySQL replacement.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TABLE_NAME = "disease_case_count_top10_result"
EXPECTED_METRIC = "disease_case_count_top10"
EXPECTED_UNIT = "discharge_records"


def normalize_generated_at(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("generated_at 必须是 ISO-8601 字符串")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("generated_at 必须包含时区")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def normalize_mysql_generated_at(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace(" ", "T"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def load_service_result(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    result = document.get("service_result", document)
    if not isinstance(result, dict):
        raise ValueError("JSON 中缺少 service_result 对象")

    if result.get("metric") != EXPECTED_METRIC:
        raise ValueError("metric 不符合 TOP10 契约")
    if result.get("unit") != EXPECTED_UNIT:
        raise ValueError("unit 不符合 TOP10 契约")

    data_version = result.get("data_version")
    if not isinstance(data_version, str) or not data_version:
        raise ValueError("data_version 不能为空")
    try:
        data_version.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("data_version 必须是 ASCII") from error

    generated_at = normalize_generated_at(result.get("generated_at"))
    items = result.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        raise ValueError("service_result.items 必须包含 1—10 项")

    names: set[str] = set()
    normalized_items: list[dict[str, Any]] = []
    previous_sort_key: tuple[int, str] | None = None
    for expected_rank, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError("TOP10 项必须是对象")
        rank = item.get("rank")
        name = item.get("diagnosis_name")
        count = item.get("case_count")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank != expected_rank:
            raise ValueError("rank 必须从 1 连续递增")
        if not isinstance(name, str) or not name or len(name) > 255:
            raise ValueError("diagnosis_name 不能为空且不能超过 255 字符")
        if name in names:
            raise ValueError("diagnosis_name 不能重复")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("case_count 必须是正整数")
        sort_key = (-count, name)
        if previous_sort_key is not None and sort_key < previous_sort_key:
            raise ValueError("结果不符合病例量降序、名称升序规则")
        previous_sort_key = sort_key
        names.add(name)
        normalized_items.append(
            {"rank": rank, "diagnosis_name": name, "case_count": count}
        )

    return {
        "metric": EXPECTED_METRIC,
        "unit": EXPECTED_UNIT,
        "data_version": data_version,
        "generated_at": generated_at,
        "items": normalized_items,
    }


def connection_options() -> dict[str, Any]:
    required = {
        "host": os.getenv("MYSQL_HOST"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE"),
    }
    missing = [name for name in ("host", "user", "database") if not required[name]]
    if missing:
        missing_names = ", ".join("MYSQL_" + name.upper() for name in missing)
        raise ValueError(f"缺少 MySQL 环境变量: {missing_names}")
    return required


def validate_published_rows(cursor: Any, expected: dict[str, Any]) -> None:
    cursor.execute(
        f"""
        SELECT COUNT(*) AS row_count,
               MIN(`rank`) AS min_rank,
               MAX(`rank`) AS max_rank,
               COUNT(DISTINCT `rank`) AS distinct_rank_count,
               MIN(`unit`) AS unit_value,
               COUNT(DISTINCT `unit`) AS unit_count,
               MIN(`data_version`) AS version_value,
               COUNT(DISTINCT `data_version`) AS version_count,
               MIN(`generated_at`) AS generated_at_value,
               COUNT(DISTINCT `generated_at`) AS generated_at_count
        FROM `{TABLE_NAME}`
        """
    )
    row = cursor.fetchone()
    expected_row_count = len(expected["items"])
    if (
        row["row_count"] != expected_row_count
        or row["min_rank"] != 1
        or row["max_rank"] != expected_row_count
        or row["distinct_rank_count"] != expected_row_count
        or row["unit_value"] != expected["unit"]
        or row["unit_count"] != 1
        or str(row["version_value"]) != expected["data_version"]
        or row["version_count"] != 1
        or normalize_mysql_generated_at(row["generated_at_value"])
        != expected["generated_at"]
        or row["generated_at_count"] != 1
    ):
        raise ValueError("MySQL 服务结果批次完整性检查失败")

    cursor.execute(
        f"""
        SELECT `rank`, `diagnosis_name`, `case_count`, `unit`,
               `data_version`, `generated_at`
        FROM `{TABLE_NAME}`
        ORDER BY `rank` ASC
        """
    )
    actual_rows = cursor.fetchall()
    expected_rows = [
        {
            "rank": item["rank"],
            "diagnosis_name": item["diagnosis_name"],
            "case_count": item["case_count"],
            "unit": expected["unit"],
            "data_version": expected["data_version"],
            "generated_at": expected["generated_at"],
        }
        for item in expected["items"]
    ]
    normalized_rows = [
        {
            "rank": item["rank"],
            "diagnosis_name": item["diagnosis_name"],
            "case_count": item["case_count"],
            "unit": item["unit"],
            "data_version": item["data_version"],
            "generated_at": normalize_mysql_generated_at(item["generated_at"]),
        }
        for item in actual_rows
    ]
    if normalized_rows != expected_rows:
        raise ValueError("MySQL 服务结果行与待发布工件不一致")


def publish(expected: dict[str, Any]) -> None:
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as error:
        raise RuntimeError("执行 --apply 前请安装 PyMySQL") from error

    connection = pymysql.connect(
        **connection_options(),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=int(os.getenv("MYSQL_CONNECT_TIMEOUT", "5")),
        read_timeout=int(os.getenv("MYSQL_CONNECT_TIMEOUT", "5")),
        write_timeout=int(os.getenv("MYSQL_CONNECT_TIMEOUT", "5")),
    )
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM `{TABLE_NAME}`")
            cursor.executemany(
                f"""
                INSERT INTO `{TABLE_NAME}`
                    (`rank`, `diagnosis_name`, `case_count`, `unit`,
                     `data_version`, `generated_at`)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        item["rank"],
                        item["diagnosis_name"],
                        item["case_count"],
                        expected["unit"],
                        expected["data_version"],
                        expected["generated_at"].replace("Z", "").replace("T", " "),
                    )
                    for item in expected["items"]
                ],
            )
            validate_published_rows(cursor, expected)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="在 MySQL 中执行事务刷新；默认只做本地契约校验",
    )
    args = parser.parse_args()

    service_result = load_service_result(args.input)
    if args.apply:
        publish(service_result)

    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": "mysql" if args.apply else "dry-run",
                "table": TABLE_NAME,
                "rows": len(service_result["items"]),
                "data_version": service_result["data_version"],
                "generated_at": service_result["generated_at"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
