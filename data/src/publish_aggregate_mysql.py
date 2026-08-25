"""Stage and validate internal aggregate facts in MySQL.

The publisher never creates tables.  ``data/sql/003-aggregate-fact.sql`` is a
separate reviewed schema artifact.  A caller must explicitly opt into the
database write, and activation is a second explicit choice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.aggregate_contract import (  # noqa: E402
    AGGREGATE_ACTIVE_BATCH_TABLE,
    AGGREGATE_BATCH_TABLE,
    AGGREGATE_FACT_TABLE,
    AGGREGATE_GRAIN,
    AGGREGATE_MEASURES,
    AggregateContractError,
    validate_aggregate_reconciliation,
    validate_aggregate_batch_manifest,
    validate_aggregate_fact_row,
    validate_source_sha256,
    validate_status_transition,
)


INSERT_BATCH_SIZE = 1000
MIN_MYSQL_VERSION = (8, 0, 16)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AggregateContractError("aggregate manifest cannot be read") from error
    return validate_aggregate_batch_manifest(document)


def _json_fact_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(
            candidate
            for candidate in path.rglob("*.json")
            if candidate.is_file() and candidate.name != "_SUCCESS"
        )
    raise AggregateContractError("aggregate fact path does not exist")


def iter_fact_rows(path: Path) -> Iterator[dict[str, Any]]:
    """Stream Spark JSON part files without collecting the fact in memory."""

    for file_path in _json_fact_files(path):
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise AggregateContractError(
                            f"invalid fact JSON at {file_path}:{line_number}"
                        ) from error
                    yield validate_aggregate_fact_row(row)
        except OSError as error:
            raise AggregateContractError(f"aggregate fact cannot be read: {file_path}") from error


def parse_mysql_version(value: Any) -> tuple[int, int, int]:
    """Parse a MySQL server version and reject unknown/ MariaDB variants."""

    if not isinstance(value, str) or "mariadb" in value.lower():
        raise AggregateContractError("MySQL 8.0.16 or newer is required")
    match = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)", value)
    if match is None:
        raise AggregateContractError("MySQL server version cannot be determined")
    version = tuple(int(part) for part in match.groups())
    if version < MIN_MYSQL_VERSION:
        raise AggregateContractError("MySQL 8.0.16 or newer is required")
    return version


def _validate_mysql_version(connection: Any) -> tuple[int, int, int]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION() AS `version`")
        row = cursor.fetchone()
    if isinstance(row, dict):
        value = row.get("version")
    elif isinstance(row, (tuple, list)) and row:
        value = row[0]
    else:
        value = None
    return parse_mysql_version(value)


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise AggregateContractError("aggregate source file cannot be read") from error
    return digest.hexdigest()


def validate_source_file(path: Path, manifest: dict[str, Any]) -> str:
    """Verify the candidate manifest against the exact source file."""

    path = Path(path)
    if not path.is_file():
        raise AggregateContractError("aggregate source file does not exist")
    if path.name != manifest["input_file_name"]:
        raise AggregateContractError("aggregate source filename does not match manifest")
    return validate_source_sha256(manifest["source_sha256"], _source_sha256(path))


def summarize_candidate(
    manifest: dict[str, Any],
    rows: Iterable[dict[str, Any]],
    *,
    source_path: Path | None = None,
) -> dict[str, int | str]:
    manifest = validate_aggregate_batch_manifest(manifest)
    if source_path is not None:
        validate_source_file(source_path, manifest)
    row_count = 0
    source_records = 0
    for row in rows:
        validated = validate_aggregate_fact_row(row)
        row_count += 1
        source_records += validated["record_count"]
    validate_aggregate_reconciliation(
        source_scope_row_count=manifest["source_records"],
        aggregate_row_count=manifest["aggregate_rows"],
        fact_row_count=row_count,
        fact_record_count=source_records,
    )
    return {
        "batch_id": manifest["batch_id"],
        "data_version": manifest["data_version"],
        "aggregate_rows": row_count,
        "source_records": source_records,
    }


def connection_options(config: dict[str, Any] | None = None) -> dict[str, Any]:
    values = config or os.environ
    required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE")
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise ValueError("missing MySQL configuration: " + ", ".join(missing))
    return {
        "host": values["MYSQL_HOST"],
        "port": int(values.get("MYSQL_PORT", 3306)),
        "user": values["MYSQL_USER"],
        "password": values.get("MYSQL_PASSWORD", ""),
        "database": values["MYSQL_DATABASE"],
        "charset": "utf8mb4",
        "connect_timeout": int(values.get("MYSQL_CONNECT_TIMEOUT", 3)),
        "read_timeout": int(values.get("MYSQL_CONNECT_TIMEOUT", 3)),
        "write_timeout": int(values.get("MYSQL_CONNECT_TIMEOUT", 3)),
        "autocommit": False,
    }


def _connect(config: dict[str, Any] | None = None):
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as error:
        raise RuntimeError("PyMySQL is required for aggregate publishing") from error
    return pymysql.connect(**connection_options(config), cursorclass=DictCursor)


def _generated_at_sql(value: str) -> str:
    return value.removesuffix("Z").replace("T", " ")


def _batch_values(manifest: dict[str, Any]) -> tuple[Any, ...]:
    return (
        manifest["batch_id"],
        manifest["data_version"],
        manifest["formula_version"],
        manifest["registry_version"],
        manifest["suppression_policy_version"],
        json.dumps(manifest["suppression_policy"], ensure_ascii=False),
        json.dumps(manifest["grain"], ensure_ascii=False),
        json.dumps(manifest["measures"], ensure_ascii=False),
        manifest["input_file_name"],
        manifest["source_sha256"],
        manifest["raw_records"],
        manifest["source_records"],
        manifest["aggregate_rows"],
        "STAGING",
        _generated_at_sql(manifest["generated_at"]),
    )


def _fact_values(batch_id: str, row: dict[str, Any]) -> tuple[Any, ...]:
    return (batch_id, *(row[field] for field in AGGREGATE_GRAIN), *(row[field] for field in AGGREGATE_MEASURES))


def _transition_batch_status(
    cursor: Any,
    batch_id: str,
    current_status: str,
    target_status: str,
    *,
    rollback: bool = False,
) -> None:
    """Apply one explicitly validated batch status transition."""

    validate_status_transition(
        current_status,
        target_status,
        rollback=rollback,
    )
    assignments = ["`status` = %s"]
    values: list[Any] = [target_status]
    if target_status == "VALIDATED":
        assignments.append("`validated_at` = UTC_TIMESTAMP(6)")
    elif target_status == "ACTIVE":
        assignments.append("`activated_at` = UTC_TIMESTAMP(6)")
    cursor.execute(
        f"""
