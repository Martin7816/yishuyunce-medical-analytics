from __future__ import annotations

import json
import hashlib
import copy
import sys
import tempfile
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DATA_ROOT / "src"))

from shared.aggregate_contract import (  # noqa: E402
    AGGREGATE_FORMULA_VERSION,
    AGGREGATE_MEASURES,
    AggregateContractError,
    build_aggregate_batch_manifest,
    build_batch_id,
    default_suppression_policy,
)
from publish_aggregate_mysql import (  # noqa: E402
    activate_existing,
    iter_fact_rows,
    publish,
    rollback_active_batch,
    parse_mysql_version,
    summarize_candidate,
    validate_source_file,
)
from shared.aggregate_registry import SEMANTIC_REGISTRY_VERSION  # noqa: E402


@pytest.fixture
def local_tmp_path():
    with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".tmp") as directory:
        yield Path(directory)


def _manifest(source_sha256="b" * 64):
    policy = default_suppression_policy()
    return build_aggregate_batch_manifest(
        batch_id=build_batch_id(
            "fixture:aggregate:v1",
            AGGREGATE_FORMULA_VERSION,
            SEMANTIC_REGISTRY_VERSION,
            policy["policy_version"],
        ),
        data_version="fixture:aggregate:v1",
        formula_version=AGGREGATE_FORMULA_VERSION,
        registry_version=SEMANTIC_REGISTRY_VERSION,
        suppression_policy=policy,
        input_file_name="sample.csv",
        source_sha256=source_sha256,
        raw_records=2,
        source_records=2,
        aggregate_rows=1,
        generated_at="2026-08-24T00:00:00Z",
    )


def _row():
    row = {
        "facility_id": "F001",
        "diagnosis_code": "RSP009",
        "age": "0 to 17",
        "gender": "F",
        "severity": "Major",
        "payment": "Medicare",
        "admission": "Emergency",
    }
    row.update(
        {
            "record_count": 2,
            "los_sum": 4,
            "los_valid_count": 2,
            "charges_sum": 100,
            "charges_valid_count": 2,
            "costs_sum": 50,
            "costs_valid_count": 2,
            "emergency_yes_count": 2,
            "emergency_valid_count": 2,
            "surgical_yes_count": 0,
            "surgical_valid_count": 2,
            "severe_yes_count": 2,
            "severe_valid_count": 2,
        }
    )
    assert set(row) == set(AGGREGATE_MEASURES) | {
        "facility_id", "diagnosis_code", "age", "gender", "severity", "payment", "admission"
    }
    return row


class FakeCursor:
    def __init__(self):
        self.executed = []
        self.inserted = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, args=None):
        self.executed.append((query, args))
        self.rowcount = 1

    def executemany(self, query, rows):
        self.inserted.extend(rows)

    def fetchone(self):
        query = self.executed[-1][0]
        if "SELECT VERSION()" in query:
            return {"version": "8.0.36"}
        if "COUNT(*) AS `fact_rows`" in query:
            return {"fact_rows": 1, "source_records": 2}
        if "FROM `analytics_aggregate_active_batch`" in query:
            return None
        if "SELECT `batch_id`, `data_version`" in query:
            return {
                "batch_id": "agg_fixture",
                "data_version": "fixture:aggregate:v1",
                "formula_version": "aggregate-additive-v1",
                "registry_version": "aggregate-registry-v1",
                "suppression_policy_version": "query-suppression-v1",
                "suppression_policy_json": json.dumps(default_suppression_policy()),
                "grain_json": json.dumps(
                    [
                        "facility_id", "diagnosis_code", "age", "gender",
                        "severity", "payment", "admission",
                    ]
                ),
                "measures_json": json.dumps(list(AGGREGATE_MEASURES)),
                "status": "VALIDATED",
            }
        return None

    def fetchall(self):
        query = self.executed[-1][0]
        if "WHERE `status` = 'ACTIVE'" in query:
            return []
        return []


class FakeConnection:
    def __init__(self):
        self.cursor_value = FakeCursor()
        self.committed = False
        self.rolled_back = False

    def begin(self):
        pass

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _db_batch(batch_id, status, *, data_version="fixture:aggregate:v1"):
    return {
        "batch_id": batch_id,
        "data_version": data_version,
        "formula_version": "aggregate-additive-v1",
        "registry_version": "aggregate-registry-v1",
        "suppression_policy_version": "query-suppression-v1",
        "suppression_policy_json": json.dumps(default_suppression_policy()),
        "grain_json": json.dumps(
            [
                "facility_id", "diagnosis_code", "age", "gender",
                "severity", "payment", "admission",
            ]
        ),
        "measures_json": json.dumps(list(AGGREGATE_MEASURES)),
        "status": status,
    }


