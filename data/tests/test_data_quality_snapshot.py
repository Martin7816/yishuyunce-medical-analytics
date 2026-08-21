from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
DATA_QUALITY_SAMPLE = DATA_ROOT / "fixtures" / "data_quality_snapshot_sample.csv"
DATA_QUALITY_VERIFIER = DATA_ROOT / "src" / "verify_data_quality_snapshot.py"
EXPECTED_METRICS = {
    "raw_rows": 10,
    "valid_rows": 8,
    "out_of_scope_rows": 1,
    "money_parse_or_negative": 3,
    "missing_los": 1,
    "diagnosis_missing": 1,
    "los_capped": 1,
}


@pytest.fixture(scope="module")
def data_quality_artifact(tmp_path_factory):
    spark_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if not spark_python.exists():
        pytest.skip("workspace PySpark runtime is not installed")

    snapshot_path = tmp_path_factory.mktemp("data-quality-snapshot") / "snapshot.json"
    environment = os.environ.copy()
    environment["PYSPARK_PYTHON"] = str(spark_python)
    generated = subprocess.run(
        [
            str(spark_python),
            str(DATA_ROOT / "src" / "run_full_analytics_pyspark.py"),
            "--input",
            str(DATA_QUALITY_SAMPLE),
            "--output",
            str(snapshot_path),
            "--generated-at",
            "2026-08-19T00:00:00Z",
            "--mysql-status",
            "VERIFIED",
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert generated.returncode == 0, generated.stderr + generated.stdout
    return {
        "document": json.loads(snapshot_path.read_text(encoding="utf-8")),
        "path": snapshot_path,
        "python": spark_python,
    }


@pytest.fixture(scope="module")
def data_quality_document(data_quality_artifact):
    return data_quality_artifact["document"]


def quality_record(document):
    records = [
        row
        for row in document["records"]
        if row["module_key"] == "data_quality"
        and row["entity_key"] == "summary"
    ]
    assert len(records) == 1
    return records[0]


def quality_metrics(document):
    return {
        item["key"]: item
        for item in quality_record(document)["payload"]["metrics"]
    }


def quality_storage_section(document):
    sections = [
        item
        for item in quality_record(document)["payload"]["sections"]
        if item["key"] == "storage"
    ]
    assert len(sections) == 1
    return sections[0]


def test_data_quality_snapshot_has_one_summary_record(data_quality_document):
    quality = quality_record(data_quality_document)

    assert quality["module_key"] == "data_quality"
    assert quality["entity_key"] == "summary"


def test_data_quality_metrics_match_frozen_fixture(data_quality_document):
    metrics = quality_metrics(data_quality_document)
    actual = {key: metrics[key]["value"] for key in EXPECTED_METRICS}

    assert actual == EXPECTED_METRICS


def test_data_quality_metrics_use_record_units(data_quality_document):
    metrics = quality_metrics(data_quality_document)
    actual = {key: metrics[key]["unit"] for key in EXPECTED_METRICS}

    assert actual == {key: "条" for key in EXPECTED_METRICS}


def test_out_of_scope_anomalies_do_not_pollute_quality_counts(
    data_quality_document,
):
    metrics = quality_metrics(data_quality_document)

    assert metrics["out_of_scope_rows"]["value"] == 1
    assert metrics["diagnosis_missing"]["value"] == 1
    assert metrics["missing_los"]["value"] == 1
    assert metrics["money_parse_or_negative"]["value"] == 3


def test_fixture_storage_and_task_statuses_are_explicit(data_quality_document):
    storage = quality_storage_section(data_quality_document)
    statuses = {item["name"]: item["value"] for item in storage["items"]}

    assert storage["type"] == "status"
    assert statuses == {
        "HDFS": "CHECK_REQUIRED",
        "Hive": "CHECK_REQUIRED",
        "MySQL": "CHECK_REQUIRED",
        "PySpark任务": "FIXTURE_ONLY",
    }


def test_fixture_metadata_uses_frozen_version_and_time(data_quality_document):
    assert data_quality_document["data_version"].startswith("fixture:")
    assert data_quality_document["generated_at"] == (
        "2026-08-19T00:00:00.000000Z"
    )


def test_data_quality_payload_uses_frozen_shape(data_quality_document):
    payload = quality_record(data_quality_document)["payload"]
    allowed = {"title", "description", "options", "filters", "metrics", "sections"}

    assert {"title", "description", "metrics", "sections"} <= set(payload)
    assert set(payload) <= allowed


def test_stdlib_verifier_accepts_the_pyspark_snapshot(data_quality_artifact):
    verified = subprocess.run(
        [
            str(data_quality_artifact["python"]),
            str(DATA_QUALITY_VERIFIER),
            "--input",
            str(DATA_QUALITY_SAMPLE),
            "--snapshot",
            str(data_quality_artifact["path"]),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert verified.returncode == 0, verified.stderr + verified.stdout
    assert json.loads(verified.stdout)["status"] == "PASS"


def test_stdlib_verifier_rejects_a_tampered_metric(
    data_quality_artifact, tmp_path
):
    document = json.loads(json.dumps(data_quality_artifact["document"]))
    metrics = quality_record(document)["payload"]["metrics"]
    diagnosis_missing = next(
        item for item in metrics if item["key"] == "diagnosis_missing"
    )
    diagnosis_missing["value"] = 999
    tampered = tmp_path / "tampered-snapshot.json"
    tampered.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    verified = subprocess.run(
        [
            str(data_quality_artifact["python"]),
            str(DATA_QUALITY_VERIFIER),
            "--input",
            str(DATA_QUALITY_SAMPLE),
            "--snapshot",
            str(tampered),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    result = json.loads(verified.stdout)
    diagnosis_check = next(
        item for item in result["metrics"] if item["metric"] == "diagnosis_missing"
    )

    assert verified.returncode == 1
    assert result["status"] == "FAIL"
    assert diagnosis_check == {
        "metric": "diagnosis_missing",
        "expected": 1,
        "actual": 999,
        "status": "FAIL",
    }
