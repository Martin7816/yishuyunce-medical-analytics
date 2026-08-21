"""Build product snapshots from one cached PySpark clean frame.

The raw CSV is read once by Spark.  The first action materializes the cleaned
frame, and every subsequent module reuses that cache.  The dashboard builder
is deliberately kept as a named aggregation so its formulas can be checked
independently before the rest of the product snapshot is published.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import product
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.storagelevel import StorageLevel

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analytics_metadata import (  # noqa: E402
    build_data_version,
    normalize_generated_at,
    sha256_file,
)
from shared.analytics_snapshot_contract import (  # noqa: E402
    normalize_utc_timestamp,
    validate_snapshot_document,
)

# Backward-compatible name used by the model task in this workflow.
fingerprint = sha256_file


FIELDS = {
    "year": "Discharge Year",
    "diagnosis": "CCSR Diagnosis Description",
    "diagnosis_code": "CCSR Diagnosis Code",
    "age": "Age Group",
    "gender": "Gender",
    "race": "Race",
    "ethnicity": "Ethnicity",
    "admission": "Type of Admission",
    "los": "Length of Stay",
    "charges": "Total Charges",
    "costs": "Total Costs",
    "emergency": "Emergency Department Indicator",
    "facility": "Facility Name",
    "facility_id": "Permanent Facility Id",
    "severity": "APR Severity of Illness Description",
    "mortality": "APR Risk of Mortality",
    "disposition": "Patient Disposition",
    "payment": "Payment Typology 1",
    "medical_surgical": "APR Medical Surgical Description",
    "procedure": "CCSR Procedure Description",
    "area": "Health Service Area",
}

FIELD_ALIASES = {"facility_id": ("Permanent Facility Id", "Facility ID")}

SEVERITY_VALUES = ("Minor", "Moderate", "Major", "Extreme")
HIGH_RISK_SEVERITY_VALUES = ("Major", "Extreme")
ANALYTICS_FORMULA_VERSION = "analytics-denominator-v1"

COHORT_MISSING = "__COHORT_MISSING__"
COHORT_FIELDS = ("age", "gender", "admission")
COHORT_OPTION_KEYS = {
    "age": "age_group",
    "gender": "gender",
    "admission": "admission_type",
}

RISK_MISSING = "__RISK_MISSING__"
RISK_FIELDS = ("age", "diagnosis_code")
RISK_ENTITY_FIELDS = ("age", "diagnosis")
RISK_OPTION_KEYS = {
    "age": "age_group",
    "diagnosis_code": "diagnosis_code",
}

PAYMENT_MISSING = "__PAYMENT_MISSING__"
PAYMENT_FIELDS = ("payment", "age")
PAYMENT_OPTION_KEYS = {
    "payment": "payment_type",
    "age": "age_group",
}

COST_DIMENSIONS = ("diagnosis_code", "facility_id", "severity")
COST_MISSING = "__COST_MISSING__"
COST_PERCENTILES = (("p25", 0.25), ("p50", 0.5), ("p75", 0.75), ("p90", 0.9))
COST_COMPARISON_LIMIT = 10


def clean_frame(raw: DataFrame) -> DataFrame:
    """Select the frozen columns and apply the shared cleaning rules."""

    def source(name: str):
        for column in FIELD_ALIASES.get(name, (FIELDS[name],)):
            if column in raw.columns:
                return F.col(column)
        return F.lit(None)

    def trim(name: str):
        return F.trim(source(name).cast("string"))

    def money(name: str):
        return F.regexp_replace(trim(name), ",", "").cast("decimal(20,2)")

    year = trim("year")
    los_text = trim("los")
    return raw.select(
        year.alias("year"),
        *[
            trim(name).alias(name)
            for name in (
                "diagnosis",
                "diagnosis_code",
                "age",
                "gender",
                "race",
                "ethnicity",
                "admission",
                "emergency",
                "facility",
                "facility_id",
                "severity",
                "mortality",
                "disposition",
                "payment",
                "medical_surgical",
                "procedure",
                "area",
            )
        ],
        money("charges").alias("charges"),
        money("costs").alias("costs"),
        F.when(los_text == "120 +", F.lit(120))
        .otherwise(los_text.cast("int"))
        .alias("los"),
        (los_text == "120 +").alias("los_capped"),
    ).withColumn("in_scope", F.col("year") == F.lit("2021")).withColumn(
        "valid_money",
        F.col("charges").isNotNull()
        & F.col("costs").isNotNull()
        & (F.col("charges") >= 0)
        & (F.col("costs") >= 0),
    )


def _rounded(value: Any, decimals: int = 2, *, integer: bool = False):
    if value is None:
        return 0 if integer else 0.0
    if integer:
        return int(value)
    return round(float(value), decimals)


def _rate(numerator: Any, denominator: Any) -> float:
    denominator_value = int(denominator or 0)
    if denominator_value == 0:
        return 0.0
    return round(float(numerator or 0) / denominator_value, 4)


def rows(
    frame: DataFrame,
    group: str,
    value: str = "count",
    limit: int | None = 10,
) -> list[dict[str, Any]]:
    """Collect only a small, stable aggregate result; never raw records."""

    nonempty = F.col(group).isNotNull() & (F.length(F.col(group)) > 0)
    grouped = frame.where(nonempty).groupBy(group)
    if value == "count":
        result = grouped.count().withColumnRenamed("count", "value")
    else:
        result = grouped.agg(F.avg(F.col(value)).alias("value"))

    ordered = result.orderBy(F.desc("value"), F.asc(group))
    if limit is not None:
        ordered = ordered.limit(limit)

    output = []
    for row in ordered.collect():
        output.append(
            {
                "name": str(row[group]),
                "value": _rounded(row["value"], integer=value == "count"),
            }
        )
    return output


def grouped_rows(
    frame: DataFrame,
    parent: str,
    group: str,
    value: str = "count",
    limit: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """Aggregate all profile sections for a pair of dimensions in one job."""

    nonempty = (F.length(F.col(parent)) > 0) & (F.length(F.col(group)) > 0)
    grouped = frame.where(nonempty).groupBy(parent, group)
    result = (
        grouped.count().withColumnRenamed("count", "value")
        if value == "count"
        else grouped.agg(F.avg(F.col(value)).alias("value"))
    )
    ordered = result.orderBy(F.asc(parent), F.desc("value"), F.asc(group))
    output: dict[str, list[dict[str, Any]]] = {}
    for row in ordered.collect():
        key = str(row[parent])
        values = output.setdefault(key, [])
        if len(values) < limit:
            values.append(
                {
                    "name": str(row[group]),
                    "value": _rounded(row["value"], integer=value == "count"),
                }
            )
    return output


def _summary_aggregation_expressions() -> list[Any]:
    return [
        F.count("*").alias("record_count"),
        F.avg(F.when(F.col("los") >= 0, F.col("los")).otherwise(None)).alias(
            "avg_los"
        ),
        F.avg(F.when(F.col("charges") >= 0, F.col("charges")).otherwise(None)).alias(
            "avg_charges"
        ),
        F.avg(F.when(F.col("costs") >= 0, F.col("costs")).otherwise(None)).alias(
            "avg_costs"
        ),
        F.sum(F.when(F.col("emergency") == "Y", 1).otherwise(0)).alias(
            "emergency_yes"
        ),
        F.sum(
            F.when(
                F.col("emergency").isNotNull()
                & (F.length(F.col("emergency")) > 0),
                1,
            ).otherwise(0)
        ).alias("emergency_valid_count"),
        F.sum(
            F.when(F.col("medical_surgical").contains("Surgical"), 1).otherwise(0)
        ).alias("surgical_yes"),
        F.sum(
            F.when(
                F.col("medical_surgical").isNotNull()
                & (F.length(F.col("medical_surgical")) > 0),
                1,
            ).otherwise(0)
        ).alias("surgical_valid_count"),
        F.sum(
            F.when(
                F.col("severity").isin(*HIGH_RISK_SEVERITY_VALUES), 1
            ).otherwise(0)
        ).alias("severe_yes"),
        F.sum(
            F.when(F.col("severity").isin(*SEVERITY_VALUES), 1).otherwise(0)
        ).alias("severity_valid_count"),
    ]


def _summary_aggregation(frame: DataFrame, group: str | None = None) -> DataFrame:
    aggregations = _summary_aggregation_expressions()
    return frame.groupBy(group).agg(*aggregations) if group else frame.agg(*aggregations)


def _summary_metrics_from_row(
    row: Any,
    *,
    count_key: str = "record_count",
    count_label: str = "住院出院记录",
) -> list[dict[str, Any]]:
    denominator = row["record_count"]
    severity_denominator = row["severity_valid_count"]
    return [
        metric(count_key, count_label, _rounded(denominator, integer=True), "条"),
        metric("avg_los", "平均住院时长", _rounded(row["avg_los"]), "天"),
        metric("avg_charges", "平均收费", _rounded(row["avg_charges"]), "美元"),
        metric("avg_costs", "平均成本", _rounded(row["avg_costs"]), "美元"),
        metric(
            "emergency_rate",
            "急诊率",
            _rate(row["emergency_yes"], row["emergency_valid_count"]),
            "%",
        ),
        metric(
            "surgical_rate",
            "外科率",
            _rate(row["surgical_yes"], row["surgical_valid_count"]),
            "%",
        ),
        metric(
            "severe_rate",
            "重症率",
            _rate(row["severe_yes"], severity_denominator),
            "%",
        ),
    ]


def grouped_summary_metrics(
    frame: DataFrame,
    group: str,
    *,
    count_key: str = "record_count",
    count_label: str = "住院出院记录",
) -> dict[str, list[dict[str, Any]]]:
    return {
        str(row[group]): _summary_metrics_from_row(
            row, count_key=count_key, count_label=count_label
        )
        for row in _summary_aggregation(frame, group).collect()
    }


def facility_ranking_rows(
    frame: DataFrame, limit: int | None = 10
) -> list[dict[str, Any]]:
    """Rank facilities by string id while retaining a display name.

    A facility name is not a stable identifier: the source contains multiple
    facilities with the same display name.  Grouping by ``facility_id`` keeps
    the ranking aligned with the profile entity keys and the published option
    list.  ``min`` gives a deterministic label if one id appears with more
    than one trimmed name.
    """

    nonempty_id = F.length(F.col("facility_id")) > 0
    display_name = F.when(
        F.length(F.col("facility")) > 0, F.col("facility")
    )
    grouped = (
        frame.where(nonempty_id)
        .groupBy("facility_id")
        .agg(
            F.count("*").alias("value"),
            F.min(display_name).alias("facility"),
        )
    )
    ordered = grouped.orderBy(
        F.desc("value"),
        F.asc(F.coalesce(F.col("facility"), F.col("facility_id"))),
        F.asc("facility_id"),
    )
    if limit is not None:
        ordered = ordered.limit(limit)

    output = []
    for row in ordered.collect():
        output.append(
            {
                "name": str(row["facility"] or row["facility_id"]),
                "value": _rounded(row["value"], integer=True),
            }
        )
    return output


def metric(key: str, label: str, value: int | float, unit: str) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "unit": unit}


def section(
    key: str,
    title: str,
    items: list[dict[str, Any]],
    kind: str = "bar",
) -> dict[str, Any]:
    return {"key": key, "title": title, "type": kind, "items": items}


def summary_metrics(
    frame: DataFrame,
    *,
    count_key: str = "record_count",
    count_label: str = "住院出院记录",
) -> list[dict[str, Any]]:
    """Build reusable metrics with field-valid averages and record denominators."""

    aggregate = frame.agg(*_summary_aggregation_expressions()).first()

    denominator = aggregate["record_count"]
    severity_denominator = aggregate["severity_valid_count"]
    return [
        metric(
            count_key,
            count_label,
            _rounded(denominator, integer=True),
            "条",
        ),
        metric("avg_los", "平均住院时长", _rounded(aggregate["avg_los"]), "天"),
        metric(
            "avg_charges",
            "平均收费",
            _rounded(aggregate["avg_charges"]),
            "美元",
        ),
        metric(
            "avg_costs",
            "平均成本",
            _rounded(aggregate["avg_costs"]),
            "美元",
        ),
        metric(
            "emergency_rate",
            "急诊率",
            _rate(
                aggregate["emergency_yes"],
                aggregate["emergency_valid_count"],
            ),
            "%",
        ),
        metric(
            "surgical_rate",
            "外科率",
            _rate(
                aggregate["surgical_yes"],
                aggregate["surgical_valid_count"],
            ),
            "%",
        ),
        metric(
            "severe_rate",
            "重症率",
            _rate(aggregate["severe_yes"], severity_denominator),
            "%",
        ),
    ]


def business_field_profile(frame: DataFrame) -> dict[str, Any]:
    """Return auditable field-valid counts for fields used by product pages."""

    def nonempty(name: str) -> Any:
        return F.col(name).isNotNull() & (F.length(F.col(name)) > 0)

    definitions = [
        ("facility_id", "机构编号", nonempty("facility_id")),
        (
            "diagnosis",
            "主诊断",
            nonempty("diagnosis_code") & nonempty("diagnosis"),
        ),
        ("severity", "病情严重程度", F.col("severity").isin(*SEVERITY_VALUES)),
        ("mortality", "死亡风险", F.col("mortality").isin(*SEVERITY_VALUES)),
        ("procedure", "主要操作", nonempty("procedure")),
        ("payment", "主支付方式", nonempty("payment")),
        ("charges", "收费", F.col("charges").isNotNull() & (F.col("charges") >= 0)),
        ("costs", "成本", F.col("costs").isNotNull() & (F.col("costs") >= 0)),
        ("los", "住院时长", F.col("los").isNotNull() & (F.col("los") >= 0)),
        ("age", "年龄组", nonempty("age")),
        ("gender", "性别", nonempty("gender")),
        ("admission", "入院方式", nonempty("admission")),
        ("emergency", "急诊标志", nonempty("emergency")),
        ("medical_surgical", "内外科分类", nonempty("medical_surgical")),
    ]
    aggregate = frame.agg(
        F.count("*").alias("base_record_count"),
        *[
            F.sum(F.when(condition, 1).otherwise(0)).alias(key)
            for key, _, condition in definitions
        ],
        F.sum(F.when(F.col("emergency") == "Y", 1).otherwise(0)).alias(
            "emergency_yes"
        ),
        F.sum(
            F.when(F.col("medical_surgical").contains("Surgical"), 1).otherwise(0)
        ).alias("surgical_yes"),
        F.sum(
            F.when(F.col("severity").isin(*HIGH_RISK_SEVERITY_VALUES), 1).otherwise(0)
        ).alias("severe_yes"),
    ).first()
    base_count = int(aggregate["base_record_count"] or 0)
    counts = {key: int(aggregate[key] or 0) for key, _, _ in definitions}
    valid_items = [
        {"name": label, "value": counts[key]}
        for key, label, _ in definitions
    ]
    missing_items = [
        {"name": label, "value": base_count - counts[key]}
        for key, label, _ in definitions
        if base_count - counts[key] > 0
    ]
    field_audit = {
        key: {
            "label": label,
            "applicable_count": base_count,
            "valid_count": counts[key],
            "missing_count": base_count - counts[key],
        }
        for key, label, _ in definitions
    }
    ratio_audit = {
        "emergency_rate": {
            "numerator": int(aggregate["emergency_yes"] or 0),
            "denominator": counts["emergency"],
            "formula": "count(emergency=Y) / valid(emergency)",
        },
        "surgical_rate": {
            "numerator": int(aggregate["surgical_yes"] or 0),
            "denominator": counts["medical_surgical"],
            "formula": "count(medical_surgical contains Surgical) / valid(medical_surgical)",
        },
        "severe_rate": {
            "numerator": int(aggregate["severe_yes"] or 0),
            "denominator": counts["severity"],
            "formula": "count(severity in Major,Extreme) / valid(severity)",
        },
    }
    return {
        "base_count": base_count,
        "counts": counts,
        "valid_items": valid_items,
        "missing_items": missing_items,
        "audit": {
            "formula_version": ANALYTICS_FORMULA_VERSION,
            "base_population": {
                "count": base_count,
                "filters": {
                    "discharge_year": "2021",
                    "length_of_stay": "parsed",
                },
            },
            "fields": field_audit,
            "ratios": ratio_audit,
        },
    }


def _cohort_dimension_frame(frame: DataFrame) -> DataFrame:
    """Add non-null cube dimensions without changing the public clean frame.

    A missing source value is represented by a sentinel before ``cube``.  This
    keeps it distinct from the null values that Spark uses for wildcard rollup
    rows, so wildcard filters include missing values while specific filters do
    not.
    """

    result = frame
    for field in COHORT_FIELDS:
        result = result.withColumn(
            f"_cohort_{field}",
            F.when(
                F.col(field).isNotNull() & (F.length(F.col(field)) > 0),
                F.col(field),
            ).otherwise(F.lit(COHORT_MISSING)),
        )
    return result


def _cohort_options(frame: DataFrame) -> dict[str, list[str]]:
    def values(field: str) -> list[str]:
        return [
            row[field]
            for row in frame.where(
                F.col(field).isNotNull() & (F.length(F.col(field)) > 0)
            )
            .select(field)
            .distinct()
            .orderBy(field)
            .collect()
        ]

    return {COHORT_OPTION_KEYS[field]: values(field) for field in COHORT_FIELDS}


def _cohort_valid_rollup(row_field: str, options: list[str]):
    return F.col(row_field).isNull() | F.col(row_field).isin(options)


def _cohort_tuple_from_row(row: Any) -> tuple[str | None, str | None, str | None]:
    return tuple(
        None if row[f"_cohort_{field}"] is None else str(row[f"_cohort_{field}"])
        for field in COHORT_FIELDS
    )  # type: ignore[return-value]


def _cohort_summary_rows(
    frame: DataFrame, options: dict[str, list[str]]
) -> dict[tuple[str | None, str | None, str | None], Any]:
    """Aggregate all wildcard and finite filter combinations in one cube."""

    decorated = _cohort_dimension_frame(frame)
    grouped = decorated.cube(
        *(f"_cohort_{field}" for field in COHORT_FIELDS)
    ).agg(*_summary_aggregation_expressions())
    valid = grouped.where(
        _cohort_valid_rollup("_cohort_age", options["age_group"])
        & _cohort_valid_rollup("_cohort_gender", options["gender"])
        & _cohort_valid_rollup("_cohort_admission", options["admission_type"])
    )
    return {
        _cohort_tuple_from_row(row): row
        for row in valid.collect()
        if int(row["record_count"] or 0) > 0
    }


def _cohort_section_rows(
    frame: DataFrame,
    group: str,
    options: dict[str, list[str]],
    *,
    limit: int | None = 10,
) -> dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]]:
    """Aggregate one chart dimension for every legal cohort filter."""

    decorated = _cohort_dimension_frame(frame).withColumn(
        "_cohort_item",
        F.when(
            F.col(group).isNotNull() & (F.length(F.col(group)) > 0),
            F.col(group),
        ),
    )
    grouped = decorated.cube(
        *(f"_cohort_{field}" for field in COHORT_FIELDS),
        "_cohort_item",
    ).count()
    valid = grouped.where(
        F.col("_cohort_item").isNotNull()
        & _cohort_valid_rollup("_cohort_age", options["age_group"])
        & _cohort_valid_rollup("_cohort_gender", options["gender"])
        & _cohort_valid_rollup("_cohort_admission", options["admission_type"])
    )
    ordered = valid.orderBy(
        F.asc("_cohort_age"),
        F.asc("_cohort_gender"),
        F.asc("_cohort_admission"),
        F.desc("count"),
        F.asc("_cohort_item"),
    )
    result: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]] = {}
    for row in ordered.collect():
        key = _cohort_tuple_from_row(row)
        values = result.setdefault(key, [])
        if limit is None or len(values) < limit:
            values.append(
                {
                    "name": str(row["_cohort_item"]),
                    "value": _rounded(row["count"], integer=True),
                }
            )
    return result


def _cohort_entity_key(
    values: tuple[str | None, str | None, str | None]
) -> str:
    return "|".join(
        f"{field}={value if value is not None else '*'}"
        for field, value in zip(COHORT_FIELDS, values)
    )


def _cohort_record(
    values: tuple[str | None, str | None, str | None],
    summary_row: Any | None,
    section_values: dict[str, list[dict[str, Any]]],
    options: dict[str, list[str]],
) -> dict[str, Any]:
    filters = {
        COHORT_OPTION_KEYS[field]: value
        for field, value in zip(COHORT_FIELDS, values)
        if value is not None
    }
    if summary_row is None:
        metrics: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
    else:
        metrics = _summary_metrics_from_row(summary_row)
        sections = [
            section("diseases", "主要疾病", section_values["diagnosis"]),
            section("severity", "严重程度", section_values["severity"]),
            section("age", "年龄结构", section_values["age"]),
            section("gender", "性别结构", section_values["gender"]),
        ]
    return record(
        "cohorts",
        _cohort_entity_key(values),
        "住院记录群体分析",
        "有限白名单群体筛选；记录不按患者去重，重症率按严重程度可判定记录计算。",
        metrics,
        sections,
        options if values == (None, None, None) else None,
        filters,
    )


def build_cohort_records(frame: DataFrame) -> list[dict[str, Any]]:
    """Build the wildcard and complete finite cohort snapshot matrix."""

    options = _cohort_options(frame)
    values = (
        [None, *options["age_group"]],
        [None, *options["gender"]],
        [None, *options["admission_type"]],
    )
    summary_rows = _cohort_summary_rows(frame, options)
    section_rows = {
        "diagnosis": _cohort_section_rows(frame, "diagnosis", options, limit=10),
        "severity": _cohort_section_rows(frame, "severity", options, limit=10),
        "age": _cohort_section_rows(frame, "age", options, limit=None),
        "gender": _cohort_section_rows(frame, "gender", options, limit=None),
    }
    records = []
    for combination in product(*values):
        key = tuple(combination)
        records.append(
            _cohort_record(
                key,
                summary_rows.get(key),
                {
                    name: rows.get(key, [])
                    for name, rows in section_rows.items()
                },
                options,
            )
        )
    return records


def _payment_dimension_frame(frame: DataFrame) -> DataFrame:
    """Add payment dimensions without losing missing values in wildcard rows."""

    result = frame
    for field in PAYMENT_FIELDS:
        result = result.withColumn(
            f"_payment_{field}",
            F.when(
                F.col(field).isNotNull() & (F.length(F.col(field)) > 0),
                F.col(field),
            ).otherwise(F.lit(PAYMENT_MISSING)),
        )
    return result


def _payment_options(frame: DataFrame) -> dict[str, list[str]]:
    def values(field: str) -> list[str]:
        return [
            row[field]
            for row in frame.where(
                F.col(field).isNotNull() & (F.length(F.col(field)) > 0)
            )
            .select(field)
            .distinct()
            .orderBy(field)
            .collect()
        ]

    return {PAYMENT_OPTION_KEYS[field]: values(field) for field in PAYMENT_FIELDS}


def _payment_valid_rollup(row_field: str, options: list[str]):
    return F.col(row_field).isNull() | F.col(row_field).isin(options)


def _payment_tuple_from_row(row: Any) -> tuple[str | None, str | None]:
    return tuple(
        None if row[f"_payment_{field}"] is None else str(row[f"_payment_{field}"])
        for field in PAYMENT_FIELDS
    )  # type: ignore[return-value]


def _payment_summary_aggregation_expressions() -> list[Any]:
    return _summary_aggregation_expressions() + [
        F.percentile_approx(
            F.when(F.col("charges") >= 0, F.col("charges")),
            0.5,
            10000,
        ).alias("median_charges")
    ]


def _payment_summary_rows(
    frame: DataFrame, options: dict[str, list[str]]
) -> dict[tuple[str | None, str | None], Any]:
    """Aggregate every wildcard/finite payment filter in one cube."""

    decorated = _payment_dimension_frame(frame)
    grouped = decorated.cube(
        *(f"_payment_{field}" for field in PAYMENT_FIELDS)
    ).agg(*_payment_summary_aggregation_expressions())
    valid = grouped.where(
        _payment_valid_rollup("_payment_payment", options["payment_type"])
        & _payment_valid_rollup("_payment_age", options["age_group"])
    )
    return {
        _payment_tuple_from_row(row): row
        for row in valid.collect()
        if int(row["record_count"] or 0) > 0
    }


def _payment_section_rows(
    frame: DataFrame,
    group: str,
    options: dict[str, list[str]],
    value: str = "count",
    limit: int | None = 10,
) -> dict[tuple[str | None, str | None], list[dict[str, Any]]]:
    """Aggregate one payment page section for every legal filter pair."""

    decorated = _payment_dimension_frame(frame).withColumn(
        "_payment_item",
        F.when(
            F.col(group).isNotNull() & (F.length(F.col(group)) > 0),
            F.col(group),
        ),
    )
    aggregate = (
        F.count("*")
        if value == "count"
        else F.avg(F.col(value))
    ).alias("value")
    grouped = decorated.cube(
        *(f"_payment_{field}" for field in PAYMENT_FIELDS),
        "_payment_item",
    ).agg(aggregate)
    valid = grouped.where(
        F.col("_payment_item").isNotNull()
        & _payment_valid_rollup("_payment_payment", options["payment_type"])
        & _payment_valid_rollup("_payment_age", options["age_group"])
    )
    ordered = valid.orderBy(
        F.asc("_payment_payment"),
        F.asc("_payment_age"),
        F.desc("value"),
        F.asc("_payment_item"),
    )
    result: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
    for row in ordered.collect():
        key = _payment_tuple_from_row(row)
        values = result.setdefault(key, [])
        if limit is None or len(values) < limit:
            values.append(
                {
                    "name": str(row["_payment_item"]),
                    "value": _rounded(row["value"], integer=value == "count"),
                }
            )
    return result


def _payment_metrics_from_row(row: Any) -> list[dict[str, Any]]:
    return [
        metric("record_count", "记录数", _rounded(row["record_count"], integer=True), "条"),
        metric("avg_charges", "平均收费", _rounded(row["avg_charges"]), "美元"),
        metric(
            "median_charges",
            "收费中位数",
            _rounded(row["median_charges"]),
            "美元",
        ),
    ]


def _payment_record(
    values: tuple[str | None, str | None],
    summary_row: Any | None,
    section_values: dict[str, list[dict[str, Any]]],
    options: dict[str, list[str]],
) -> dict[str, Any]:
    filters = {
        PAYMENT_OPTION_KEYS[field]: value
        for field, value in zip(PAYMENT_FIELDS, values)
        if value is not None
    }
    if summary_row is None:
        metrics: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
    else:
        metrics = _payment_metrics_from_row(summary_row)
        sections = [
            section("payment", "主支付方式结构", section_values["payment"]),
            section("charges", "不同支付方式平均收费", section_values["charges"]),
            section("age", "年龄结构", section_values["age"]),
            section("diseases", "主要疾病", section_values["diagnosis"]),
        ]
    return record(
        "payments",
        "|".join(
            f"{field}={value if value is not None else '*'}"
            for field, value in zip(PAYMENT_FIELDS, values)
        ),
        "支付方式分析",
        "核心支付维度为 Payment Typology 1；统计对象为住院出院记录。",
        metrics,
        sections,
        options if values == (None, None) else None,
        filters,
    )


def build_payment_records(frame: DataFrame) -> list[dict[str, Any]]:
    """Build the payment wildcard and complete finite filter matrix."""

    options = _payment_options(frame)
    values = (
        [None, *options["payment_type"]],
        [None, *options["age_group"]],
    )
    summary_rows = _payment_summary_rows(frame, options)
    charge_frame = frame.where(F.coalesce(F.col("valid_money"), F.lit(False)))
    section_rows = {
        "payment": _payment_section_rows(frame, "payment", options, limit=None),
        "charges": _payment_section_rows(
            charge_frame, "payment", options, value="charges", limit=None
        ),
        "age": _payment_section_rows(frame, "age", options, limit=None),
        "diagnosis": _payment_section_rows(frame, "diagnosis", options, limit=10),
    }
    records = []
    for combination in product(*values):
        key = tuple(combination)
        records.append(
            _payment_record(
                key,
                summary_rows.get(key),
                {
                    name: rows.get(key, [])
                    for name, rows in section_rows.items()
                },
                options,
            )
        )
    return records


def _cost_aggregation_expressions() -> list[Any]:
    """Return the named Spark aggregate shared by all legal cost filters."""

    expressions: list[Any] = [
        F.count("*").alias("record_count"),
        F.avg("charges").alias("avg_charges"),
        F.avg("costs").alias("avg_costs"),
        F.avg(F.col("charges") - F.col("costs")).alias("charge_cost_gap"),
        F.avg(
            F.when(F.col("los") > 0, F.col("charges") / F.col("los"))
        ).alias("daily_charges"),
        F.avg(
            F.when(F.col("los") > 0, F.col("costs") / F.col("los"))
        ).alias("daily_costs"),
    ]
    for name, percentile in COST_PERCENTILES:
        expressions.extend(
            [
                F.percentile_approx("charges", percentile, 10000).alias(
                    f"{name}_charges"
                ),
                F.percentile_approx("costs", percentile, 10000).alias(
                    f"{name}_costs"
                ),
            ]
        )
    return expressions


def _cost_summary_rows(frame: DataFrame) -> dict[tuple[Any, Any, Any], Any]:
    """Collect only the small aggregate cube, never raw records."""

    decorated = frame
    grouped_dimensions = []
    for field in COST_DIMENSIONS:
        grouped_field = f"_cost_{field}"
        grouped_dimensions.append(grouped_field)
        decorated = decorated.withColumn(
            grouped_field,
            F.when(
                F.col(field).isNotNull() & (F.length(F.col(field)) > 0),
                F.col(field),
            ).otherwise(F.lit(COST_MISSING)),
        )
    aggregate = decorated.cube(*grouped_dimensions).agg(
        *_cost_aggregation_expressions()
    )
    return {
        tuple(
            None
            if row[f"_cost_{field}"] is None
            else row[f"_cost_{field}"]
            for field in COST_DIMENSIONS
        ): row
        for row in aggregate.collect()
        if int(row["record_count"] or 0) > 0
    }


def _cost_entity_key(
    diagnosis_code: str | None,
    facility_id: str | None,
    severity: str | None,
) -> str:
    return "|".join(
        (
            f"diagnosis={diagnosis_code if diagnosis_code is not None else '*'}",
            f"facility={facility_id if facility_id is not None else '*'}",
            f"severity={severity if severity is not None else '*'}",
        )
    )


def _cost_metrics_from_row(row: Any) -> list[dict[str, Any]]:
    return [
        metric("record_count", "有效费用记录", _rounded(row["record_count"], integer=True), "条"),
        metric("avg_charges", "平均收费", _rounded(row["avg_charges"]), "美元"),
        metric("median_charges", "收费中位数", _rounded(row["p50_charges"]), "美元"),
        metric("p25_charges", "收费P25", _rounded(row["p25_charges"]), "美元"),
        metric("p75_charges", "收费P75", _rounded(row["p75_charges"]), "美元"),
        metric("p90_charges", "收费P90", _rounded(row["p90_charges"]), "美元"),
        metric("avg_costs", "平均成本", _rounded(row["avg_costs"]), "美元"),
        metric("median_costs", "成本中位数", _rounded(row["p50_costs"]), "美元"),
        metric("p25_costs", "成本P25", _rounded(row["p25_costs"]), "美元"),
        metric("p75_costs", "成本P75", _rounded(row["p75_costs"]), "美元"),
        metric("p90_costs", "成本P90", _rounded(row["p90_costs"]), "美元"),
        metric("charge_cost_gap", "平均收费成本差", _rounded(row["charge_cost_gap"]), "美元"),
        metric("daily_charges", "平均单日收费", _rounded(row["daily_charges"]), "美元/天"),
        metric("daily_costs", "平均单日成本", _rounded(row["daily_costs"]), "美元/天"),
    ]


def _cost_comparison_items(
    summaries: dict[tuple[Any, Any, Any], Any],
    current: tuple[str | None, str | None, str | None],
    dimension: str,
    options: list[str | dict[str, str]],
    value_field: str,
    labels: dict[str, str],
) -> list[dict[str, Any]]:
    positions = {name: index for index, name in enumerate(COST_DIMENSIONS)}
    items = []
    selected = current[positions[dimension]]
    candidate_options = [selected] if selected is not None else options
    for option in candidate_options:
        value = str(option["value"]) if isinstance(option, dict) else str(option)
        key = list(current)
        key[positions[dimension]] = value
        row = summaries.get(tuple(key))
        if row is None:
            continue
        items.append({"name": labels.get(value, value), "value": _rounded(row[value_field])})
    return sorted(items, key=lambda item: (-item["value"], item["name"]))[:COST_COMPARISON_LIMIT]


def _cost_sections(
    summaries: dict[tuple[Any, Any, Any], Any],
    current: tuple[str | None, str | None, str | None],
    row: Any,
    diagnosis_options: list[dict[str, str]],
    facility_options: list[dict[str, str]],
    severity_options: list[str],
) -> list[dict[str, Any]]:
    diagnosis_labels = {item["value"]: item["label"] for item in diagnosis_options}
    facility_labels = {item["value"]: item["label"] for item in facility_options}
    sections = [
        section(
            "charges_quantiles",
            "收费分位数",
            [
                {"name": name.upper(), "value": _rounded(row[f"{name}_charges"])}
                for name, _ in COST_PERCENTILES
            ],
        ),
        section(
            "costs_quantiles",
            "成本分位数",
            [
                {"name": name.upper(), "value": _rounded(row[f"{name}_costs"])}
                for name, _ in COST_PERCENTILES
            ],
        ),
        section(
            "charge_cost_distribution",
            "收费与成本分布",
            [
                {"name": "收费均值", "value": _rounded(row["avg_charges"])},
                {"name": "收费中位数", "value": _rounded(row["p50_charges"])},
                {"name": "成本均值", "value": _rounded(row["avg_costs"])},
                {"name": "成本中位数", "value": _rounded(row["p50_costs"])},
            ],
            "table",
        ),
    ]
    diagnosis, facility, _ = current
    if diagnosis is None:
        sections.extend(
            [
                section(
                    "diagnosis_charges",
                    "按疾病比较：平均收费",
                    _cost_comparison_items(
                        summaries, current, "diagnosis_code", diagnosis_options,
                        "avg_charges", diagnosis_labels
                    ),
                ),
                section(
                    "diagnosis_costs",
                    "按疾病比较：平均成本",
                    _cost_comparison_items(
                        summaries, current, "diagnosis_code", diagnosis_options,
                        "avg_costs", diagnosis_labels
                    ),
                ),
            ]
        )
    if facility is None:
        sections.extend(
            [
                section(
                    "facility_charges",
                    "按医院比较：平均收费",
                    _cost_comparison_items(
                        summaries, current, "facility_id", facility_options,
                        "avg_charges", facility_labels
                    ),
                ),
                section(
                    "facility_costs",
                    "按医院比较：平均成本",
                    _cost_comparison_items(
                        summaries, current, "facility_id", facility_options,
                        "avg_costs", facility_labels
                    ),
                ),
            ]
        )
    sections.extend(
        [
            section(
                "severity_charges",
                "按严重程度比较：平均收费",
                _cost_comparison_items(
                    summaries, current, "severity", severity_options,
                    "avg_charges", {value: value for value in severity_options}
                ),
            ),
            section(
                "severity_costs",
                "按严重程度比较：平均成本",
                _cost_comparison_items(
                    summaries, current, "severity", severity_options,
                    "avg_costs", {value: value for value in severity_options}
                ),
            ),
        ]
    )
    return sections


def build_cost_records(
    cost_frame: DataFrame,
    diagnosis_options: list[dict[str, str]],
    facility_options: list[dict[str, str]],
    severity_options: list[str],
) -> list[dict[str, Any]]:
    """Build the wildcard and finite legal cost filter matrix."""

    summaries = _cost_summary_rows(cost_frame)
    diagnosis_values = [item["value"] for item in diagnosis_options]
    facility_values = [item["value"] for item in facility_options]
    keys: list[tuple[str | None, str | None, str | None]] = [
        (None, None, severity) for severity in [None, *severity_options]
    ]
    keys.extend(
        (diagnosis, None, severity)
        for diagnosis in diagnosis_values
        for severity in [None, *severity_options]
    )
    keys.extend(
        (None, facility, severity)
        for facility in facility_values
        for severity in [None, *severity_options]
    )

    records = []
    for current in keys:
        row = summaries.get(current)
        filters = {
            name: value
            for name, value in zip(("diagnosis_code", "facility_id", "severity"), current)
            if value is not None
        }
        wildcard = current == (None, None, None)
        options = {"severity": severity_options} if wildcard else None
        common = (
            "医疗费用与成本分析",
            "费用与成本均值、分位数及有限筛选比较；分位数使用 percentile_approx(accuracy=10000)。",
        )
        if row is None:
            records.append(
                record(
                    "costs", _cost_entity_key(*current), common[0], common[1],
                    options=options, filters=filters
                )
            )
            continue
        records.append(
            record(
                "costs", _cost_entity_key(*current), common[0], common[1],
                _cost_metrics_from_row(row),
                _cost_sections(
                    summaries, current, row, diagnosis_options,
                    facility_options, severity_options
                ),
                options, filters,
            )
        )
    return records


def record(
    module: str,
    entity: str,
    title: str,
    description: str,
    metrics: list[dict[str, Any]] | None = None,
    sections: list[dict[str, Any]] | None = None,
    options: dict[str, Any] | None = None,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "metrics": metrics or [],
        "sections": sections or [],
    }
    if options is not None:
        payload["options"] = options
    if filters is not None:
        payload["filters"] = filters
    return {"module_key": module, "entity_key": entity, "payload": payload}


def _risk_dimension_frame(frame: DataFrame) -> DataFrame:
    """Add non-null cube dimensions while preserving wildcard semantics."""

    result = frame
    for field in RISK_FIELDS:
        result = result.withColumn(
            f"_risk_{field}",
            F.when(
                F.col(field).isNotNull() & (F.length(F.col(field)) > 0),
                F.col(field),
            ).otherwise(F.lit(RISK_MISSING)),
        )
    return result


def _risk_valid_rollup(row_field: str, options: list[str]) -> Any:
    """Accept wildcard cube rows and only published finite option values."""

    return F.col(row_field).isNull() | F.col(row_field).isin(options)


def _risk_tuple_from_row(row: Any) -> tuple[str | None, str | None]:
    return tuple(
        None if row[f"_risk_{field}"] is None else str(row[f"_risk_{field}"])
        for field in RISK_FIELDS
    )  # type: ignore[return-value]


def _risk_summary_aggregation_expressions() -> list[Any]:
    high_risk = F.col("severity").isin(*HIGH_RISK_SEVERITY_VALUES)
    return [
        F.count("*").alias("record_count"),
        F.sum(
            F.when(F.col("severity").isin(*SEVERITY_VALUES), 1).otherwise(0)
        ).alias("severity_valid_count"),
        F.sum(F.when(high_risk, 1).otherwise(0)).alias("high_risk_count"),
        F.avg(
            F.when(high_risk & (F.col("los") >= 0), F.col("los"))
        ).alias("high_risk_avg_los"),
        F.avg(
            F.when(high_risk & (F.col("charges") >= 0), F.col("charges"))
        ).alias("high_risk_avg_charges"),
        F.avg(
            F.when(high_risk & (F.col("costs") >= 0), F.col("costs"))
        ).alias("high_risk_avg_costs"),
    ]


def _risk_summary_rows(
    frame: DataFrame, options: dict[str, Any]
) -> dict[tuple[str | None, str | None], Any]:
    """Aggregate wildcard and every finite risk filter in one cube."""

    decorated = _risk_dimension_frame(frame)
    grouped = decorated.cube(
        *(f"_risk_{field}" for field in RISK_FIELDS)
    ).agg(*_risk_summary_aggregation_expressions())
    valid = grouped.where(
        _risk_valid_rollup("_risk_age", options["age_group"])
        & _risk_valid_rollup("_risk_diagnosis_code", options["diagnosis_code_values"])
    )
    return {
        _risk_tuple_from_row(row): row
        for row in valid.collect()
        if int(row["record_count"] or 0) > 0
    }


def _risk_section_rows(
    frame: DataFrame,
    group: str,
    options: dict[str, Any],
    *,
    limit: int | None,
) -> dict[tuple[str | None, str | None], list[dict[str, Any]]]:
    """Aggregate one risk section for every legal wildcard/finite filter."""

    decorated = _risk_dimension_frame(frame).withColumn(
        "_risk_item",
        F.when(
            F.col(group).isNotNull() & (F.length(F.col(group)) > 0),
            F.col(group),
        ),
    )
    grouped = decorated.cube(
        *(f"_risk_{field}" for field in RISK_FIELDS),
        "_risk_item",
    ).count()
    valid = grouped.where(
        F.col("_risk_item").isNotNull()
        & _risk_valid_rollup("_risk_age", options["age_group"])
        & _risk_valid_rollup(
            "_risk_diagnosis_code", options["diagnosis_code_values"]
        )
    )
    ordered = valid.orderBy(
        F.asc("_risk_age"),
        F.asc("_risk_diagnosis_code"),
        F.desc("count"),
        F.asc("_risk_item"),
    )
    result: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
    for row in ordered.collect():
        key = _risk_tuple_from_row(row)
        values = result.setdefault(key, [])
        if limit is None or len(values) < limit:
            values.append(
                {
                    "name": str(row["_risk_item"]),
                    "value": _rounded(row["count"], integer=True),
                }
            )
    return result


def _risk_metrics_from_row(row: Any) -> list[dict[str, Any]]:
    record_count = int(row["record_count"] or 0)
    if record_count == 0:
        return []

    severity_denominator = int(row["severity_valid_count"] or 0)
    high_risk_count = int(row["high_risk_count"] or 0)
    metrics = [
        metric(
            "severity_valid_count",
            "可判定风险记录",
            severity_denominator,
            "条",
        ),
        metric(
            "high_risk_count",
            "Major/Extreme记录数",
            high_risk_count,
            "条",
        ),
        metric(
            "high_risk_rate",
            "Major/Extreme比例",
            _rate(high_risk_count, severity_denominator),
            "%",
        ),
    ]
    if high_risk_count:
        metrics.extend(
            [
                metric(
                    "avg_los",
                    "高风险平均住院时长",
                    _rounded(row["high_risk_avg_los"]),
                    "天",
                ),
                metric(
                    "avg_charges",
                    "高风险平均收费",
                    _rounded(row["high_risk_avg_charges"]),
                    "美元",
                ),
                metric(
                    "avg_costs",
                    "高风险平均成本",
                    _rounded(row["high_risk_avg_costs"]),
                    "美元",
                ),
            ]
        )
    return metrics


def _risk_entity_key(values: tuple[str | None, str | None]) -> str:
    return "|".join(
        f"{field}={value if value is not None else '*'}"
        for field, value in zip(RISK_ENTITY_FIELDS, values)
    )


def _risk_record(
    values: tuple[str | None, str | None],
    summary_row: Any | None,
    section_values: dict[str, list[dict[str, Any]]],
    options: dict[str, Any],
) -> dict[str, Any]:
    filters = {
        RISK_OPTION_KEYS[field]: value
        for field, value in zip(RISK_FIELDS, values)
        if value is not None
    }
    if summary_row is None:
        metrics: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
    else:
        metrics = _risk_metrics_from_row(summary_row)
        sections = [
            section("severity", "严重程度分布", section_values["severity"]),
            section("mortality", "死亡风险分布", section_values["mortality"]),
            section("disposition", "高风险记录离院去向", section_values["disposition"]),
            section("age", "高风险年龄结构", section_values["age"]),
            section("diseases", "高风险疾病 TOP10", section_values["diseases"]),
        ]
    return record(
        "risks",
        _risk_entity_key(values),
        "病情严重程度与风险分析",
        "Major/Extreme比例以严重程度可判定记录为统计总体；群体统计不构成诊断、治疗或因果判断。",
        metrics,
        sections,
        options if values == (None, None) else None,
        filters,
    )


def build_risk_records(
    frame: DataFrame,
    options: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the wildcard and complete risk filter snapshot matrix."""

    diagnosis_values = [
        item["value"] if isinstance(item, dict) else str(item)
        for item in options["diagnosis_code"]
    ]
    cube_options = {
        "age_group": options["age_group"],
        "diagnosis_code_values": diagnosis_values,
    }
    summary_rows = _risk_summary_rows(frame, cube_options)
    high_risk = frame.where(F.col("severity").isin(*HIGH_RISK_SEVERITY_VALUES))
    section_rows = {
        "severity": _risk_section_rows(frame, "severity", cube_options, limit=None),
        "mortality": _risk_section_rows(frame, "mortality", cube_options, limit=None),
        "disposition": _risk_section_rows(
            high_risk, "disposition", cube_options, limit=None
        ),
        "age": _risk_section_rows(high_risk, "age", cube_options, limit=None),
        "diseases": _risk_section_rows(
            high_risk, "diagnosis", cube_options, limit=10
        ),
    }
    values = (
        [None, *options["age_group"]],
        [None, *diagnosis_values],
    )
    records = []
    for combination in product(*values):
        key = tuple(combination)
        records.append(
            _risk_record(
                key,
                summary_rows.get(key),
                {
                    name: rows.get(key, [])
                    for name, rows in section_rows.items()
                },
                options,
            )
        )
    return records