class StatefulCursor:
    def __init__(self, connection):
        self.connection = connection
        self.executed = []
        self.rowcount = 1
        self.fetchone_value = None
        self.fetchall_value = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, args=None):
        self.executed.append((query, args))
        self.rowcount = 1
        self.fetchone_value = None
        self.fetchall_value = []
        if "SELECT VERSION()" in query:
            self.fetchone_value = {"version": "8.0.36"}
        elif "SELECT `batch_id`, `data_version`" in query:
            batch_id = args[0]
            self.fetchone_value = self.connection.batches.get(batch_id)
        elif "FROM `analytics_aggregate_active_batch`" in query:
            if self.connection.pointer is not None:
                self.fetchone_value = {"batch_id": self.connection.pointer}
        elif "SELECT `batch_id`, `status`" in query:
            self.fetchall_value = [
                {"batch_id": batch_id, "status": batch["status"]}
                for batch_id, batch in self.connection.batches.items()
                if batch["status"] == "ACTIVE"
            ]
        elif query.startswith("DELETE FROM `analytics_aggregate_active_batch`"):
            if self.connection.pointer is None:
                self.rowcount = 0
            else:
                self.connection.pointer = None
        elif query.startswith("UPDATE `analytics_aggregate_batch`"):
            target_status, batch_id, current_status = args
            batch = self.connection.batches.get(batch_id)
            if batch is None or batch["status"] != current_status:
                self.rowcount = 0
            else:
                batch["status"] = target_status
        elif query.startswith("INSERT INTO `analytics_aggregate_active_batch`"):
            if self.connection.fail_on_pointer_insert:
                raise RuntimeError("simulated pointer insert failure")
            self.connection.pointer = args[0]

    def executemany(self, query, rows):
        pass

    def fetchone(self):
        return self.fetchone_value

    def fetchall(self):
        return self.fetchall_value


class StatefulConnection:
    def __init__(self, batches, pointer=None, *, fail_on_pointer_insert=False):
        self.batches = copy.deepcopy(batches)
        self.pointer = pointer
        self.fail_on_pointer_insert = fail_on_pointer_insert
        self.committed = False
        self.rolled_back = False
        self._snapshot = None
        self.cursor_value = StatefulCursor(self)

    def begin(self):
        self._snapshot = (copy.deepcopy(self.batches), self.pointer)

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True
        if self._snapshot is not None:
            self.batches, self.pointer = self._snapshot

    def close(self):
        pass


def test_candidate_json_parts_are_streamed_and_validated(local_tmp_path):
    fact_dir = local_tmp_path / "facts"
    fact_dir.mkdir()
    (fact_dir / "part-00000.json").write_text(
        json.dumps(_row()) + "\n", encoding="utf-8"
    )
    summary = summarize_candidate(_manifest(), iter_fact_rows(fact_dir))
    assert summary["aggregate_rows"] == 1
    assert summary["source_records"] == 2


def test_publisher_stages_and_validates_without_activation(local_tmp_path):
    connection = FakeConnection()
    source = local_tmp_path / "sample.csv"
    source.write_bytes(b"sample")
    manifest = _manifest(hashlib.sha256(b"sample").hexdigest())
    result = publish(manifest, [_row()], source_path=source, connection=connection)
    assert result["status"] == "VALIDATED"
    assert connection.committed
    assert not connection.rolled_back
    assert len(connection.cursor_value.inserted) == 1
    assert any("analytics_aggregate_batch" in query for query, _ in connection.cursor_value.executed)


def test_publisher_activates_only_after_validation_when_explicitly_requested(local_tmp_path):
    connection = FakeConnection()
    source = local_tmp_path / "sample.csv"
    source.write_bytes(b"sample")
    manifest = _manifest(hashlib.sha256(b"sample").hexdigest())
    result = publish(
        manifest,
        [_row()],
        source_path=source,
        connection=connection,
        activate=True,
    )
    assert result["status"] == "ACTIVE"
    assert connection.committed
    assert any(
        "analytics_aggregate_active_batch" in query
        for query, _ in connection.cursor_value.executed
    )


