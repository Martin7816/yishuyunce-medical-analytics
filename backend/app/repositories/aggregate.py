"""Read-only backend access to the active internal aggregate batch.

This repository exposes batch metadata and server-side grouped sums only.  It
has no raw-fact row reader and is not registered as an HTTP route.  Future
query tooling must apply privacy validation to the returned final groups before
constructing Safe Evidence.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from shared.aggregate_contract import (
    AGGREGATE_ACTIVE_BATCH_TABLE,
    AGGREGATE_BATCH_TABLE,
    AGGREGATE_FACT_TABLE,
    AGGREGATE_GRAIN,
    AGGREGATE_MEASURES,
    AggregateContractError,
    validate_aggregate_batch_manifest,
)

from ..errors import (
    DatabaseUnavailableError,
    InvalidServiceResultError,
    ResultNotReadyError,
    ServerMisconfiguredError,
)


ACTIVE_BATCH_QUERY = f"""
SELECT
    b.`batch_id`, b.`data_version`, b.`formula_version`, b.`registry_version`,
    b.`suppression_policy_version`, b.`suppression_policy_json`,
    b.`grain_json`, b.`measures_json`, b.`input_file_name`, b.`source_sha256`,
    b.`raw_records`, b.`source_records`, b.`aggregate_rows`, b.`status`,
    b.`generated_at`, b.`validated_at`, b.`activated_at`
FROM `{AGGREGATE_ACTIVE_BATCH_TABLE}` AS a
JOIN `{AGGREGATE_BATCH_TABLE}` AS b
  ON b.`batch_id` = a.`batch_id`
