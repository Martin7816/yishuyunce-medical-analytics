from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
sys.path.insert(0, str(DATA_ROOT / "src"))

from verify_risk_snapshot import expected_payload, summarize_stream  # noqa: E402


EDGE_SAMPLE = DATA_ROOT / "fixtures" / "dashboard_edge_sample.csv"


def test_independent_risk_formula_includes_empty_combinations():
    with EDGE_SAMPLE.open("r", encoding="utf-8-sig", newline="") as handle:
        expected, raw_rows, scoped_rows = summarize_stream(csv.DictReader(handle))

    assert raw_rows == 4
    assert scoped_rows == 3
    assert expected["options"] == {
        "age_group": ["0 to 17", "18 to 29", "50 to 69"],
        "diagnosis_code": [
            {"value": "END003", "label": "DIABETES"},
            {"value": "RSP009", "label": "ASTHMA"},
        ],
    }

    aggregates = expected["aggregates"]
    assert len(aggregates) == 12
    assert aggregates[(None, None)]["count"] == 3
    assert aggregates[(None, None)]["high_risk_count"] == 2
    assert aggregates[("0 to 17", "RSP009")]["high_risk_count"] == 1
    assert aggregates[("50 to 69", "END003")]["count"] == 0

    wildcard = expected_payload((None, None), aggregates[(None, None)], expected["options"])
    assert wildcard["metrics"] == [
        {"key": "high_risk_count", "label": "Major/Extreme记录数", "value": 2, "unit": "条"},
        {"key": "high_risk_rate", "label": "Major/Extreme比例", "value": 0.6667, "unit": "%"},
        {"key": "avg_los", "label": "高风险平均住院时长", "value": 61.0, "unit": "天"},
        {"key": "avg_charges", "label": "高风险平均收费", "value": 100.0, "unit": "美元"},
        {"key": "avg_costs", "label": "高风险平均成本", "value": 30.0, "unit": "美元"},
    ]
    assert [item["name"] for item in wildcard["sections"][0]["items"]] == [
        "Extreme",
        "Major",
    ]
    assert [item["name"] for item in wildcard["sections"][3]["items"]] == [
        "0 to 17",
        "18 to 29",
    ]


def test_pyspark_risk_snapshot_matches_independent_verifier(tmp_path):
    runtimes = [
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        DATA_ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    spark_python = next((path for path in runtimes if path.exists()), None)
    if spark_python is None:
        pytest.skip("workspace PySpark runtime is not installed")

    snapshot_path = tmp_path / "risk-snapshot.json"
    environment = os.environ.copy()
    environment["PYSPARK_PYTHON"] = str(spark_python)
    generated = subprocess.run(
        [
            str(spark_python),
            str(DATA_ROOT / "src" / "run_full_analytics_pyspark.py"),
            "--input",
            str(EDGE_SAMPLE),
            "--output",
            str(snapshot_path),
            "--generated-at",
            "2026-08-19T00:00:00Z",
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert generated.returncode == 0, generated.stderr + generated.stdout

    verified = subprocess.run(
        [
            str(spark_python),
            str(DATA_ROOT / "src" / "verify_risk_snapshot.py"),
            "--input",
            str(EDGE_SAMPLE),
            "--snapshot",
            str(snapshot_path),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert verified.returncode == 0, verified.stderr + verified.stdout
    result = json.loads(verified.stdout)
    assert result["status"] == "PASS"
    assert result["risk_key_count"] == 12
    assert result["empty_combination_count"] == 4
    assert result["wildcard_high_risk_count"] == 2

    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    risk_records = {
        record["entity_key"]: record
        for record in document["records"]
        if record["module_key"] == "risks"
    }
    assert len(risk_records) == 12
    assert set(risk_records["age=*|diagnosis=*"]["payload"]["options"]) == {
        "age_group",
        "diagnosis_code",
    }
    assert risk_records["age=50 to 69|diagnosis=END003"]["payload"]["metrics"] == []
    assert [item["key"] for item in risk_records["age=*|diagnosis=*"]["payload"]["metrics"]] == [
        "high_risk_count",
        "high_risk_rate",
        "avg_los",
        "avg_charges",
        "avg_costs",
    ]