def build_dashboard_record(frame: DataFrame) -> dict[str, Any]:
    """Build the complete, unfiltered ``dashboard/overview`` payload."""

    dashboard_aggregate = frame.agg(
        F.count("*").alias("record_count"),
        F.countDistinct(
            F.when(F.length(F.col("facility_id")) > 0, F.col("facility_id"))
        ).alias("facility_count"),
        F.avg(F.when(F.col("los") >= 0, F.col("los")).otherwise(None)).alias(
            "avg_los"
        ),
        F.avg(
            F.when(F.col("charges") >= 0, F.col("charges")).otherwise(None)
        ).alias("avg_charges"),
        F.avg(F.when(F.col("costs") >= 0, F.col("costs")).otherwise(None)).alias(
            "avg_costs"
        ),
        F.sum(F.when(F.col("emergency") == "Y", 1).otherwise(0)).alias(
            "emergency_yes"
        ),
        F.sum(
            F.when(
                F.col("emergency").isNotNull()
                & (F.length(F.col("emergency")) > 0),
                1,
            ).otherwise(0)
        ).alias("emergency_valid_count"),
        F.sum(
            F.when(F.col("medical_surgical").contains("Surgical"), 1).otherwise(0)
        ).alias("surgical_yes"),
        F.sum(
            F.when(
                F.col("medical_surgical").isNotNull()
                & (F.length(F.col("medical_surgical")) > 0),
                1,
            ).otherwise(0)
        ).alias("surgical_valid_count"),
        F.sum(
            F.when(F.col("severity").isin(*HIGH_RISK_SEVERITY_VALUES), 1).otherwise(0)
        ).alias("severe_yes"),
        F.sum(
            F.when(F.col("severity").isin(*SEVERITY_VALUES), 1).otherwise(0)
        ).alias("severity_valid_count"),
    )
    aggregate = dashboard_aggregate.first()
    denominator = aggregate["record_count"]
    emergency_denominator = aggregate["emergency_valid_count"]
    surgical_denominator = aggregate["surgical_valid_count"]
    severity_denominator = aggregate["severity_valid_count"]

    metrics = [
        metric(
            "record_count",
            "住院出院记录",
            _rounded(denominator, integer=True),
            "条",
        ),
        metric(
            "facility_count",
            "医疗机构",
            _rounded(aggregate["facility_count"], integer=True),
            "家",
        ),
        metric("avg_los", "平均住院时长", _rounded(aggregate["avg_los"]), "天"),
        metric(
            "avg_charges",
            "平均收费",
            _rounded(aggregate["avg_charges"]),
            "美元",
        ),
        metric(
            "avg_costs",
            "平均成本",
            _rounded(aggregate["avg_costs"]),
            "美元",
        ),
        metric(
            "emergency_rate",
            "急诊率",
            _rate(aggregate["emergency_yes"], emergency_denominator),
            "%",
        ),
        metric(
            "surgical_rate",
            "外科率",
            _rate(aggregate["surgical_yes"], surgical_denominator),
            "%",
        ),
        metric(
            "severe_rate",
            "重症率",
            _rate(aggregate["severe_yes"], severity_denominator),
            "%",
        ),
    ]
    sections = [
        section("age", "年龄结构", rows(frame, "age", limit=None)),
        section("payment", "主要支付方式", rows(frame, "payment", limit=None)),
        section(
            "disease_top10",
            "疾病病例量 TOP10",
            rows(frame, "diagnosis", limit=10),
        ),
        section(
            "hospital_top10",
            "医院病例量 TOP10",
            rows(frame, "facility", limit=10),
        ),
        section("severity", "病情严重程度", rows(frame, "severity", limit=None)),
    ]
    return record(
        "dashboard",
        "overview",
        "医疗运营驾驶舱",
        "从基础住院出院记录观察医疗机构、住院时长、费用与急诊结构；重症率按严重程度可判定记录计算。",
        metrics,
        sections,
    )