def test_publisher_rolls_back_on_fact_manifest_mismatch(local_tmp_path):
    connection = FakeConnection()
    source = local_tmp_path / "sample.csv"
    source.write_bytes(b"sample")
    manifest = _manifest(hashlib.sha256(b"sample").hexdigest())
    with pytest.raises(AggregateContractError, match="aggregate row count"):
        publish(manifest, [], source_path=source, connection=connection)
    assert connection.rolled_back
    assert not connection.committed


def test_source_file_digest_is_checked_before_publish(local_tmp_path):
    source = local_tmp_path / "sample.csv"
    source.write_bytes(b"actual")
    manifest = _manifest(hashlib.sha256(b"expected").hexdigest())
    with pytest.raises(AggregateContractError, match="source_sha256"):
        validate_source_file(source, manifest)


def test_mysql_version_guard_fails_closed_for_old_or_non_mysql_versions():
    assert parse_mysql_version("8.0.16-ubuntu") == (8, 0, 16)
    with pytest.raises(AggregateContractError, match="8.0.16"):
        parse_mysql_version("8.0.15")
    with pytest.raises(AggregateContractError, match="8.0.16"):
        parse_mysql_version("10.6.12-MariaDB")


def test_activate_existing_switches_batches_in_one_transaction():
    connection = StatefulConnection(
        {
            "old": _db_batch("old", "ACTIVE"),
            "new": _db_batch("new", "VALIDATED"),
        },
        pointer="old",
    )
    result = activate_existing("new", connection=connection)
    assert result == {
        "status": "ACTIVE",
        "batch_id": "new",
        "idempotent": False,
    }
    assert connection.batches["old"]["status"] == "RETIRED"
    assert connection.batches["new"]["status"] == "ACTIVE"
    assert connection.pointer == "new"
    assert connection.committed
    assert not connection.rolled_back


def test_repeated_activation_is_idempotent():
    connection = StatefulConnection(
        {"new": _db_batch("new", "ACTIVE")},
        pointer="new",
    )
    result = activate_existing("new", connection=connection)
    assert result["idempotent"] is True
    assert connection.committed
    assert not connection.rolled_back


def test_activation_failure_rolls_back_status_and_pointer_changes():
    connection = StatefulConnection(
        {
            "old": _db_batch("old", "ACTIVE"),
            "new": _db_batch("new", "VALIDATED"),
        },
        pointer="old",
        fail_on_pointer_insert=True,
    )
    with pytest.raises(RuntimeError, match="pointer insert"):
        activate_existing("new", connection=connection)
    assert connection.batches["old"]["status"] == "ACTIVE"
    assert connection.batches["new"]["status"] == "VALIDATED"
    assert connection.pointer == "old"
    assert connection.rolled_back
    assert not connection.committed


def test_pointer_to_non_active_batch_fails_closed():
    connection = StatefulConnection(
        {
            "old": _db_batch("old", "VALIDATED"),
            "new": _db_batch("new", "VALIDATED"),
        },
        pointer="old",
    )
    with pytest.raises(AggregateContractError, match="does not target"):
        activate_existing("new", connection=connection)
    assert connection.pointer == "old"
    assert connection.rolled_back


def test_multiple_active_batches_fail_closed():
    connection = StatefulConnection(
        {
            "old": _db_batch("old", "ACTIVE"),
            "other": _db_batch("other", "ACTIVE"),
            "new": _db_batch("new", "VALIDATED"),
        },
        pointer="old",
    )
    with pytest.raises(AggregateContractError, match="multiple ACTIVE"):
        activate_existing("new", connection=connection)
    assert connection.pointer == "old"
    assert connection.rolled_back


def test_rollback_restores_compatible_retired_batch_and_is_repeatable():
    connection = StatefulConnection(
        {
            "current": _db_batch("current", "ACTIVE"),
            "previous": _db_batch("previous", "RETIRED"),
        },
        pointer="current",
    )
    result = rollback_active_batch("previous", connection=connection)
    assert result["rollback"] is True
    assert result["idempotent"] is False
    assert connection.batches["current"]["status"] == "RETIRED"
    assert connection.batches["previous"]["status"] == "ACTIVE"
    assert connection.pointer == "previous"

    repeated = rollback_active_batch("previous", connection=connection)
    assert repeated["idempotent"] is True
