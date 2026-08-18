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


def _summary_aggregation(frame: DataFrame, group: str | None = None) -> DataFrame:
    aggregations = [
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
            F.when(F.col("medical_surgical").contains("Surgical"), 1).otherwise(0)
        ).alias("surgical_yes"),
        F.sum(F.when(F.col("severity").isin("Major", "Extreme"), 1).otherwise(0)).alias(
            "severe_yes"
        ),
    ]
    return frame.groupBy(group).agg(*aggregations) if group else frame.agg(*aggregations)


def _summary_metrics_from_row(
    row: Any,
    *,
    count_key: str = "record_count",
    count_label: str = "住院出院记录",
) -> list[dict[str, Any]]:
    denominator = row["record_count"]
    return [
        metric(count_key, count_label, _rounded(denominator, integer=True), "条"),
        metric("avg_los", "平均住院时长", _rounded(row["avg_los"]), "天"),
        metric("avg_charges", "平均收费", _rounded(row["avg_charges"]), "美元"),
        metric("avg_costs", "平均成本", _rounded(row["avg_costs"]), "美元"),
        metric("emergency_rate", "急诊率", _rate(row["emergency_yes"], denominator), "%"),
        metric("surgical_rate", "外科率", _rate(row["surgical_yes"], denominator), "%"),
        metric("severe_rate", "重症率", _rate(row["severe_yes"], denominator), "%"),
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

    aggregate = frame.agg(
        F.count("*").alias("record_count"),
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
            F.when(F.col("medical_surgical").contains("Surgical"), 1).otherwise(0)
        ).alias("surgical_yes"),
        F.sum(
            F.when(F.col("severity").isin("Major", "Extreme"), 1).otherwise(0)
        ).alias("severe_yes"),
    ).first()

    denominator = aggregate["record_count"]
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
            _rate(aggregate["emergency_yes"], denominator),
            "%",
        ),
        metric(
            "surgical_rate",
            "外科率",
            _rate(aggregate["surgical_yes"], denominator),
            "%",
        ),
        metric(
            "severe_rate",
            "重症率",
            _rate(aggregate["severe_yes"], denominator),
            "%",
        ),
    ]


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
            F.when(F.col("medical_surgical").contains("Surgical"), 1).otherwise(0)
        ).alias("surgical_yes"),
        F.sum(
            F.when(F.col("severity").isin("Major", "Extreme"), 1).otherwise(0)
        ).alias("severe_yes"),
    )
    aggregate = dashboard_aggregate.first()
    denominator = aggregate["record_count"]

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
            _rate(aggregate["emergency_yes"], denominator),
            "%",
        ),
        metric(
            "surgical_rate",
            "外科率",
            _rate(aggregate["surgical_yes"], denominator),
            "%",
        ),
        metric(
            "severe_rate",
            "重症率",
            _rate(aggregate["severe_yes"], denominator),
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
        "从住院出院记录观察医疗机构、住院时长、费用与急诊结构。",
        metrics,
        sections,
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
                "医疗机构运营画像。",
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
                "该诊断类别的住院出院记录群体画像。",
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
            "有限白名单群体筛选；记录不按患者去重。",
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

    high_risk = valid.where(F.col("severity").isin("Major", "Extreme"))
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
) -> list[dict[str, Any]]:
    """Build all modules with batched grouped actions over the cached frame."""

    scoped = frame.where(
        F.coalesce(F.col("in_scope"), F.lit(False))
        & F.col("los").isNotNull()
    )
    cost_frame = scoped.where(F.col("valid_money"))
    common = summary_metrics(scoped)
    overall = {
        name: rows(scoped, name, limit=None)
        for name in ("age", "payment", "diagnosis", "severity")
    }
    dashboard_frame = frame.where(F.coalesce(F.col("in_scope"), F.lit(False)))
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
                "医疗机构运营画像。",
                facility_summaries.get(facility_id, []),
                [
                    section("diseases", "主要疾病 TOP5", facility_diseases.get(facility_id, [])),
                    section("medical_surgical", "内外科结构", facility_types.get(facility_id, [])),
                ],
            )
        )

    diagnosis_options_frame = (
        scoped.where(F.length(F.col("diagnosis_code")) > 0)
        .select("diagnosis_code", "diagnosis")
        .dropDuplicates(["diagnosis_code"])
    )
    diagnosis_options = [
        {"value": row.diagnosis_code, "label": row.diagnosis or row.diagnosis_code}
        for row in diagnosis_options_frame.orderBy("diagnosis_code").limit(1000).collect()
    ]
    diagnosis_summaries = grouped_summary_metrics(scoped, "diagnosis_code")
    diagnosis_ages = grouped_rows(scoped, "diagnosis_code", "age")
    diagnosis_genders = grouped_rows(scoped, "diagnosis_code", "gender")
    diagnosis_severities = grouped_rows(scoped, "diagnosis_code", "severity")
    diagnosis_mortality = grouped_rows(scoped, "diagnosis_code", "mortality")
    diagnosis_procedures = grouped_rows(scoped, "diagnosis_code", "procedure", limit=5)
    diagnosis_facilities = grouped_rows(scoped, "diagnosis_code", "facility", limit=5)
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
                "该诊断类别的住院出院记录群体画像。",
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

    def option_values(name: str) -> list[str]:
        return [
            row[name]
            for row in scoped.where(F.length(F.col(name)) > 0)
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
            "有限白名单群体筛选；记录不按患者去重。",
            common,
            [
                section("diseases", "主要疾病", overall["diagnosis"][:10]),
                section("severity", "严重程度", overall["severity"][:10]),
                section("age", "年龄结构", overall["age"][:10]),
            ],
            {
                "age_group": option_values("age"),
                "gender": option_values("gender"),
                "admission_type": option_values("admission"),
            },
            {},
        )
    )

    quantiles = cost_frame.agg(
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
        metric("median_charges", "收费中位数", _rounded(quantiles.p50), "美元"),
        metric("p90_charges", "收费P90", _rounded(quantiles.p90), "美元"),
        metric("avg_costs", "平均成本", _rounded(quantiles.avg_costs), "美元"),
        metric("charge_cost_gap", "平均收费成本差", _rounded(quantiles.gap), "美元"),
        metric("daily_charges", "平均单日收费", _rounded(quantiles.daily_charges), "美元/天"),
        metric("daily_costs", "平均单日成本", _rounded(quantiles.daily_costs), "美元/天"),
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
                        {"name": name, "value": _rounded(quantiles[name.lower()])}
                        for name in ("P25", "P50", "P75", "P90")
                    ],
                ),
                section(
                    "severity",
                    "不同严重程度平均收费",
                    rows(cost_frame, "severity", "charges"),
                ),
            ],
            {"severity": option_values("severity")},
            {},
        )
    )

    high_risk = scoped.where(F.col("severity").isin("Major", "Extreme"))
    records.append(
        record(
            "risks",
            "age=*|diagnosis=*",
            "病情严重程度与风险分析",
            "群体统计，不构成诊断、治疗或因果判断。",
            summary_metrics(high_risk),
            [
                section("severity", "严重程度分布", overall["severity"][:10]),
                section("mortality", "死亡风险分布", rows(scoped, "mortality")),
                section("disposition", "高风险记录离院去向", rows(high_risk, "disposition")),
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
                section("payment", "主支付方式结构", overall["payment"][:10]),
                section("charges", "不同支付方式平均收费", rows(cost_frame, "payment", "charges")),
                section("age", "年龄结构", overall["age"][:10]),
                section("diseases", "主要疾病", overall["diagnosis"][:10]),
            ],
            {
                "payment_type": option_values("payment"),
                "age_group": option_values("age"),
            },
            {},
        )
    )

    out_of_scope = frame.where(~F.coalesce(F.col("in_scope"), F.lit(False))).count()
    invalid_money = frame.where(
        F.coalesce(F.col("in_scope"), F.lit(False))
        & ~F.coalesce(F.col("valid_money"), F.lit(False))
    ).count()
    missing_los = frame.where(
        F.coalesce(F.col("in_scope"), F.lit(False)) & F.col("los").isNull()
    ).count()
    records.append(
        record(
            "data_quality",
            "summary",
            "数据质量与任务管理",
            "只读展示当前批次与管道检查。",
            [
                metric("raw_rows", "原始记录", raw_count, "条"),
                metric("valid_rows", "纳入分析记录", scoped.count(), "条"),
                metric("out_of_scope_rows", "范围外记录", out_of_scope, "条"),
                metric("money_parse_or_negative", "费用解析/负值异常", invalid_money, "条"),
                metric("missing_los", "住院时长解析异常", missing_los, "条"),
                metric(
                    "diagnosis_missing",
                    "诊断缺失",
                    scoped.where(
                        F.col("diagnosis").isNull() | (F.length("diagnosis") == 0)
                    ).count(),
                    "条",
                ),
                metric("los_capped", "住院时长120+截断", frame.where("los_capped").count(), "条"),
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
) -> tuple[dict[str, Any], int]:
    """Materialize the shared frame once and build the requested snapshot."""

    raw_count = cleaned.count()
    execution_status = (
        "FIXTURE_ONLY"
        if input_path.resolve() == (REPO_ROOT / "data" / "fixtures" / "sparcs_mvp_sample.csv").resolve()
        else "PASS"
    )
    dashboard_frame = cleaned.where(
        F.coalesce(F.col("in_scope"), F.lit(False))
        & F.col("los").isNotNull()
    )
    records = (
        [build_dashboard_record(dashboard_frame)]
        if module == "dashboard"
        else build_records(cleaned, raw_count, execution_status)
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
        choices=("all", "dashboard"),
        default="all",
        help="默认生成全量共享快照；dashboard 只生成 #43 的 dashboard/overview。",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    digest = sha256_file(input_path)
    generated_at = normalize_generated_at(args.generated_at)
    spark = (
        SparkSession.builder.master("local[*]")
        .appName("yishuyunce-full-analytics")
        .config("spark.ui.enabled", "false")
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
            cleaned, input_path, digest, generated_at, args.module
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
        record
        for record in document["records"]
        if record["module_key"] == "dashboard"
        and record["entity_key"] == "overview"
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "module": args.module,
                "records": len(document["records"]),
                "raw_rows": raw_count,
                "data_version": document["data_version"],
                "generated_at": document["generated_at"],
                "dashboard_metric_keys": [
                    item["key"] for item in dashboard["payload"]["metrics"]
                ],
                "dashboard_section_counts": {
                    section_value["key"]: len(section_value["items"])
                    for section_value in dashboard["payload"]["sections"]
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