def build_data_quality_record(
    frame: DataFrame,
    raw_count: int,
    execution_status: str,
    mysql_status: str,
) -> dict[str, Any]:
    """Build #71 from one named aggregate over the cached clean frame."""

    in_scope = F.coalesce(F.col("in_scope"), F.lit(False))
    valid_record = in_scope & F.col("los").isNotNull()
    invalid_money = in_scope & ~F.coalesce(
        F.col("valid_money"), F.lit(False)
    )
    diagnosis_missing = in_scope & (
        F.col("diagnosis").isNull() | (F.length(F.col("diagnosis")) == 0)
    )
    los_capped = in_scope & F.coalesce(F.col("los_capped"), F.lit(False))

    quality_summary_frame = frame.agg(
        F.sum(F.when(valid_record, 1).otherwise(0)).alias("valid_rows"),
        F.sum(F.when(~in_scope, 1).otherwise(0)).alias("out_of_scope_rows"),
        F.sum(F.when(invalid_money, 1).otherwise(0)).alias(
            "money_parse_or_negative"
        ),
        F.sum(
            F.when(in_scope & F.col("los").isNull(), 1).otherwise(0)
        ).alias("missing_los"),
        F.sum(F.when(diagnosis_missing, 1).otherwise(0)).alias(
            "diagnosis_missing"
        ),
        F.sum(F.when(los_capped, 1).otherwise(0)).alias("los_capped"),
    )
    quality = quality_summary_frame.collect()[0]
    field_profile = business_field_profile(frame.where(valid_record))
    return record(
        "data_quality",
        "summary",
        "数据质量与任务管理",
        "只读展示当前批次与管道检查。",
        [
            metric("raw_rows", "原始记录", raw_count, "条"),
            metric(
                "valid_rows",
                "基础记录总体",
                _rounded(quality["valid_rows"], integer=True),
                "条",
            ),
            metric(
                "severity_valid_rows",
                "严重程度可判定记录",
                field_profile["counts"]["severity"],
                "条",
            ),
            metric(
                "severity_missing_rows",
                "严重程度缺失/不可判定",
                field_profile["base_count"]
                - field_profile["counts"]["severity"],
                "条",
            ),
            metric(
                "out_of_scope_rows",
                "范围外记录",
                _rounded(quality["out_of_scope_rows"], integer=True),
                "条",
            ),
            metric(
                "money_parse_or_negative",
                "费用解析/负值异常",
                _rounded(quality["money_parse_or_negative"], integer=True),
                "条",
            ),
            metric(
                "missing_los",
                "住院时长解析异常",
                _rounded(quality["missing_los"], integer=True),
                "条",
            ),
            metric(
                "diagnosis_missing",
                "主诊断描述缺失",
                _rounded(quality["diagnosis_missing"], integer=True),
                "条",
            ),
            metric(
                "los_capped",
                "住院时长120+截断",
                _rounded(quality["los_capped"], integer=True),
                "条",
            ),
        ],
        [
            section(
                "storage",
                "存储与服务检查",
                [
                    {"name": "HDFS", "value": "CHECK_REQUIRED"},
                    {"name": "Hive", "value": "CHECK_REQUIRED"},
                    {"name": "MySQL", "value": mysql_status},
                    {"name": "PySpark任务", "value": execution_status},
                ],
                "status",
            ),
            section(
                "field_validity",
                "业务字段有效记录数",
                field_profile["valid_items"],
            ),
            section(
                "field_missing",
                "存在缺失或不可判定的业务字段",
                field_profile["missing_items"],
            ),
        ],
        {
            "formula_version": field_profile["audit"]["formula_version"],
            "audit": field_profile["audit"],
        },
    )


