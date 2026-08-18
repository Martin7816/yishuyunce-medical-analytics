"""Train and export the leakage-safe high-cost Logistic Regression model."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from pyspark.ml import Pipeline
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import OneHotEncoder, StringIndexer, VectorAssembler
from pyspark.sql import SparkSession, functions as F

from run_full_analytics_pyspark import FIELDS, clean_frame, fingerprint


FEATURES = ["age", "gender", "race", "ethnicity", "area", "facility_id", "admission", "emergency"]
PUBLIC_NAMES = {
    "age": "age_group", "gender": "gender", "race": "race", "ethnicity": "ethnicity",
    "area": "hospital_service_area", "facility_id": "facility_id",
    "admission": "admission_type", "emergency": "emergency_indicator",
}
SEED = 20260818


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, help="把模型指标合并进待发布的统一快照")
    args = parser.parse_args()

    spark = SparkSession.builder.master("local[*]").appName("yishuyunce-high-cost-model").config("spark.ui.enabled", "false").getOrCreate()
    try:
        raw = spark.read.option("header", "true").option("inferSchema", "false").option("mode", "PERMISSIVE").csv(str(args.input.resolve()))
        frame = clean_frame(raw).where(F.col("valid_money") & F.col("charges").isNotNull())
        train_base, test_base = frame.randomSplit([0.8, 0.2], seed=SEED)
        threshold = float(train_base.agg(F.percentile_approx("charges", 0.75, 10000).alias("q")).first().q)
        train = train_base.withColumn("label", (F.col("charges") >= threshold).cast("double"))
        test = test_base.withColumn("label", (F.col("charges") >= threshold).cast("double"))

        indexers = [StringIndexer(inputCol=name, outputCol=f"{name}_idx", handleInvalid="keep", stringOrderType="alphabetAsc") for name in FEATURES]
        encoder = OneHotEncoder(inputCols=[f"{name}_idx" for name in FEATURES], outputCols=[f"{name}_vec" for name in FEATURES], dropLast=False, handleInvalid="keep")
        assembler = VectorAssembler(inputCols=[f"{name}_vec" for name in FEATURES], outputCol="features")
        classifier = LogisticRegression(featuresCol="features", labelCol="label", maxIter=100, regParam=0.05, elasticNetParam=0.0)
        model = Pipeline(stages=[*indexers, encoder, assembler, classifier]).fit(train)
        predictions = model.transform(test).cache()
        counts = predictions.agg(
            F.count("*").alias("n"),
            F.sum(((F.col("prediction") == 1) & (F.col("label") == 1)).cast("long")).alias("tp"),
            F.sum(((F.col("prediction") == 1) & (F.col("label") == 0)).cast("long")).alias("fp"),
            F.sum(((F.col("prediction") == 0) & (F.col("label") == 1)).cast("long")).alias("fn"),
            F.sum(((F.col("prediction") == 0) & (F.col("label") == 0)).cast("long")).alias("tn"),
        ).first()
        tp, fp, fn, tn = (int(counts.tp or 0), int(counts.fp or 0), int(counts.fn or 0), int(counts.tn or 0))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        accuracy = (tp + tn) / counts.n if counts.n else 0.0
        auc = BinaryClassificationEvaluator(labelCol="label", rawPredictionCol="rawPrediction", metricName="areaUnderROC").evaluate(predictions)

        lr_model = model.stages[-1]
        coefficients = list(lr_model.coefficients)
        feature_weights, offset = {}, 0
        category_sizes = list(model.stages[len(FEATURES)].categorySizes)
        for name, indexer_model, category_size in zip(FEATURES, model.stages[:len(FEATURES)], category_sizes):
            labels = list(indexer_model.labels)
            # With OneHotEncoder(handleInvalid=keep, dropLast=False), Spark
            # appends one encoded invalid bucket beyond categorySizes.
            width = category_size + 1
            weights = {label: float(coefficients[offset + index]) for index, label in enumerate(labels)}
            # StringIndexer(handleInvalid=keep) reserves the first unseen/null
            # category after its learned labels. OneHotEncoder may reserve an
            # additional invalid bucket; categorySizes is the authoritative
            # encoded width, so offsets must not be inferred from labels alone.
            weights["OTHER"] = float(coefficients[offset + min(len(labels), width - 1)])
            feature_weights[PUBLIC_NAMES[name]] = weights
            offset += width
        if offset != len(coefficients):
            raise ValueError(
                f"导出系数与独热编码宽度不一致: category_sizes={category_sizes}, "
                f"sum={offset}, coefficients={len(coefficients)}"
            )

        digest = fingerprint(args.input)
        data_version = f"sparcs_sha256_{digest}"
        model_version = f"high_cost_lr_seed_{SEED}_{digest[:12]}"
        artifact = {
            "artifact_type": "pyspark_logistic_regression", "model_version": model_version,
            "data_version": data_version, "threshold_amount": threshold,
            "classification_threshold": 0.5, "intercept": float(lr_model.intercept),
            "feature_weights": feature_weights, "seed": SEED,
            "excluded_leakage_fields": ["total_charges", "total_costs", "length_of_stay", "discharge_disposition", "operating_room_procedure", "post_discharge_fields"],
        }
        metrics = {
            "model_version": model_version, "data_version": data_version, "generated_at": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "threshold_amount": threshold, "train_rows": train.count(), "test_rows": int(counts.n),
            "accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1, "auc": auc,
            "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp}, "seed": SEED,
        }
        predictions.unpersist()
    finally:
        spark.stop()

    for path, document in ((args.artifact, artifact), (args.metrics, metrics)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.snapshot:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if snapshot.get("data_version") != data_version:
            raise ValueError("模型与分析快照的 data_version 不一致")
        snapshot["records"] = [
            row for row in snapshot["records"]
            if not (row.get("module_key") == "high_cost_model" and row.get("entity_key") == "metrics")
        ]
        snapshot["records"].append({
            "module_key": "high_cost_model", "entity_key": "metrics",
            "payload": {
                "title": "高费用病例分类模型", "description": "仅使用入院时可得类别字段的运营分类模型。",
                "options": {"model_version": model_version, "threshold_amount": threshold, "feature_names": list(PUBLIC_NAMES.values())},
                "metrics": [
                    {"key": "train_rows", "label": "训练集", "value": metrics["train_rows"], "unit": "条"},
                    {"key": "test_rows", "label": "测试集", "value": metrics["test_rows"], "unit": "条"},
                    *[{"key": key, "label": key.upper() if key != "accuracy" else "Accuracy", "value": metrics[key], "unit": "%"} for key in ("accuracy", "precision", "recall", "f1", "auc")],
                ],
                "sections": [{"key": "confusion", "title": "混淆矩阵", "type": "table", "items": [{"name": key.upper(), "value": value} for key, value in metrics["confusion_matrix"].items()]}],
            },
        })
        args.snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "model_version": model_version, "data_version": data_version}, ensure_ascii=False))


if __name__ == "__main__":
    main()