UPDATE `{AGGREGATE_BATCH_TABLE}`
SET {', '.join(assignments)}
WHERE `batch_id` = %s AND `status` = %s
""".strip(),
        (*values, batch_id, current_status),
    )
    if getattr(cursor, "rowcount", 1) != 1:
        raise AggregateContractError(
            f"aggregate status transition failed: {current_status} -> {target_status}"
        )


def _fetch_batch(cursor: Any, batch_id: str) -> dict[str, Any]:
    cursor.execute(
        f"""
SELECT `batch_id`, `data_version`, `formula_version`, `registry_version`,
       `suppression_policy_version`, `suppression_policy_json`, `grain_json`,
       `measures_json`, `status`
FROM `{AGGREGATE_BATCH_TABLE}`
WHERE `batch_id` = %s
FOR UPDATE
""".strip(),
        (batch_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise AggregateContractError(f"aggregate batch does not exist: {batch_id}")
    return dict(row)


def _fetch_active_pointer(cursor: Any) -> dict[str, Any] | None:
    cursor.execute(
        f"""
SELECT `batch_id`
FROM `{AGGREGATE_ACTIVE_BATCH_TABLE}`
WHERE `singleton_id` = 1
FOR UPDATE
""".strip()
    )
    pointer = cursor.fetchone()
    if not pointer:
        return None
    batch_id = pointer["batch_id"]
    return {"batch_id": batch_id, "batch": _fetch_batch(cursor, batch_id)}


def _fetch_active_batches(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        f"""
SELECT `batch_id`, `status`
FROM `{AGGREGATE_BATCH_TABLE}`
WHERE `status` = 'ACTIVE'
FOR UPDATE
""".strip()
    )
    return [dict(row) for row in (cursor.fetchall() or [])]


def _assert_active_invariant(
    pointer: dict[str, Any] | None,
    active_batches: list[dict[str, Any]],
) -> None:
    active_ids = {row["batch_id"] for row in active_batches}
    if len(active_ids) > 1:
        raise AggregateContractError("multiple ACTIVE aggregate batches detected")
    if pointer is None:
        if active_ids:
            raise AggregateContractError("ACTIVE aggregate batch has no active pointer")
        return
    if pointer["batch"]["status"] != "ACTIVE":
        raise AggregateContractError("active pointer does not target an ACTIVE batch")
    if active_ids != {pointer["batch_id"]}:
        raise AggregateContractError("active pointer and ACTIVE batch are inconsistent")


def _decode_json_value(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return json.loads(value)
    return value


def _same_aggregate_identity(first: dict[str, Any], second: dict[str, Any]) -> bool:
    for field in (
        "formula_version",
        "registry_version",
        "suppression_policy_version",
    ):
        if first.get(field) != second.get(field):
            return False
    for field in (
        "suppression_policy_json",
        "grain_json",
        "measures_json",
    ):
        try:
            if _decode_json_value(first.get(field)) != _decode_json_value(second.get(field)):
                return False
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
    return True


def _fetch_fact_reconciliation(cursor: Any, batch_id: str) -> dict[str, int]:
    """Return database fact totals through a stable mapping contract."""

    cursor.execute(
        f"""