def _legacy_build_records(
    frame: DataFrame,
    raw_count: int,
    execution_status: str = "PASS",
) -> list[dict[str, Any]]:
    """Build the shared snapshot; dashboard is always the first record."""

    dashboard = build_dashboard_record(frame)
    valid = frame.where(F.col("valid_money") & F.col("los").isNotNull())
    common = summary_metrics(valid)
    facility_count = (
        valid.where(F.length("facility_id") > 0)
        .select("facility_id")
        .distinct()
        .count()
    )
    records = [dashboard]

    facilities = (
        valid.where(F.length("facility_id") > 0)
        .select("facility_id", "facility")
        .dropDuplicates(["facility_id"])
    )
    facility_options = [
        {"value": row.facility_id, "label": row.facility or row.facility_id}
        for row in facilities.orderBy("facility_id").limit(500).collect()
    ]
    records.append(
        record(
            "hospitals",
            "index",
            "医院运营分析",
            "医院排行与双院对比。",
            [metric("facility_count", "可分析医疗机构", facility_count, "家")],
            [section("ranking", "医院病例量排行", rows(valid, "facility"))],
            {"facilities": facility_options},
        )
    )
    for option in facility_options:
        subset = valid.where(F.col("facility_id") == option["value"])
        records.append(
            record(
                "hospitals",
                f"profile:{option['value']}",
                option["label"],
                "医疗机构运营画像；重症率按严重程度可判定记录计算。",
                summary_metrics(
                    subset,
                    count_key="case_count",
                    count_label="病例量",
                ),
                [
                    section(
                        "diseases",
                        "主要疾病 TOP5",
                        rows(subset, "diagnosis", limit=5),
                    ),
                    section(
                        "medical_surgical",
                        "内外科结构",
                        rows(subset, "medical_surgical"),
                    ),
                    section(
                        "severity",
                        "病情严重程度",
                        rows(subset, "severity", limit=None),
                    ),
                ],
            )
        )

    diagnoses = (
        valid.where(F.length("diagnosis_code") > 0)
        .select("diagnosis_code", "diagnosis")
        .dropDuplicates(["diagnosis_code"])
    )
    diagnosis_options = [
        {"value": row.diagnosis_code, "label": row.diagnosis or row.diagnosis_code}
        for row in diagnoses.orderBy("diagnosis_code").limit(1000).collect()
    ]
    records.append(
        record(
            "diseases",
            "index",
            "疾病画像分析",
            "按主诊断类别观察群体画像。",
            [metric("diagnosis_count", "有效诊断类别", len(diagnosis_options), "类")],
            [section("top10", "疾病病例量 TOP10", rows(valid, "diagnosis"))],
            {"diagnoses": diagnosis_options},
        )
    )
    for option in diagnosis_options:
        subset = valid.where(F.col("diagnosis_code") == option["value"])
        records.append(
            record(
                "diseases",
                f"profile:{option['value']}",
                option["label"],
                "该诊断类别的住院出院记录群体画像；重症率按严重程度可判定记录计算。",
                summary_metrics(subset),
                [
                    section("age", "年龄结构", rows(subset, "age")),
                    section("gender", "性别结构", rows(subset, "gender")),
                    section("severity", "严重程度", rows(subset, "severity")),
                    section("mortality", "死亡风险", rows(subset, "mortality")),
                    section(
                        "procedures",
                        "常见操作",
                        rows(subset, "procedure", limit=5),
                    ),
                    section("hospitals", "主要医院", rows(subset, "facility", limit=5)),
                ],
            )
        )

    def option_values(name: str) -> list[str]:
        return [
            row[name]
            for row in valid.where(F.length(name) > 0)
            .select(name)
            .distinct()
            .orderBy(name)
            .collect()
        ]

    records.append(
        record(
            "cohorts",
            "age=*|gender=*|admission=*",
            "住院记录群体分析",
            "有限白名单群体筛选；记录不按患者去重，重症率按严重程度可判定记录计算。",
            common,
            [
                section("diseases", "主要疾病", rows(valid, "diagnosis")),
                section("severity", "严重程度", rows(valid, "severity")),
                section("age", "年龄结构", rows(valid, "age")),
            ],
            {
                "age_group": option_values("age"),
                "gender": option_values("gender"),
                "admission_type": option_values("admission"),
            },
            {},
        )
    )

    quantiles = valid.agg(
        *[
            F.percentile_approx("charges", percentile, 10000).alias(
                f"p{int(percentile * 100)}"
            )
            for percentile in (0.25, 0.5, 0.75, 0.9)
        ],
        F.avg("charges").alias("avg_charges"),
        F.avg("costs").alias("avg_costs"),
        F.avg(F.col("charges") - F.col("costs")).alias("gap"),
        F.avg(F.col("charges") / F.when(F.col("los") > 0, F.col("los"))).alias(
            "daily_charges"
        ),
        F.avg(F.col("costs") / F.when(F.col("los") > 0, F.col("los"))).alias(
            "daily_costs"
        ),
    ).first()
    cost_metrics = [
        metric("avg_charges", "平均收费", _rounded(quantiles.avg_charges), "美元"),
        metric(
            "median_charges",
            "收费中位数",
            _rounded(quantiles.p50),
            "美元",
        ),
        metric("p90_charges", "收费P90", _rounded(quantiles.p90), "美元"),
        metric("avg_costs", "平均成本", _rounded(quantiles.avg_costs), "美元"),
        metric(
            "charge_cost_gap",
            "平均收费成本差",
            _rounded(quantiles.gap),
            "美元",
        ),
        metric(
            "daily_charges",
            "平均单日收费",
            _rounded(quantiles.daily_charges),
            "美元/天",
        ),
        metric(
            "daily_costs",
            "平均单日成本",
            _rounded(quantiles.daily_costs),
            "美元/天",
        ),
    ]
    records.append(
        record(
            "costs",
            "diagnosis=*|facility=*|severity=*",
            "医疗费用与成本分析",
            "分位数使用 percentile_approx(accuracy=10000)。",
            cost_metrics,
            [
                section(
                    "quantiles",
                    "收费分位数",
                    [
                        {
                            "name": name,
                            "value": _rounded(getattr(quantiles, name.lower())),
                        }
                        for name in ("P25", "P50", "P75", "P90")
                    ],
                ),
                section(
                    "severity",
                    "不同严重程度平均收费",
                    rows(valid, "severity", "charges"),
                ),
            ],
            {"severity": option_values("severity")},
            {},
        )
    )

    high_risk = valid.where(F.col("severity").isin(*HIGH_RISK_SEVERITY_VALUES))
    records.append(
        record(
            "risks",
            "age=*|diagnosis=*",
            "病情严重程度与风险分析",
            "群体统计，不构成诊断、治疗或因果判断。",
            summary_metrics(high_risk),
            [
                section("severity", "严重程度分布", rows(valid, "severity")),
                section("mortality", "死亡风险分布", rows(valid, "mortality")),
                section(
                    "disposition",
                    "高风险记录离院去向",
                    rows(high_risk, "disposition"),
                ),
                section("age", "高风险年龄结构", rows(high_risk, "age")),
                section("diseases", "高风险疾病", rows(high_risk, "diagnosis")),
            ],
            {"age_group": option_values("age")},
            {},
        )
    )
    records.append(
        record(
            "payments",
            "payment=*|age=*",
            "支付方式分析",
            "核心支付维度为 Payment Typology 1。",
            common,
            [
                section("payment", "主支付方式结构", rows(valid, "payment")),
                section(
                    "charges",
                    "不同支付方式平均收费",
                    rows(valid, "payment", "charges"),
                ),
                section("age", "年龄结构", rows(valid, "age")),
                section("diseases", "主要疾病", rows(valid, "diagnosis")),
            ],
            {
                "payment_type": option_values("payment"),
                "age_group": option_values("age"),
            },
            {},
        )
    )

    invalid_money = frame.where(
        ~F.coalesce(F.col("valid_money"), F.lit(False))
    ).count()
    records.append(
        record(
            "data_quality",
            "summary",
            "数据质量与任务管理",
            "只读展示当前批次与管道检查。",
            [
                metric("raw_rows", "原始记录", raw_count, "条"),
                metric("valid_rows", "有效记录", valid.count(), "条"),
                metric(
                    "money_parse_or_negative",
                    "费用解析/负值异常",
                    invalid_money,
                    "条",
                ),
                metric(
                    "diagnosis_missing",
                    "诊断缺失",
                    frame.where(
                        F.col("diagnosis").isNull()
                        | (F.length("diagnosis") == 0)
                    ).count(),
                    "条",
                ),
                metric(
                    "los_capped",
                    "住院时长120+截断",
                    frame.where("los_capped").count(),
                    "条",
                ),
            ],
            [
                section(
                    "storage",
                    "存储与服务检查",
                    [
                        {"name": "HDFS", "value": "CHECK_REQUIRED"},
                        {"name": "Hive", "value": "CHECK_REQUIRED"},
                        {"name": "MySQL", "value": "NOT_PUBLISHED"},
                        {"name": "PySpark任务", "value": execution_status},
                    ],
                    "status",
                )
            ],
        )
    )
    return records


