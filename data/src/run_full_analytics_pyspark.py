"""Build every read-only product snapshot from one cached PySpark clean frame.

The raw CSV is loaded once. All product modules reuse the same normalized,
persisted frame and therefore share one data_version/generated_at boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.storagelevel import StorageLevel


FIELDS = {
    "diagnosis": "CCSR Diagnosis Description", "diagnosis_code": "CCSR Diagnosis Code",
    "age": "Age Group", "gender": "Gender", "race": "Race", "ethnicity": "Ethnicity",
    "admission": "Type of Admission", "los": "Length of Stay", "charges": "Total Charges",
    "costs": "Total Costs", "emergency": "Emergency Department Indicator",
    "facility": "Facility Name", "facility_id": "Facility ID", "severity": "APR Severity of Illness Description",
    "mortality": "APR Risk of Mortality", "disposition": "Patient Disposition",
    "payment": "Payment Typology 1", "medical_surgical": "APR Medical Surgical Description",
    "procedure": "CCSR Procedure Description", "area": "Health Service Area",
}


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_frame(raw: DataFrame) -> DataFrame:
    def source(name: str):
        column = FIELDS[name]
        return F.col(column) if column in raw.columns else F.lit(None)

    trim = lambda name: F.trim(source(name).cast("string"))
    money = lambda name: F.regexp_replace(trim(name), ",", "").cast("decimal(20,2)")
    los_text = trim("los")
    return raw.select(
        *[trim(name).alias(name) for name in ("diagnosis", "diagnosis_code", "age", "gender", "race", "ethnicity", "admission", "emergency", "facility", "facility_id", "severity", "mortality", "disposition", "payment", "medical_surgical", "procedure", "area")],
        money("charges").alias("charges"), money("costs").alias("costs"),
        F.when(los_text == "120 +", F.lit(120)).otherwise(los_text.cast("int")).alias("los"),
        (los_text == "120 +").alias("los_capped"),
    ).withColumn("valid_money", (F.col("charges") >= 0) & (F.col("costs") >= 0))


def rows(frame: DataFrame, group: str, value: str = "count", limit: int = 10) -> list[dict]:
    grouped = frame.where(F.length(F.col(group)) > 0).groupBy(group)
    result = grouped.count().withColumnRenamed("count", "value") if value == "count" else grouped.agg(F.avg(value).alias("value"))
    return [{"name": str(row[group]), "value": round(float(row["value"]), 2)} for row in result.orderBy(F.desc("value"), F.asc(group)).limit(limit).collect()]


def metric(key: str, label: str, value, unit: str) -> dict:
    return {"key": key, "label": label, "value": value, "unit": unit}


def section(key: str, title: str, items: list[dict], kind: str = "bar") -> dict:
    return {"key": key, "title": title, "type": kind, "items": items}


def summary_metrics(frame: DataFrame) -> list[dict]:
    row = frame.agg(
        F.count("*").alias("n"), F.avg("los").alias("los"), F.avg("charges").alias("charges"),
        F.avg("costs").alias("costs"), F.avg((F.col("emergency") == "Y").cast("double")).alias("emergency"),
        F.avg(F.col("medical_surgical").contains("Surgical").cast("double")).alias("surgical"),
        F.avg(F.col("severity").isin("Major", "Extreme").cast("double")).alias("severe"),
    ).first()
    return [
        metric("record_count", "住院出院记录", int(row.n), "条"),
        metric("avg_los", "平均住院时长", round(float(row.los or 0), 2), "天"),
        metric("avg_charges", "平均收费", round(float(row.charges or 0), 2), "美元"),
        metric("avg_costs", "平均成本", round(float(row.costs or 0), 2), "美元"),
        metric("emergency_rate", "急诊率", round(float(row.emergency or 0), 4), "%"),
        metric("surgical_rate", "外科率", round(float(row.surgical or 0), 4), "%"),
        metric("severe_rate", "重症率", round(float(row.severe or 0), 4), "%"),
    ]


def record(module: str, entity: str, title: str, description: str, metrics=None, sections=None, options=None, filters=None) -> dict:
    payload = {"title": title, "description": description, "metrics": metrics or [], "sections": sections or []}
    if options is not None: payload["options"] = options
    if filters is not None: payload["filters"] = filters
    return {"module_key": module, "entity_key": entity, "payload": payload}


def build_records(frame: DataFrame, raw_count: int) -> list[dict]:
    valid = frame.where(F.col("valid_money") & F.col("los").isNotNull())
    common = summary_metrics(valid)
    facility_count = valid.where(F.length("facility_id") > 0).select("facility_id").distinct().count()
    dashboard = record("dashboard", "overview", "医疗运营驾驶舱", "住院出院记录的群体运营总览。",
        [common[0], metric("facility_count", "医疗机构", facility_count, "家"), *common[1:]],
        [section("age", "年龄结构", rows(valid, "age")), section("payment", "主要支付方式", rows(valid, "payment")), section("disease_top10", "疾病病例量 TOP10", rows(valid, "diagnosis")), section("hospital_top10", "医院病例量 TOP10", rows(valid, "facility")), section("severity", "病情严重程度", rows(valid, "severity"))])
    records = [dashboard]

    facilities = valid.where(F.length("facility_id") > 0).select("facility_id", "facility").dropDuplicates(["facility_id"])
    facility_options = [{"value": row.facility_id, "label": row.facility or row.facility_id} for row in facilities.orderBy("facility_id").limit(500).collect()]
    records.append(record("hospitals", "index", "医院运营分析", "医院排行与双院对比。", [metric("facility_count", "可分析医疗机构", facility_count, "家")], [section("ranking", "医院病例量排行", rows(valid, "facility"))], {"facilities": facility_options}))
    for option in facility_options:
        subset = valid.where(F.col("facility_id") == option["value"])
        records.append(record("hospitals", f"profile:{option['value']}", option["label"], "医疗机构运营画像。", summary_metrics(subset), [section("diseases", "主要疾病 TOP5", rows(subset, "diagnosis", limit=5)), section("medical_surgical", "内外科结构", rows(subset, "medical_surgical"))]))

    diagnoses = valid.where(F.length("diagnosis_code") > 0).select("diagnosis_code", "diagnosis").dropDuplicates(["diagnosis_code"])
    diagnosis_options = [{"value": row.diagnosis_code, "label": row.diagnosis or row.diagnosis_code} for row in diagnoses.orderBy("diagnosis_code").limit(1000).collect()]
    records.append(record("diseases", "index", "疾病画像分析", "按主诊断类别观察群体画像。", [metric("diagnosis_count", "有效诊断类别", len(diagnosis_options), "类")], [section("top10", "疾病病例量 TOP10", rows(valid, "diagnosis"))], {"diagnoses": diagnosis_options}))
    for option in diagnosis_options:
        subset = valid.where(F.col("diagnosis_code") == option["value"])
        records.append(record("diseases", f"profile:{option['value']}", option["label"], "该诊断类别的住院出院记录群体画像。", summary_metrics(subset), [section("age", "年龄结构", rows(subset, "age")), section("gender", "性别结构", rows(subset, "gender")), section("severity", "严重程度", rows(subset, "severity")), section("mortality", "死亡风险", rows(subset, "mortality")), section("procedures", "常见操作", rows(subset, "procedure", limit=5)), section("hospitals", "主要医院", rows(subset, "facility", limit=5))]))

    option_values = lambda name: [row[name] for row in valid.where(F.length(name) > 0).select(name).distinct().orderBy(name).collect()]
    records.append(record("cohorts", "age=*|gender=*|admission=*", "住院记录群体分析", "有限白名单群体筛选；记录不按患者去重。", common, [section("diseases", "主要疾病", rows(valid, "diagnosis")), section("severity", "严重程度", rows(valid, "severity")), section("age", "年龄结构", rows(valid, "age"))], {"age_group": option_values("age"), "gender": option_values("gender"), "admission_type": option_values("admission")}, {}))

    q = valid.agg(*[F.percentile_approx("charges", p, 10000).alias(f"p{int(p*100)}") for p in (.25, .5, .75, .9)], F.avg("charges").alias("avg_charges"), F.avg("costs").alias("avg_costs"), F.avg(F.col("charges") - F.col("costs")).alias("gap"), F.avg(F.col("charges") / F.when(F.col("los") > 0, F.col("los"))).alias("daily_charges"), F.avg(F.col("costs") / F.when(F.col("los") > 0, F.col("los"))).alias("daily_costs")).first()
    cost_metrics = [metric("avg_charges", "平均收费", round(float(q.avg_charges),2), "美元"), metric("median_charges", "收费中位数", round(float(q.p50),2), "美元"), metric("p90_charges", "收费P90", round(float(q.p90),2), "美元"), metric("avg_costs", "平均成本", round(float(q.avg_costs),2), "美元"), metric("charge_cost_gap", "平均收费成本差", round(float(q.gap),2), "美元"), metric("daily_charges", "平均单日收费", round(float(q.daily_charges),2), "美元/天"), metric("daily_costs", "平均单日成本", round(float(q.daily_costs),2), "美元/天")]
    records.append(record("costs", "diagnosis=*|facility=*|severity=*", "医疗费用与成本分析", "分位数使用 percentile_approx(accuracy=10000)。", cost_metrics, [section("quantiles", "收费分位数", [{"name": name, "value": round(float(getattr(q, name.lower())),2)} for name in ("P25","P50","P75","P90")]), section("severity", "不同严重程度平均收费", rows(valid, "severity", "charges"))], {"severity": option_values("severity")}, {}))
    high_risk = valid.where(F.col("severity").isin("Major", "Extreme"))
    records.append(record("risks", "age=*|diagnosis=*", "病情严重程度与风险分析", "群体统计，不构成诊断、治疗或因果判断。", summary_metrics(high_risk), [section("severity", "严重程度分布", rows(valid, "severity")), section("mortality", "死亡风险分布", rows(valid, "mortality")), section("disposition", "高风险记录离院去向", rows(high_risk, "disposition")), section("age", "高风险年龄结构", rows(high_risk, "age")), section("diseases", "高风险疾病", rows(high_risk, "diagnosis"))], {"age_group": option_values("age")}, {}))
    records.append(record("payments", "payment=*|age=*", "支付方式分析", "核心支付维度为 Payment Typology 1。", common, [section("payment", "主支付方式结构", rows(valid, "payment")), section("charges", "不同支付方式平均收费", rows(valid, "payment", "charges")), section("age", "年龄结构", rows(valid, "age")), section("diseases", "主要疾病", rows(valid, "diagnosis"))], {"payment_type": option_values("payment"), "age_group": option_values("age")}, {}))
    invalid_money = frame.where(~F.coalesce(F.col("valid_money"), F.lit(False))).count()
    records.append(record("data_quality", "summary", "数据质量与任务管理", "只读展示当前批次与管道检查。", [metric("raw_rows", "原始记录", raw_count, "条"), metric("valid_rows", "有效记录", valid.count(), "条"), metric("money_parse_or_negative", "费用解析/负值异常", invalid_money, "条"), metric("diagnosis_missing", "诊断缺失", frame.where(F.col("diagnosis").isNull() | (F.length("diagnosis") == 0)).count(), "条"), metric("los_capped", "住院时长120+截断", frame.where("los_capped").count(), "条")], [section("storage", "存储与服务检查", [{"name": "HDFS", "value": "CHECK_REQUIRED"}, {"name": "Hive", "value": "CHECK_REQUIRED"}, {"name": "MySQL", "value": "NOT_PUBLISHED"}, {"name": "PySpark任务", "value": "PASS"}], "status")]))
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    generated_at = args.generated_at or datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    digest = fingerprint(args.input)
    spark = SparkSession.builder.master("local[*]").appName("yishuyunce-full-analytics").config("spark.ui.enabled", "false").getOrCreate()
    try:
        raw = spark.read.option("header", "true").option("inferSchema", "false").option("mode", "PERMISSIVE").csv(str(args.input.resolve()))
        cleaned = clean_frame(raw).persist(StorageLevel.MEMORY_AND_DISK)
        # This first materialization both establishes the raw row count and
        # fills the shared clean-frame cache. No earlier action may scan raw.
        raw_count = cleaned.count()
        document = {"data_version": f"sparcs_sha256_{digest}", "generated_at": generated_at, "input": {"file_name": args.input.name, "sha256": digest, "raw_rows": raw_count}, "records": build_records(cleaned, raw_count)}
        cleaned.unpersist()
    finally:
        spark.stop()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "records": len(document["records"]), "data_version": document["data_version"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