SELECT COUNT(*) AS `fact_rows`,
       COALESCE(SUM(`record_count`), 0) AS `record_count_sum`
FROM `{AGGREGATE_FACT_TABLE}`
WHERE `batch_id` = %s
""".strip(),
        (batch_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return {"fact_rows": 0, "record_count_sum": 0}
    if isinstance(row, dict):
        values = (row.get("fact_rows"), row.get("record_count_sum"))
    elif isinstance(row, (tuple, list)) and len(row) == 2:
        values = (row[0], row[1])
    else:
        raise AggregateContractError(
            "aggregate fact reconciliation returned an unsupported row type"
        )
    if any(value is None for value in values):
        raise AggregateContractError(
            "aggregate fact reconciliation returned incomplete totals"
        )
    try:
        return {
            "fact_rows": int(values[0]),
            "record_count_sum": int(values[1]),
        }
    except (TypeError, ValueError) as error:
        raise AggregateContractError(
            "aggregate fact reconciliation totals are not integers"
        ) from error


def _stage_and_validate(
    cursor: Any,
    manifest: dict[str, Any],
    rows: Iterable[dict[str, Any]],
) -> tuple[int, int]:
    cursor.execute(
        f"""
INSERT INTO `{AGGREGATE_BATCH_TABLE}`
    (`batch_id`, `data_version`, `formula_version`, `registry_version`,
     `suppression_policy_version`, `suppression_policy_json`, `grain_json`,
     `measures_json`, `input_file_name`, `source_sha256`, `raw_records`,
     `source_records`, `aggregate_rows`, `status`, `generated_at`)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
""".strip(),
        _batch_values(manifest),
    )
    insert_query = f"""
