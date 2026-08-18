"""Validate and transactionally replace the complete analytics snapshot."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


TABLE = "analysis_snapshot_result"


def load_snapshot(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    version = document.get("data_version")
    generated_at = document.get("generated_at")
    records = document.get("records")
    if not isinstance(version, str) or not version or not version.isascii():
        raise ValueError("data_version 必须是非空 ASCII 字符串")
    if not isinstance(generated_at, str):
        raise ValueError("generated_at 必须是 ISO-8601 字符串")
    datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    if not isinstance(records, list) or not records:
        raise ValueError("records 必须是非空数组")
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("每条快照必须是对象")
        key = (record.get("module_key"), record.get("entity_key"))
        payload = record.get("payload")
        if not all(isinstance(value, str) and value for value in key):
            raise ValueError("module_key/entity_key 不能为空")
        if key in seen:
            raise ValueError(f"快照主键重复: {key}")
        if not isinstance(payload, dict) or not isinstance(payload.get("metrics", []), list) or not isinstance(payload.get("sections", []), list):
            raise ValueError(f"payload 结构无效: {key}")
        seen.add(key)
    return document


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
    generated_at = document["generated_at"].replace("Z", "").replace("T", " ")
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
            cursor.execute(f"SELECT COUNT(*) AS n, COUNT(DISTINCT `data_version`) AS versions FROM `{TABLE}`")
            row = cursor.fetchone()
            if row["n"] != len(document["records"]) or row["versions"] != 1:
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
