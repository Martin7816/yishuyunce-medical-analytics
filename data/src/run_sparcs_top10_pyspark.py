"""Run the frozen SPARCS TOP10 contract with local PySpark.

This is the formal M1 computation path for the current environment decision:
PySpark runs in local mode, while the raw input may come from the HDFS/Hive
course environment.  The standard-library verifier remains an independent
check and is deliberately not imported here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pyspark
from pyspark.sql import DataFrame, SparkSession, functions as F

from analytics_metadata import (
    build_data_version,
    normalize_generated_at,
)
from storage_input import (
    DataSource,
    add_source_arguments,
    ensure_local_source_exists,
    fingerprint_source,
    read_source,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE = REPO_ROOT / "data" / "fixtures" / "sparcs_mvp_sample.csv"
DIAGNOSIS_FIELD = "CCSR Diagnosis Description"
YEAR_FIELD = "Discharge Year"
SERVICE_METRIC = "disease_case_count_top10"
SERVICE_UNIT = "discharge_records"
EDGE_WHITESPACE = r"^[\s\p{Z}\ufeff]+|[\s\p{Z}\ufeff]+$"


def calculate_top10(
    spark: SparkSession, source: DataSource, top_n: int
) -> dict[str, Any]:
    """Calculate the TOP10 using the frozen contract and local Spark."""

    frame = read_source(spark, source)
    missing = {DIAGNOSIS_FIELD, YEAR_FIELD}.difference(frame.columns)
    if missing:
        raise ValueError(f"输入数据缺少指标字段: {sorted(missing)}")

    diagnosis = F.regexp_replace(
        F.col(DIAGNOSIS_FIELD), EDGE_WHITESPACE, ""
    ).alias("diagnosis")
    year = F.trim(F.col(YEAR_FIELD))
    valid = (
        frame.where(year == F.lit("2021"))
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
        "input": source.name,
        "rows": frame.count(),
        "malformed_rows": 0,
        "out_of_scope_rows": frame.where(
            year.isNull() | (year != F.lit("2021"))
        ).count(),
        "diagnosis_nonempty_rows": valid.count(),
        "diagnosis_nonempty_distinct": valid.select("diagnosis").distinct().count(),
        "top10": top10,
    }


def build_run_document(
    result: dict[str, Any],
    source: DataSource,
    digest: str,
    generated_at: str,
    data_version_override: str | None = None,
) -> dict[str, Any]:
    data_version = data_version_override or build_data_version(
        source.version_path, digest, fixture=source.is_fixture
    )
    service_result = {
        "metric": SERVICE_METRIC,
        "unit": SERVICE_UNIT,
        "data_version": data_version,
        "generated_at": generated_at,
        "items": [
            {
                "rank": rank,
                "diagnosis_name": item["name"],
                "case_count": item["case_count"],
            }
            for rank, item in enumerate(result["top10"], start=1)
        ],
    }
    input_fingerprint = {
        "file_name": source.name,
        "sha256": digest,
    }
    if source.local_path is not None:
        input_fingerprint["size_bytes"] = source.local_path.stat().st_size
    return {
        **result,
        "input_fingerprint": input_fingerprint,
        "service_result": service_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    add_source_arguments(parser, required=False)
    parser.add_argument(
        "--expected",
        type=Path,
        help="可选的期望 JSON；传入后核对其中 sample.top10 和计数摘要",
    )
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        help="可选的服务结果工件路径；只写入小型 JSON，不复制原始 CSV",
    )
    parser.add_argument(
        "--generated-at",
        help="可选的 ISO-8601 时间；不传时使用当前 UTC 时间",
    )
    args = parser.parse_args()

    if args.top < 1:
        raise ValueError("--top 必须为正整数")

    if args.input is None and args.hive_table is None:
        args.input = str(DEFAULT_SAMPLE)
    source = DataSource.from_arguments(args.input, args.hive_table)
    ensure_local_source_exists(source)
    digest = fingerprint_source(source, args.input_sha256)

    builder = (
        SparkSession.builder.master("local[2]")
        .appName("yishuyunce-sparcs-top10")
        .config("spark.ui.enabled", "false")
    )
    if source.kind == "hive":
        builder = builder.enableHiveSupport()
    spark = builder.getOrCreate()
    try:
        result = calculate_top10(spark, source, args.top)
    finally:
        spark.stop()

    if args.expected:
        expected_document = json.loads(args.expected.read_text(encoding="utf-8"))
        expected_key = (
            "sample"
            if source.local_path == DEFAULT_SAMPLE.resolve()
            else "full_scan"
        )
        expected = expected_document[expected_key]
        for field in (
            "rows",
            "malformed_rows",
            "out_of_scope_rows",
            "diagnosis_nonempty_rows",
            "diagnosis_nonempty_distinct",
        ):
            if result[field] != expected[field]:
                raise AssertionError(
                    f"{field} 不一致: expected={expected[field]!r}, actual={result[field]!r}"
                )
        if result["top10"] != expected["top10"]:
            raise AssertionError("top10 不一致")

    document = build_run_document(
        result,
        source,
        digest,
        normalize_generated_at(args.generated_at),
        args.data_version,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(document, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
