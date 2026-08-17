"""Read-only repositories for the validated TOP10 service result."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import (
    DatabaseUnavailableError,
    ResultNotReadyError,
    ServerMisconfiguredError,
)


MYSQL_QUERY = """
SELECT `rank`, `diagnosis_name`, `case_count`, `unit`,
       `data_version`, `generated_at`
FROM `disease_case_count_top10_result`
ORDER BY `rank` ASC
LIMIT 10
""".strip()


class FixtureDiseaseTop10Repository:
    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    def fetch(self) -> dict:
        try:
            with self.fixture_path.open("r", encoding="utf-8") as fixture_file:
                return json.load(fixture_file)
        except (OSError, json.JSONDecodeError) as error:
            raise ServerMisconfiguredError() from error


class MySQLDiseaseTop10Repository:
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

    def fetch(self) -> dict:
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
                    cursor.execute(MYSQL_QUERY)
                    rows = cursor.fetchall()
            finally:
                connection.close()
        except ServerMisconfiguredError:
            raise
        except pymysql.MySQLError as error:
            raise DatabaseUnavailableError() from error

        if not rows:
            # Issue #9 does not publish empty batches. An empty production table
            # therefore means that no validated result is ready.
            raise ResultNotReadyError()

        first = rows[0]
        return {
            "metric": "disease_case_count_top10",
            "unit": first["unit"],
            "data_version": first["data_version"],
            "generated_at": first["generated_at"],
            "items": [
                {
                    "rank": row["rank"],
                    "diagnosis_name": row["diagnosis_name"],
                    "case_count": row["case_count"],
                }
                for row in rows
            ],
            "_row_metadata": [
                {
                    "unit": row["unit"],
                    "data_version": row["data_version"],
                    "generated_at": row["generated_at"],
                }
                for row in rows
            ],
        }


def build_repository(config: dict):
    source = str(config.get("TOP10_DATA_SOURCE", "fixture")).lower()
    if source == "mysql":
        return MySQLDiseaseTop10Repository(config)

    if source == "fixture":
        state = str(config.get("TOP10_FIXTURE_STATE", "success")).lower()
        if state not in {"success", "empty"}:
            return FixtureDiseaseTop10Repository(Path("__invalid_fixture_state__"))
        fixture_path = (
            Path(config["APP_ROOT"])
            / "fixtures"
            / f"disease_top10_{state}.json"
        )
        return FixtureDiseaseTop10Repository(fixture_path)

    return FixtureDiseaseTop10Repository(Path("__invalid_data_source__"))
