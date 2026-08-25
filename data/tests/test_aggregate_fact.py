from __future__ import annotations

import sys
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DATA_ROOT / "src"))

pyspark = pytest.importorskip("pyspark")
from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from aggregate_fact_pyspark import build_aggregate_fact  # noqa: E402
from run_full_analytics_pyspark import clean_frame  # noqa: E402
from shared.aggregate_contract import AggregateContractError  # noqa: E402


EDGE_SAMPLE = DATA_ROOT / "fixtures" / "dashboard_edge_sample.csv"


@pytest.fixture(scope="module")
def spark():
    session = (
        SparkSession.builder.master("local[1]")
        .appName("aggregate-fact-tests")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def test_build_aggregate_fact_uses_existing_scope_and_additive_measures(spark):
    raw = (
        spark.read.option("header", "true")
        .option("inferSchema", "false")
        .option("mode", "FAILFAST")
        .csv(str(EDGE_SAMPLE))
    )
    cleaned = clean_frame(raw)
    fact = build_aggregate_fact(cleaned)
    rows = [row.asDict() for row in fact.collect()]

    assert len(rows) == 3
    assert sum(row["record_count"] for row in rows) == 3

    missing = next(
        row for row in rows if row["diagnosis_code"] == "__MISSING_DIAGNOSIS_CODE__"
    )
    assert missing["severity"] == "__MISSING_SEVERITY__"
    assert missing["record_count"] == 1
    assert float(missing["charges_sum"]) == pytest.approx(200)
    assert missing["charges_valid_count"] == 1

    valid = next(row for row in rows if row["diagnosis_code"] == "RSP009")
    assert valid["record_count"] == 1
    assert valid["los_sum"] == 2
    assert valid["los_valid_count"] == 1
    assert float(valid["charges_sum"]) == pytest.approx(100)
    assert float(valid["costs_sum"]) == pytest.approx(20)
    assert valid["emergency_yes_count"] == 1
    assert valid["surgical_yes_count"] == 0
    assert valid["severe_yes_count"] == 1


def test_build_aggregate_fact_rejects_missing_bucket_collision(spark):
    raw = (
        spark.read.option("header", "true")
        .option("inferSchema", "false")
        .option("mode", "FAILFAST")
        .csv(str(EDGE_SAMPLE))
    )
    cleaned = clean_frame(raw).withColumn(
        "facility_id", F.lit("__MISSING_FACILITY_ID__")
    )
    with pytest.raises(AggregateContractError, match="facility_id"):
        build_aggregate_fact(cleaned).count()