WHERE a.`singleton_id` = 1 AND b.`status` = 'ACTIVE'
LIMIT 1
""".strip()


class DisabledAggregateRepository:
    """Fail closed when the internal aggregate source is not configured."""

    def fetch_active_batch(self) -> dict[str, Any]:
        raise ServerMisconfiguredError()

    def aggregate(
        self,
        group_by: Sequence[str] = (),
        filters: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        raise ServerMisconfiguredError()


class MySQLAggregateFactRepository:
    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config

    def _connection_options(self) -> dict[str, Any]:
        required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE")
        if any(not self.config.get(key) for key in required):
            raise ServerMisconfiguredError()
        timeout = self.config.get("MYSQL_CONNECT_TIMEOUT", 3)
        return {
            "host": self.config["MYSQL_HOST"],
            "port": self.config.get("MYSQL_PORT", 3306),
            "user": self.config["MYSQL_USER"],
            "password": self.config.get("MYSQL_PASSWORD", ""),
            "database": self.config["MYSQL_DATABASE"],
            "charset": "utf8mb4",
            "connect_timeout": timeout,
            "read_timeout": timeout,
            "write_timeout": timeout,
            "autocommit": True,
        }

    @staticmethod
    def _decode_json(value: Any) -> Any:
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        if isinstance(value, str):
            return json.loads(value)
        return value

    def _connect(self):
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as error:
            raise ServerMisconfiguredError() from error
        try:
            return pymysql.connect(
                **self._connection_options(), cursorclass=DictCursor
            )
        except ServerMisconfiguredError:
            raise
        except pymysql.MySQLError as error:
            raise DatabaseUnavailableError() from error

    def _manifest_from_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        try:
            manifest = {
                "contract": "sparcs_aggregate_batch",
                "contract_version": 1,
                "batch_id": row["batch_id"],
                "data_version": row["data_version"],
                "formula_version": row["formula_version"],
                "registry_version": row["registry_version"],
                "suppression_policy_version": row["suppression_policy_version"],
                "suppression_policy": self._decode_json(row["suppression_policy_json"]),
                "grain": self._decode_json(row["grain_json"]),
                "measures": self._decode_json(row["measures_json"]),
                "input_file_name": row["input_file_name"],
                "source_sha256": row["source_sha256"],
                "raw_records": row["raw_records"],
                "source_records": row["source_records"],
                "aggregate_rows": row["aggregate_rows"],
                "generated_at": row["generated_at"],
                "status": row["status"],
            }
            return validate_aggregate_batch_manifest(manifest)
        except (AggregateContractError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise InvalidServiceResultError() from error

    def _fetch_active_batch_with_cursor(self, cursor: Any) -> dict[str, Any]:
        cursor.execute(ACTIVE_BATCH_QUERY)
        row = cursor.fetchone()
        if not row:
            raise ResultNotReadyError("aggregate batch")
        return self._manifest_from_row(row)

    def fetch_active_batch(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                return self._fetch_active_batch_with_cursor(cursor)
        except (ServerMisconfiguredError, ResultNotReadyError, InvalidServiceResultError):
            raise
        except Exception as error:
            try:
                import pymysql
            except ImportError:
                raise ServerMisconfiguredError() from error
            if isinstance(error, pymysql.MySQLError):
                raise DatabaseUnavailableError() from error
            raise
        finally:
            connection.close()

    @staticmethod
    def _validate_group_by(group_by: Sequence[str]) -> tuple[str, ...]:
        values = tuple(group_by)
        if len(set(values)) != len(values):
            raise ValueError("group_by cannot contain duplicate dimensions")
        unknown = set(values) - set(AGGREGATE_GRAIN)
        if unknown:
            raise ValueError("unknown aggregate dimensions: " + ", ".join(sorted(unknown)))
        return values

    @staticmethod
    def _validate_filters(filters: Mapping[str, str] | None) -> dict[str, str]:
        if filters is None:
            return {}
        if not isinstance(filters, Mapping):
            raise ValueError("filters must be a mapping")
        unknown = set(filters) - set(AGGREGATE_GRAIN)
        if unknown:
            raise ValueError("unknown aggregate filters: " + ", ".join(sorted(unknown)))
        if any(not isinstance(value, str) for value in filters.values()):
            raise ValueError("aggregate filter values must be strings")
        return dict(filters)

    def aggregate(
        self,
        group_by: Sequence[str] = (),
        filters: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Return grouped additive sums for the active batch, never raw rows."""

        dimensions = self._validate_group_by(group_by)
        selected_filters = self._validate_filters(filters)
        selected = [f"f.`{field}`" for field in dimensions]
        selected.extend(
            f"SUM(f.`{measure}`) AS `{measure}`" for measure in AGGREGATE_MEASURES
        )
        query = f"""
SELECT {', '.join(selected)}
FROM `{AGGREGATE_FACT_TABLE}` AS f
JOIN `{AGGREGATE_ACTIVE_BATCH_TABLE}` AS a
  ON a.`singleton_id` = 1 AND a.`batch_id` = f.`batch_id`
JOIN `{AGGREGATE_BATCH_TABLE}` AS b
  ON b.`batch_id` = f.`batch_id` AND b.`status` = 'ACTIVE'
WHERE b.`batch_id` = %s
"""
        params: list[Any] = []
        for field, value in selected_filters.items():
            query += f"AND f.`{field}` = %s\n"
            params.append(value)
        group_by_sql = ", ".join(f"f.`{field}`" for field in dimensions)
        if dimensions:
            query += f"GROUP BY {group_by_sql}\n"
        # The batch id is deliberately bound after query construction so a
        # future caller cannot turn a dimension name into SQL.
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                batch = self._fetch_active_batch_with_cursor(cursor)
                # Move the batch placeholder to the front of the parameter list.
                cursor.execute(query, (batch["batch_id"], *params))
                rows = [dict(row) for row in cursor.fetchall()]
            return {"batch": batch, "rows": rows}
        except (ServerMisconfiguredError, ResultNotReadyError, InvalidServiceResultError, ValueError):
            raise
        except Exception as error:
            try:
                import pymysql
            except ImportError:
                raise ServerMisconfiguredError() from error
            if isinstance(error, pymysql.MySQLError):
                raise DatabaseUnavailableError() from error
            raise
        finally:
            connection.close()


def build_aggregate_repository(config: Mapping[str, Any]):
    source = str(config.get("AGGREGATE_DATA_SOURCE") or "").lower()
    if source == "mysql":
        return MySQLAggregateFactRepository(config)
    return DisabledAggregateRepository()
