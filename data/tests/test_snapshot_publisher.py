from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_ROOT / "src"))

import publish_analytics_snapshot_mysql as publisher  # noqa: E402
from publish_analytics_snapshot_mysql import load_snapshot  # noqa: E402


def test_fixture_is_valid_publishable_snapshot():
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = load_snapshot(path)
    assert document["data_version"] == "fixture:sparcs_full_analytics:v1"
    assert len({(row["module_key"], row["entity_key"]) for row in document["records"]}) == len(document["records"])


def test_duplicate_snapshot_key_is_rejected(tmp_path):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["records"].append(document["records"][0])
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="重复"):
        load_snapshot(invalid)


def test_payload_type_is_frozen_to_renderer_whitelist(tmp_path):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["records"][0]["payload"]["sections"][0]["type"] = "line"
    invalid = tmp_path / "invalid-section.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="只能是 bar、pie、table 或 status"):
        load_snapshot(invalid)


def test_payload_does_not_expose_model_metadata_as_new_top_level_fields():
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = load_snapshot(path)
    model = next(row for row in document["records"] if row["module_key"] == "high_cost_model")

    assert set(model["payload"]) <= {"title", "description", "options", "filters", "metrics", "sections"}
    assert model["payload"]["options"]["model_version"].startswith("fixture:")


def test_fixture_storage_statuses_never_claim_real_verification():
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = load_snapshot(path)
    quality = next(row for row in document["records"] if row["module_key"] == "data_quality")
    statuses = {item["name"]: item["value"] for item in quality["payload"]["sections"][0]["items"]}

    assert statuses == {
        "HDFS": "CHECK_REQUIRED",
        "Hive": "CHECK_REQUIRED",
        "MySQL": "CHECK_REQUIRED",
        "PySpark任务": "FIXTURE_ONLY",
    }


def test_non_utc_generated_at_is_rejected(tmp_path):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["generated_at"] = "2026-08-18T08:00:00.000000+08:00"
    invalid = tmp_path / "invalid-time.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="UTC"):
        load_snapshot(invalid)


def test_entity_key_preserves_internal_spaces_in_published_enum_values(tmp_path):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    cohort = next(row for row in document["records"] if row["module_key"] == "cohorts")
    cohort["entity_key"] = "age=50 to 69|gender=*|admission=*"
    invalid = tmp_path / "cohort-space-key.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")

    loaded = load_snapshot(invalid)
    assert next(
        row for row in loaded["records"] if row["module_key"] == "cohorts"
    )["entity_key"] == "age=50 to 69|gender=*|admission=*"


def test_publish_rolls_back_when_post_write_integrity_check_fails(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, args=None):
            self.last_query = query

        def executemany(self, query, rows):
            self.rows = list(rows)

        def fetchone(self):
            return {"n": 0, "versions": 1, "timestamps": 1}

    class FakeConnection:
        def __init__(self):
            self.cursor_value = FakeCursor()
            self.began = False
            self.committed = False
            self.rolled_back = False
            self.closed = False

        def begin(self):
            self.began = True

        def cursor(self):
            return self.cursor_value

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    connection = FakeConnection()

    class FakePyMySQL:
        MySQLError = Exception

        @staticmethod
        def connect(**kwargs):
            return connection

    class FakeCursors:
        DictCursor = object()

    monkeypatch.setitem(sys.modules, "pymysql", FakePyMySQL)
    monkeypatch.setitem(sys.modules, "pymysql.cursors", FakeCursors)
    monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
    monkeypatch.setenv("MYSQL_USER", "test")
    monkeypatch.setenv("MYSQL_DATABASE", "test")

    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    with pytest.raises(ValueError, match="完整性校验失败"):
        publisher.publish(load_snapshot(path))

    assert connection.began
    assert connection.rolled_back
    assert not connection.committed
    assert connection.closed