INSERT INTO `{AGGREGATE_FACT_TABLE}`
    (`batch_id`, {', '.join(f'`{field}`' for field in AGGREGATE_GRAIN)},
     {', '.join(f'`{field}`' for field in AGGREGATE_MEASURES)})
VALUES ({', '.join(['%s'] * (1 + len(AGGREGATE_GRAIN) + len(AGGREGATE_MEASURES)))})
""".strip()
    pending: list[tuple[Any, ...]] = []
    row_count = 0
    source_records = 0
    for row in rows:
        validated = validate_aggregate_fact_row(row)
        pending.append(_fact_values(manifest["batch_id"], validated))
        row_count += 1
        source_records += validated["record_count"]
        if len(pending) >= INSERT_BATCH_SIZE:
            cursor.executemany(insert_query, pending)
            pending.clear()
    if pending:
        cursor.executemany(insert_query, pending)
    validate_aggregate_reconciliation(
        source_scope_row_count=manifest["source_records"],
        aggregate_row_count=manifest["aggregate_rows"],
        fact_row_count=row_count,
        fact_record_count=source_records,
    )

    checked = _fetch_fact_reconciliation(cursor, manifest["batch_id"])
    checked_row_count = checked["fact_rows"]
    checked_source_records = checked["record_count_sum"]
    validate_aggregate_reconciliation(
        source_scope_row_count=manifest["source_records"],
        aggregate_row_count=manifest["aggregate_rows"],
        fact_row_count=checked_row_count,
        fact_record_count=checked_source_records,
    )
    _transition_batch_status(
        cursor,
        manifest["batch_id"],
        "STAGING",
        "VALIDATED",
    )
    return row_count, source_records


def _insert_active_pointer(cursor: Any, batch_id: str) -> None:
    cursor.execute(
        f"""
INSERT INTO `{AGGREGATE_ACTIVE_BATCH_TABLE}`
    (`singleton_id`, `batch_id`, `batch_status`, `activated_at`)
VALUES (1, %s, 'ACTIVE', UTC_TIMESTAMP(6))
""".strip(),
        (batch_id,),
    )


def _switch_active_batch(
    cursor: Any,
    batch_id: str,
    *,
    rollback: bool = False,
) -> bool:
    """Atomically switch the singleton pointer to an eligible batch.

    The pointer is deleted before status changes because the composite FK
    requires its target to remain ACTIVE.  The surrounding transaction makes
    the temporary no-pointer state uncommitted; any failure rolls back both
    the status changes and the pointer deletion.
    """

    target = _fetch_batch(cursor, batch_id)
    pointer = _fetch_active_pointer(cursor)
    active_batches = _fetch_active_batches(cursor)
    _assert_active_invariant(pointer, active_batches)

    if pointer and pointer["batch_id"] == batch_id:
        if target["status"] != "ACTIVE":
            raise AggregateContractError("active pointer target is not ACTIVE")
        return True

    if rollback:
        if pointer is None:
            raise AggregateContractError("cannot rollback without an ACTIVE batch")
        if not _same_aggregate_identity(pointer["batch"], target):
            raise AggregateContractError(
                "rollback batch is incompatible with the current aggregate identity"
            )
        expected_status = "RETIRED"
    else:
        expected_status = "VALIDATED"
    if target["status"] != expected_status:
        raise AggregateContractError(
            f"only {expected_status} batches can become ACTIVE"
        )

    if pointer:
        cursor.execute(
            f"""
