"""Run the frozen SPARCS TOP10 contract with local PySpark.

This is the formal M1 computation path for the current environment decision:
PySpark runs in local mode on the leader's computer.  The standard-library
verifier remains an independent check and is deliberately not imported here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pyspark
from pyspark.sql import DataFrame, SparkSession, functions as F


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE = REPO_ROOT / "data" / "fixtures" / "sparcs_mvp_sample.csv"
DIAGNOSIS_FIELD = "CCSR Diagnosis Description"
YEAR_FIELD = "Discharge Year"


def calculate_top10(spark: SparkSession, csv_path: Path, top_n: int) -> dict[str, Any]:
    """Calculate the TOP10 using the frozen contract and local Spark."""

    frame = (
        spark.read.option("header", "true")
        .option("inferSchema", "false")
        .option("mode", "FAILFAST")
        .csv(csv_path.resolve().as_uri())
    )
    missing = {DIAGNOSIS_FIELD, YEAR_FIELD}.difference(frame.columns)
    if missing:
        raise ValueError(f"CSV 缺少指标字段: {sorted(missing)}")

    diagnosis = F.trim(F.col(DIAGNOSIS_FIELD)).alias("diagnosis")
    valid = (
        frame.where(F.trim(F.col(YEAR_FIELD)) == F.lit("2021"))
        .select(diagnosis)
        .where(F.length(F.col("diagnosis")) > 0)
    )
    ranked: DataFrame = (
        valid.groupBy("diagnosis")
        .count()
        .withColumnRenamed("count", "case_count")
        .orderBy(F.desc("case_count"), F.asc("diagnosis"))
        .limit(top_n)
    )
    top10 = [
        {"name": row["diagnosis"], "case_count": int(row["case_count"])}
        for row in ranked.collect()
    ]
    return {
        "status": "PASS",
        "engine": "pyspark-local",
        "pyspark_version": pyspark.__version__,
        "input": csv_path.name,
        "rows": frame.count(),
        "diagnosis_nonempty_rows": valid.count(),
        "diagnosis_nonempty_distinct": valid.select("diagnosis").distinct().count(),
        "top10": top10,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument(
        "--expected",
        type=Path,
        help="可选的期望 JSON；传入后核对其中 sample.top10 和计数摘要",
    )
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    if args.top < 1:
        raise ValueError("--top 必须为正整数")

    spark = (
        SparkSession.builder.master("local[2]")
        .appName("yishuyunce-sparcs-top10")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    try:
        result = calculate_top10(spark, args.input, args.top)
    finally:
        spark.stop()

    if args.expected:
        expected_document = json.loads(args.expected.read_text(encoding="utf-8"))
        expected = expected_document["sample"]
        for field in (
            "rows",
            "diagnosis_nonempty_rows",
            "diagnosis_nonempty_distinct",
        ):
            if result[field] != expected[field]:
                raise AssertionError(
                    f"{field} 不一致: expected={expected[field]!r}, actual={result[field]!r}"
                )
        if result["top10"] != expected["top10"]:
            raise AssertionError("top10 不一致")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