def build_records(
    frame: DataFrame,
    raw_count: int,
    execution_status: str = "PASS",
    mysql_status: str = "NOT_PUBLISHED",
) -> list[dict[str, Any]]:
    """Build all modules with batched grouped actions over the cached frame."""

    scoped = frame.where(
        F.coalesce(F.col("in_scope"), F.lit(False))
        & F.col("los").isNotNull()
    )
    cost_frame = scoped.where(F.col("valid_money"))
    valid_diagnosis = scoped.where(
        (F.length(F.col("diagnosis_code")) > 0)
        & (F.length(F.col("diagnosis")) > 0)
    )
    overall = {
        "age": rows(scoped, "age", limit=None),
        "severity": rows(scoped, "severity", limit=None),
        "diagnosis": rows(valid_diagnosis, "diagnosis", limit=None),
    }

    def option_values(name: str) -> list[str]:
        return [
            row[name]
            for row in scoped.where(
                F.col(name).isNotNull() & (F.length(F.col(name)) > 0)
            )
            .select(name)
            .distinct()
            .orderBy(name)
            .collect()
        ]

    dashboard_frame = frame.where(
        F.coalesce(F.col("in_scope"), F.lit(False))
        & F.col("los").isNotNull()
    )
    dashboard = build_dashboard_record(dashboard_frame)
    records: list[dict[str, Any]] = [dashboard]

    facility_options_frame = (
        scoped.where(F.length(F.col("facility_id")) > 0)
        .groupBy("facility_id")
        .agg(
            F.min(
                F.when(
                    F.length(F.col("facility")) > 0, F.col("facility")
                )
            ).alias("facility")
        )
        .orderBy(F.asc("facility_id"))
    )
    facility_options = [
        {"value": row.facility_id, "label": row.facility or row.facility_id}
        for row in facility_options_frame.collect()
    ]
    facility_count = len(facility_options)
    facility_summaries = grouped_summary_metrics(
        scoped,
        "facility_id",
        count_key="case_count",
        count_label="病例量",
    )
    facility_diseases = grouped_rows(scoped, "facility_id", "diagnosis", limit=5)
    facility_types = grouped_rows(scoped, "facility_id", "medical_surgical")
    facility_severities = grouped_rows(scoped, "facility_id", "severity")
    records.append(
        record(
            "hospitals",
            "index",
            "医院运营分析",
            "医院排行与双院对比。",
            [metric("facility_count", "可分析医疗机构", facility_count, "家")],
            [section("ranking", "医院病例量排行", facility_ranking_rows(scoped))],
            {"facilities": facility_options},
        )
    )
    for option in facility_options:
        facility_id = option["value"]
        records.append(
            record(
                "hospitals",
                f"profile:{facility_id}",
                option["label"],
                "医疗机构运营画像；重症率按严重程度可判定记录计算。",
                facility_summaries.get(facility_id, []),
                [
                    section("diseases", "主要疾病 TOP5", facility_diseases.get(facility_id, [])),
                    section("medical_surgical", "内外科结构", facility_types.get(facility_id, [])),
                    section("severity", "病情严重程度", facility_severities.get(facility_id, [])),
                ],
            )
        )

    diagnosis_options_frame = (
        valid_diagnosis
        .groupBy("diagnosis_code")
        .agg(
            F.min(
                F.when(
                    F.length(F.col("diagnosis")) > 0, F.col("diagnosis")
                )
            ).alias("diagnosis")
        )
    )
    diagnosis_options = [
        {"value": row.diagnosis_code, "label": row.diagnosis or row.diagnosis_code}
        for row in diagnosis_options_frame.orderBy("diagnosis_code").collect()
    ]
    diagnosis_summaries = grouped_summary_metrics(valid_diagnosis, "diagnosis_code")
    diagnosis_ages = grouped_rows(valid_diagnosis, "diagnosis_code", "age")
    diagnosis_genders = grouped_rows(valid_diagnosis, "diagnosis_code", "gender")
    diagnosis_severities = grouped_rows(valid_diagnosis, "diagnosis_code", "severity")
    diagnosis_mortality = grouped_rows(valid_diagnosis, "diagnosis_code", "mortality")
    diagnosis_procedures = grouped_rows(valid_diagnosis, "diagnosis_code", "procedure", limit=5)
    diagnosis_facilities = grouped_rows(valid_diagnosis, "diagnosis_code", "facility", limit=5)
    records.append(
        record(
            "diseases",
            "index",
            "疾病画像分析",
            "按主诊断类别观察群体画像。",
            [metric("diagnosis_count", "有效诊断类别", len(diagnosis_options), "类")],
            [section("top10", "疾病病例量 TOP10", overall["diagnosis"][:10])],
            {"diagnoses": diagnosis_options},
        )
    )
    for option in diagnosis_options:
        diagnosis_code = option["value"]
        records.append(
            record(
                "diseases",
                f"profile:{diagnosis_code}",
                option["label"],
                "该诊断类别的住院出院记录群体画像；重症率按严重程度可判定记录计算。",
                diagnosis_summaries[diagnosis_code],
                [
                    section("age", "年龄结构", diagnosis_ages.get(diagnosis_code, [])),
                    section("gender", "性别结构", diagnosis_genders.get(diagnosis_code, [])),
                    section("severity", "严重程度", diagnosis_severities.get(diagnosis_code, [])),
                    section("mortality", "死亡风险", diagnosis_mortality.get(diagnosis_code, [])),
                    section("procedures", "常见操作", diagnosis_procedures.get(diagnosis_code, [])),
                    section("hospitals", "主要医院", diagnosis_facilities.get(diagnosis_code, [])),
                ],
            )
        )

    records.extend(build_cohort_records(scoped))

    records.extend(
        build_cost_records(
            cost_frame,
            diagnosis_options,
            facility_options,
            option_values("severity"),
        )
    )

    records.extend(
        build_risk_records(
            scoped,
            {
                "age_group": option_values("age"),
                "diagnosis_code": diagnosis_options,
            },
        )
    )
    records.extend(build_payment_records(scoped))

    records.append(
        build_data_quality_record(
            frame, raw_count, execution_status, mysql_status
        )
    )
    return records


