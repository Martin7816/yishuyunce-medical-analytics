"""Build the internal additive aggregate fact from the shared clean frame.

This module is intentionally separate from ``run_full_analytics_pyspark.py``.
It reuses that module's input validation and ``clean_frame`` implementation,
but it does not build or publish any public analytics snapshot.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pyspark import StorageLevel
from pyspark.sql import DataFrame, SparkSession, functions as F

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analytics_metadata import (  # noqa: E402
    build_data_version,
    normalize_generated_at,
    sha256_file,
)
from run_full_analytics_pyspark import (  # noqa: E402
    _validate_input_columns,
    clean_frame,
)
from shared.aggregate_contract import (  # noqa: E402
    AGGREGATE_FORMULA_VERSION,
    AGGREGATE_GRAIN,
    AGGREGATE_MEASURES,
    AggregateContractError,
    SEMANTIC_REGISTRY_VERSION,
    build_aggregate_batch_manifest,
    build_batch_id,
    default_suppression_policy,
    missing_bucket,
    validate_aggregate_reconciliation,
)


def analysis_scope(frame: DataFrame) -> DataFrame:
    """Return exactly the scope used by the existing analytics pipeline."""

    return frame.where(
        F.coalesce(F.col("in_scope"), F.lit(False))
        & F.col("los").isNotNull()
    )


def _normalized_dimension(frame: DataFrame, field: str) -> Any:
    value = F.trim(F.col(field).cast("string"))
    return F.when(
        value.isNull() | (F.length(value) == 0),
        F.lit(missing_bucket(field)),
    ).otherwise(value)


def _count_when(condition: Any) -> Any:
    return F.sum(F.when(condition, F.lit(1)).otherwise(F.lit(0))).cast("long")


def validate_missing_bucket_collisions(scoped: DataFrame) -> None:
    """Reject real values that would collide with a missing-value bucket."""

    collision_counts = scoped.agg(
        *(
            F.coalesce(
                F.sum(
                    F.when(
                        F.trim(F.col(field).cast("string"))
                        == F.lit(missing_bucket(field)),
                        F.lit(1),
                    ).otherwise(F.lit(0))
                ),
                F.lit(0),
            )
            .cast("long")
            .alias(field)
            for field in AGGREGATE_GRAIN
        )
    ).first()
    collisions = [
        field
        for field in AGGREGATE_GRAIN
        if collision_counts[field] and int(collision_counts[field]) > 0
    ]
    if collisions:
        field = collisions[0]
        raise AggregateContractError(
            f"reserved missing bucket collision for field '{field}': "
            f"{missing_bucket(field)}"
        )


def build_aggregate_fact_from_scope(scoped: DataFrame) -> DataFrame:
    """Build one row per observed seven-dimensional combination.

    Every emitted measure is additive.  Averages and rates are deliberately
    not stored; future query code must derive them from the corresponding sum
    and valid-count measures after final-group privacy validation.
    """

    validate_missing_bucket_collisions(scoped)
    normalized = scoped
    for field in AGGREGATE_GRAIN:
        normalized = normalized.withColumn(field, _normalized_dimension(normalized, field))

    valid_money = F.coalesce(F.col("valid_money"), F.lit(False))
    emergency_present = F.col("emergency").isNotNull() & (
        F.length(F.trim(F.col("emergency"))) > 0
    )
    surgical_present = F.col("medical_surgical").isNotNull() & (
        F.length(F.trim(F.col("medical_surgical"))) > 0
    )
    severe_present = F.col("severity").isin(
        "Minor", "Moderate", "Major", "Extreme"
    )
    charges_sum = F.sum(
        F.when(valid_money, F.col("charges")).otherwise(
            F.lit(0).cast("decimal(38,2)")
        )
    ).cast("decimal(38,2)")
    costs_sum = F.sum(
        F.when(valid_money, F.col("costs")).otherwise(
            F.lit(0).cast("decimal(38,2)")
        )
    ).cast("decimal(38,2)")

    aggregate = normalized.groupBy(*AGGREGATE_GRAIN).agg(
        F.count(F.lit(1)).cast("long").alias("record_count"),
        F.sum(F.col("los")).cast("long").alias("los_sum"),
        F.count(F.col("los")).cast("long").alias("los_valid_count"),
        charges_sum.alias("charges_sum"),
        _count_when(valid_money & F.col("charges").isNotNull()).alias(
            "charges_valid_count"
        ),
        costs_sum.alias("costs_sum"),
        _count_when(valid_money & F.col("costs").isNotNull()).alias(
            "costs_valid_count"
        ),
        _count_when(F.col("emergency") == F.lit("Y")).alias(
            "emergency_yes_count"
        ),
        _count_when(emergency_present).alias("emergency_valid_count"),
        _count_when(F.col("medical_surgical").contains("Surgical")).alias(
            "surgical_yes_count"
        ),
        _count_when(surgical_present).alias("surgical_valid_count"),
        _count_when(F.col("severity").isin("Major", "Extreme")).alias(
            "severe_yes_count"
        ),
        _count_when(severe_present).alias("severe_valid_count"),
    )
    return aggregate.select(*(AGGREGATE_GRAIN + AGGREGATE_MEASURES))


def build_aggregate_fact(cleaned: DataFrame) -> DataFrame:
    """Build the fact from a cleaned frame using the frozen analysis scope."""

    return build_aggregate_fact_from_scope(analysis_scope(cleaned))


def _read_cleaned(spark: SparkSession, input_path: Path) -> DataFrame:
    raw = (
        spark.read.option("header", "true")
        .option("inferSchema", "false")
        .option("mode", "FAILFAST")
        .csv(str(input_path))
    )
    _validate_input_columns(raw)
    return clean_frame(raw)


def build_aggregate_batch(
    input_path: Path,
    *,
    output_dir: Path | None = None,
    generated_at: str | None = None,
    master: str = "local[1]",
    minimum_cohort_size: int | None = None,
) -> dict[str, Any]:
    """Build and optionally materialize a candidate batch.

    Materialization is opt-in and writes only a candidate manifest plus Spark
    JSON fact parts.  No MySQL connection is made by this function.
    """

    input_path = input_path.resolve()
    digest = sha256_file(input_path)
    data_version = build_data_version(input_path, digest)
    policy = default_suppression_policy(minimum_cohort_size)
    batch_id = build_batch_id(
        data_version,
        AGGREGATE_FORMULA_VERSION,
        SEMANTIC_REGISTRY_VERSION,
        policy["policy_version"],
    )
    spark = (
        SparkSession.builder.master(master)
        .appName("yishuyunce-aggregate-fact")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    cleaned = None
    scoped = None
    fact = None
    try:
        cleaned = _read_cleaned(spark, input_path).persist(StorageLevel.MEMORY_AND_DISK)
        raw_records = cleaned.count()
        scoped = analysis_scope(cleaned).persist(StorageLevel.MEMORY_AND_DISK)
        source_records = scoped.count()
        fact = build_aggregate_fact_from_scope(scoped).persist(
            StorageLevel.MEMORY_AND_DISK
        )
        aggregate_rows = fact.count()
        fact_record_counts = fact.agg(F.sum("record_count")).first()
        fact_record_count = int(fact_record_counts[0] or 0)
        validate_aggregate_reconciliation(
            source_scope_row_count=source_records,
            aggregate_row_count=aggregate_rows,
            fact_row_count=aggregate_rows,
            fact_record_count=fact_record_count,
        )
        manifest = build_aggregate_batch_manifest(
            batch_id=batch_id,
            data_version=data_version,
            formula_version=AGGREGATE_FORMULA_VERSION,
            registry_version=SEMANTIC_REGISTRY_VERSION,
            suppression_policy=policy,
            input_file_name=input_path.name,
            source_sha256=digest,
            raw_records=raw_records,
            source_records=source_records,
            aggregate_rows=aggregate_rows,
            generated_at=normalize_generated_at(generated_at),
        )
        if output_dir is not None:
            _write_candidate(output_dir, fact, manifest)
        return manifest
    finally:
        if fact is not None:
            fact.unpersist(blocking=True)
        if scoped is not None:
            scoped.unpersist(blocking=True)
        if cleaned is not None:
            cleaned.unpersist(blocking=True)
        spark.stop()


def _write_candidate(
    output_dir: Path,
    fact: DataFrame,
    manifest: dict[str, Any],
) -> None:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    fact.write.mode("error").json(str(output_dir / "facts"))
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--generated-at")
    parser.add_argument("--master", default="local[1]")
    parser.add_argument("--minimum-cohort-size", type=int)
    args = parser.parse_args()
    manifest = build_aggregate_batch(
        args.input,
        output_dir=args.output_dir,
        generated_at=args.generated_at,
        master=args.master,
        minimum_cohort_size=args.minimum_cohort_size,
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": "candidate",
                "batch_id": manifest["batch_id"],
                "data_version": manifest["data_version"],
                "source_records": manifest["source_records"],
                "aggregate_rows": manifest["aggregate_rows"],
                "output_dir": str(args.output_dir.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
