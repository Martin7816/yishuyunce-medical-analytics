"""Adapters for immutable, versioned analytics snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from shared.analytics_snapshot_contract import validate_snapshot_document

from ..errors import (
    DatabaseUnavailableError,
    InvalidServiceResultError,
    ResultNotReadyError,
    ServerMisconfiguredError,
)


class FixtureAnalyticsSnapshotRepository:
    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path
        self._document: dict | None = None

    def _load(self) -> dict:
        if self._document is None:
            try:
                document = json.loads(self.fixture_path.read_text(encoding="utf-8"))
                self._document = validate_snapshot_document(document)
            except (OSError, json.JSONDecodeError, ValueError) as error:
                raise ServerMisconfiguredError() from error
        return self._document

    def fetch(self, module_key: str, entity_key: str) -> dict:
        document = self._load()
        for record in document.get("records", []):
            if (
                record.get("module_key") == module_key
                and record.get("entity_key") == entity_key
            ):
                return {
                    "payload": record.get("payload"),
                    "data_version": document.get("data_version"),
                    "generated_at": document.get("generated_at"),
                }
        raise ResultNotReadyError()


class MySQLAnalyticsSnapshotRepository:
    QUERY = """
SELECT `payload_json`, `data_version`, `generated_at`
FROM `analysis_snapshot_result`
WHERE `module_key` = %s AND `entity_key` = %s
LIMIT 1
""".strip()

    def __init__(self, config: dict) -> None:
        self.config = config

    def _connection_options(self) -> dict:
        required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE")
        if any(not self.config.get(key) for key in required):
            raise ServerMisconfiguredError()
        return {
            "host": self.config["MYSQL_HOST"],
            "port": self.config["MYSQL_PORT"],
            "user": self.config["MYSQL_USER"],
            "password": self.config.get("MYSQL_PASSWORD", ""),
            "database": self.config["MYSQL_DATABASE"],
            "charset": "utf8mb4",
            "connect_timeout": self.config["MYSQL_CONNECT_TIMEOUT"],
            "read_timeout": self.config["MYSQL_CONNECT_TIMEOUT"],
            "write_timeout": self.config["MYSQL_CONNECT_TIMEOUT"],
            "autocommit": True,
        }

    def fetch(self, module_key: str, entity_key: str) -> dict:
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as error:
            raise ServerMisconfiguredError() from error
        try:
            connection = pymysql.connect(
                **self._connection_options(), cursorclass=DictCursor
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute(self.QUERY, (module_key, entity_key))
                    row = cursor.fetchone()
            finally:
                connection.close()
        except ServerMisconfiguredError:
            raise
        except pymysql.MySQLError as error:
            raise DatabaseUnavailableError() from error
        if not row:
            raise ResultNotReadyError()
        payload = row["payload_json"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as error:
                # The connection and configuration are usable; the published
                # row itself is malformed and must use the contract error.
                raise InvalidServiceResultError() from error
        return {
            "payload": payload,
            "data_version": row["data_version"],
            "generated_at": row["generated_at"],
        }


def build_analytics_repository(config: dict):
    source = str(config.get("ANALYTICS_DATA_SOURCE") or "").lower()
    if source == "mysql":
        return MySQLAnalyticsSnapshotRepository(config)
    if source == "fixture":
        return FixtureAnalyticsSnapshotRepository(
            Path(config["APP_ROOT"]) / "fixtures" / "analytics_snapshot_success.json"
        )
    return FixtureAnalyticsSnapshotRepository(Path("__invalid_analytics_source__"))
