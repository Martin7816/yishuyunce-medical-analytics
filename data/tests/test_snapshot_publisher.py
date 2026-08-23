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

    with pytest.raises(ValueError, match="只能是 bar、pie、table、status、grouped_bar、scatter、heatmap 或 correlation"):
        load_snapshot(invalid)


def test_correlation_section_accepts_frozen_statistical_evidence(tmp_path):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    costs = next(row for row in document["records"] if row["module_key"] == "costs")
    costs["payload"]["sections"] = [
        section
        for section in costs["payload"]["sections"]
        if section["key"] != "continuous_correlations"
    ]
    costs["payload"]["sections"].append(
        {
            "key": "continuous_correlations",
            "title": "关键连续变量相关性",
            "type": "correlation",
            "visual": {
                "question": "住院时长、收费与成本之间呈现怎样的线性相关关系？",
                "x_label": "指标组合",
                "y_label": "Pearson r",
                "unit": "相关系数",
                "legend": [{"key": "pearson", "label": "Pearson r", "style": "numeric"}],
                "tooltip_fields": ["x_label", "y_label", "coefficient", "sample_size", "method"],
                "summary": {
                    "text": "系数按成对有效记录计算；相关不等于因果。",
                    "source_metric_keys": ["record_count"],
                    "source_section": "continuous_correlations",
                    "data_version": document["data_version"],
                    "generated_at": document["generated_at"],
                    "boundary": "当前筛选下两项指标均有效的住院出院记录",
                    "related_not_causal": True,
                },
                "fallback": {
                    "type": "table",
                    "columns": ["x_label", "y_label", "coefficient", "sample_size", "method"],
                },
                "empty": {"title": "暂无相关结果", "text": "有效样本不足或指标没有变化。"},
            },
            "items": [
                {
                    "x_key": "los",
                    "x_label": "住院时长",
                    "y_key": "charges",
                    "y_label": "收费",
                    "coefficient": 0.5,
                    "sample_size": 20,
                    "method": "pearson",
                }
            ],
        }
    )
    candidate = tmp_path / "correlation.json"
    candidate.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    loaded = load_snapshot(candidate)
    loaded_costs = next(
        row for row in loaded["records"] if row["module_key"] == "costs"
    )
    section = next(
        item
        for item in loaded_costs["payload"]["sections"]
        if item["key"] == "continuous_correlations"
    )
    assert section["items"][0]["coefficient"] == 0.5


@pytest.mark.parametrize("coefficient", [-1.01, 1.01, float("nan")])
def test_correlation_section_rejects_invalid_coefficients(tmp_path, coefficient):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    costs = next(row for row in document["records"] if row["module_key"] == "costs")
    costs["payload"]["sections"] = [
        section
        for section in costs["payload"]["sections"]
        if section["key"] != "continuous_correlations"
    ]
    costs["payload"]["sections"].append(
        {
            "key": "continuous_correlations",
            "title": "关键连续变量相关性",
            "type": "correlation",
            "visual": {
                "question": "连续变量相关性",
                "x_label": "指标组合",
                "y_label": "Pearson r",
                "unit": "相关系数",
                "legend": [{"key": "pearson", "label": "Pearson r", "style": "numeric"}],
                "tooltip_fields": ["x_label", "y_label", "coefficient", "sample_size", "method"],
                "summary": {
                    "text": "相关不等于因果。",
                    "source_metric_keys": ["record_count"],
                    "source_section": "continuous_correlations",
                    "data_version": document["data_version"],
                    "generated_at": document["generated_at"],
                    "boundary": "成对有效记录",
                    "related_not_causal": True,
                },
                "fallback": {"type": "table", "columns": ["coefficient", "sample_size"]},
                "empty": {"title": "暂无相关结果", "text": "有效样本不足。"},
            },
            "items": [
                {
                    "x_key": "los", "x_label": "住院时长",
                    "y_key": "charges", "y_label": "收费",
                    "coefficient": coefficient, "sample_size": 2, "method": "pearson",
                }
            ],
        }
    )
    candidate = tmp_path / "invalid-correlation.json"
    candidate.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="coefficient"):
        load_snapshot(candidate)


def test_relation_visual_rejects_arbitrary_renderer_options(tmp_path):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    hospital = next(
        row for row in document["records"]
        if row["module_key"] == "hospitals" and row["entity_key"] == "index"
    )
    relation = next(
        section for section in hospital["payload"]["sections"]
        if section["key"] == "facility_relation"
    )
    relation["visual"]["echarts_option"] = {"series": []}
    invalid = tmp_path / "invalid-visual.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="未冻结字段"):
        load_snapshot(invalid)


def test_relation_metadata_must_match_snapshot_envelope(tmp_path):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    risk = next(row for row in document["records"] if row["module_key"] == "risks")
    matrix = next(
        section for section in risk["payload"]["sections"]
        if section["key"] == "age_severity_matrix"
    )
    matrix["visual"]["summary"]["data_version"] = "fixture:other:v1"
    invalid = tmp_path / "invalid-relation-version.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="必须与快照 data_version 一致"):
        load_snapshot(invalid)


def test_relation_numbers_reject_nan(tmp_path):
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    costs = next(row for row in document["records"] if row["module_key"] == "costs")
    relation = next(
        section for section in costs["payload"]["sections"]
        if section["key"] == "cost_los_relation"
    )
    relation["items"][0]["y"] = float("nan")
    invalid = tmp_path / "invalid-relation-number.json"
    invalid.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="NaN"):
        load_snapshot(invalid)


def test_payload_does_not_expose_model_metadata_as_new_top_level_fields():
    path = DATA_ROOT.parent / "backend" / "app" / "fixtures" / "analytics_snapshot_success.json"
    document = load_snapshot(path)
    model = next(row for row in document["records"] if row["module_key"] == "high_cost_model")

    assert set(model["payload"]) <= {"title", "description", "options", "filters", "metrics", "sections", "insights"}
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
