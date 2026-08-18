"""Validate and transactionally replace the complete analytics snapshot."""

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

from shared.analytics_snapshot_contract import (  # noqa: E402
    normalize_utc_timestamp,
    validate_snapshot_document,
)


TABLE = "analysis_snapshot_result"


def load_snapshot(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return validate_snapshot_document(document)


def connection_options() -> dict[str, Any]:
    result = {
        "host": os.getenv("MYSQL_HOST"), "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"), "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE"),
    }
    missing = [name for name in ("host", "user", "database") if not result[name]]
    if missing:
        raise ValueError("缺少 MySQL 环境变量: " + ", ".join(name.upper() for name in missing))
    return result


def publish(document: dict[str, Any]) -> None:
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as error:
        raise RuntimeError("执行 --apply 前请安装 PyMySQL") from error
    connection = pymysql.connect(
        **connection_options(), charset="utf8mb4", cursorclass=DictCursor,
        autocommit=False, connect_timeout=5, read_timeout=10, write_timeout=10,
    )
    generated_at = normalize_utc_timestamp(document["generated_at"])
    generated_at = generated_at.removesuffix("Z").replace("T", " ")
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM `{TABLE}`")
            cursor.executemany(
                f"INSERT INTO `{TABLE}` (`module_key`,`entity_key`,`payload_json`,`data_version`,`generated_at`) VALUES (%s,%s,%s,%s,%s)",
                [
                    (record["module_key"], record["entity_key"], json.dumps(record["payload"], ensure_ascii=False), document["data_version"], generated_at)
                    for record in document["records"]
                ],
            )
            cursor.execute(
                f"SELECT COUNT(*) AS n, COUNT(DISTINCT `data_version`) AS versions, "
                f"COUNT(DISTINCT `generated_at`) AS timestamps FROM `{TABLE}`"
            )
            row = cursor.fetchone()
            if (
                row["n"] != len(document["records"])
                or row["versions"] != 1
                or row["timestamps"] != 1
            ):
                raise ValueError("发布后快照完整性校验失败")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    document = load_snapshot(args.input)
    if args.apply:
        publish(document)
    print(json.dumps({"status": "PASS", "mode": "mysql" if args.apply else "dry-run", "rows": len(document["records"]), "data_version": document["data_version"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