DELETE FROM `{AGGREGATE_ACTIVE_BATCH_TABLE}`
WHERE `singleton_id` = 1
""".strip()
        )
        if getattr(cursor, "rowcount", 1) != 1:
            raise AggregateContractError("active pointer could not be removed")
        _transition_batch_status(
            cursor,
            pointer["batch_id"],
            "ACTIVE",
            "RETIRED",
        )

    _transition_batch_status(
        cursor,
        batch_id,
        expected_status,
        "ACTIVE",
        rollback=rollback,
    )
    _insert_active_pointer(cursor, batch_id)
    return False


def _activate(cursor: Any, batch_id: str) -> bool:
    return _switch_active_batch(cursor, batch_id)


def publish(
    manifest: dict[str, Any],
    rows: Iterable[dict[str, Any]],
    *,
    source_path: Path | None = None,
    config: dict[str, Any] | None = None,
    activate: bool = False,
    connection: Any | None = None,
) -> dict[str, Any]:
    """Stage and validate a candidate; activate only when explicitly asked."""

    manifest = validate_aggregate_batch_manifest(manifest)
    if manifest["status"] != "STAGING":
        raise AggregateContractError("only STAGING manifests can be published")
    if source_path is None:
        raise AggregateContractError(
            "source_path is required before an aggregate batch can be VALIDATED"
        )
    validate_source_file(source_path, manifest)
    own_connection = connection is None
    connection = connection or _connect(config)
    try:
        _validate_mysql_version(connection)
        connection.begin()
        with connection.cursor() as cursor:
            row_count, source_records = _stage_and_validate(cursor, manifest, rows)
            if activate:
                _activate(cursor, manifest["batch_id"])
        connection.commit()
        return {
            "status": "ACTIVE" if activate else "VALIDATED",
            "batch_id": manifest["batch_id"],
            "data_version": manifest["data_version"],
            "aggregate_rows": row_count,
            "source_records": source_records,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        if own_connection:
            connection.close()


def activate_existing(
    batch_id: str,
    *,
    config: dict[str, Any] | None = None,
    connection: Any | None = None,
) -> dict[str, Any]:
    """Activate an already VALIDATED batch without re-reading fact files."""

    own_connection = connection is None
    connection = connection or _connect(config)
    try:
        _validate_mysql_version(connection)
        connection.begin()
        with connection.cursor() as cursor:
            idempotent = _activate(cursor, batch_id)
        connection.commit()
        return {
            "status": "ACTIVE",
            "batch_id": batch_id,
            "idempotent": idempotent,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        if own_connection:
            connection.close()


def rollback_active_batch(
    previous_batch_id: str,
    *,
    config: dict[str, Any] | None = None,
    connection: Any | None = None,
) -> dict[str, Any]:
    """Restore a compatible RETIRED batch through the explicit rollback path."""

    own_connection = connection is None
    connection = connection or _connect(config)
    try:
        _validate_mysql_version(connection)
        connection.begin()
        with connection.cursor() as cursor:
            idempotent = _switch_active_batch(
                cursor,
                previous_batch_id,
                rollback=True,
            )
        connection.commit()
        return {
            "status": "ACTIVE",
            "batch_id": previous_batch_id,
            "rollback": True,
            "idempotent": idempotent,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        if own_connection:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--facts", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--activate-batch-id")
    parser.add_argument("--rollback-batch-id")
    args = parser.parse_args()
    operation_count = sum(
        value is not None
        for value in (args.activate_batch_id, args.rollback_batch_id)
    )
    if operation_count > 1:
        parser.error("choose only one batch activation operation")
    if operation_count:
        if not args.apply:
            parser.error("batch activation requires --apply")
        if args.manifest or args.facts or args.source or args.activate:
            parser.error("batch activation cannot republish a candidate")
        if args.activate_batch_id:
            summary = activate_existing(args.activate_batch_id)
        else:
            summary = rollback_active_batch(args.rollback_batch_id)
    else:
        if not args.manifest or not args.facts or not args.source:
            parser.error("--manifest, --facts, and --source are required")
        if args.activate and not args.apply:
            parser.error("--activate requires --apply")
        manifest = load_manifest(args.manifest)
        rows = iter_fact_rows(args.facts)
        if not args.apply:
            summary = summarize_candidate(
                manifest,
                rows,
                source_path=args.source,
            )
            summary["status"] = "DRY_RUN"
        else:
            summary = publish(
                manifest,
                rows,
                source_path=args.source,
                activate=args.activate,
            )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