def _validate_input_columns(raw: DataFrame) -> None:
    required_names = ("year", "diagnosis", "age", "admission", "los", "charges", "costs")
    missing = [
        FIELDS[name]
        for name in required_names
        if not any(column in raw.columns for column in FIELD_ALIASES.get(name, (FIELDS[name],)))
    ]
    if missing:
        raise ValueError("输入 CSV 缺少必要字段: " + ", ".join(missing))


def build_document(
    cleaned: DataFrame,
    input_path: Path,
    digest: str,
    generated_at: str,
    module: str,
    mysql_status: str,
) -> tuple[dict[str, Any], int]:
    """Materialize the shared frame once and build the requested snapshot."""

    raw_count = cleaned.count()
    fixture_root = (REPO_ROOT / "data" / "fixtures").resolve()
    execution_status = (
        "FIXTURE_ONLY"
        if input_path.resolve().parent == fixture_root
        else "PASS"
    )
    effective_mysql_status = (
        "CHECK_REQUIRED"
        if execution_status == "FIXTURE_ONLY"
        else mysql_status
    )
    dashboard_frame = cleaned.where(
        F.coalesce(F.col("in_scope"), F.lit(False))
        & F.col("los").isNotNull()
    )
    records = (
        [build_dashboard_record(dashboard_frame)]
        if module == "dashboard"
        else build_payment_records(dashboard_frame)
        if module == "payments"
        else build_records(
            cleaned,
            raw_count,
            execution_status,
            effective_mysql_status,
        )
    )
    document = {
        "data_version": build_data_version(input_path, digest),
        "generated_at": normalize_utc_timestamp(generated_at),
        "input": {
            "file_name": input_path.name,
            "sha256": digest,
            "raw_rows": raw_count,
        },
        "records": records,
    }
    return validate_snapshot_document(document), raw_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at")
    parser.add_argument(
        "--module",
        choices=("all", "dashboard", "payments"),
        default="all",
        help=(
            "默认生成全量共享快照；dashboard 只生成 dashboard/overview；"
            "payments 只生成支付方式模块，仍复用统一清洗帧。"
        ),
    )
    parser.add_argument(
        "--master",
        default="local[1]",
        help="Spark master；默认使用 1 个本地 worker，避免验收电脑耗尽内存。",
    )
    parser.add_argument(
        "--mysql-status",
        choices=("NOT_PUBLISHED", "VERIFIED"),
        default="NOT_PUBLISHED",
        help="真实 MySQL 发布证据取得前保持 NOT_PUBLISHED；取得证据后才可使用 VERIFIED。",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    digest = sha256_file(input_path)
    generated_at = normalize_generated_at(args.generated_at)
    spark = (
        SparkSession.builder.master(args.master)
        .appName("yishuyunce-full-analytics")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    cleaned = None
    try:
        raw = (
            spark.read.option("header", "true")
            .option("inferSchema", "false")
            .option("mode", "FAILFAST")
            .csv(str(input_path))
        )
        _validate_input_columns(raw)
        cleaned = clean_frame(raw).persist(StorageLevel.MEMORY_AND_DISK)
        document, raw_count = build_document(
            cleaned,
            input_path,
            digest,
            generated_at,
            args.module,
            args.mysql_status,
        )
    finally:
        if cleaned is not None:
            cleaned.unpersist(blocking=True)
        spark.stop()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    dashboard = next(
        (
            record
            for record in document["records"]
            if record["module_key"] == "dashboard"
            and record["entity_key"] == "overview"
        ),
        None,
    )
    summary: dict[str, Any] = {
        "status": "PASS",
        "module": args.module,
        "records": len(document["records"]),
        "raw_rows": raw_count,
        "data_version": document["data_version"],
        "generated_at": document["generated_at"],
    }
    if dashboard is not None:
        summary.update(
            {
                "dashboard_metric_keys": [
                    item["key"] for item in dashboard["payload"]["metrics"]
                ],
                "dashboard_section_counts": {
                    section_value["key"]: len(section_value["items"])
                    for section_value in dashboard["payload"]["sections"]
                },
            }
        )
    if args.module == "payments":
        summary["payment_key_count"] = sum(
            record["module_key"] == "payments" for record in document["records"]
        )
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
