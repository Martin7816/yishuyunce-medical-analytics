"""Train and export the leakage-safe high-cost Logistic Regression model.

The trainer deliberately keeps the model boundary narrow: the label is derived
from the training split only, while the pipeline receives only admission-time
categorical fields.  ``--repetitions 2`` is the reproducibility check used by
the Issue #75 acceptance run; the first run is the published artifact.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pyspark.ml import Pipeline
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import OneHotEncoder, StringIndexer, VectorAssembler
from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.storagelevel import StorageLevel


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analytics_metadata import build_data_version  # noqa: E402
from run_full_analytics_pyspark import clean_frame, fingerprint  # noqa: E402
from shared.analytics_snapshot_contract import (  # noqa: E402
    validate_snapshot_document,
)


FEATURES = [
    "age",
    "gender",
    "race",
    "ethnicity",
    "area",
    "facility_id",
    "admission",
    "emergency",
]
PUBLIC_NAMES = {
    "age": "age_group",
    "gender": "gender",
    "race": "race",
    "ethnicity": "ethnicity",
    "area": "hospital_service_area",
    "facility_id": "facility_id",
    "admission": "admission_type",
    "emergency": "emergency_indicator",
}
SEED = 20260818
# Spark's distributed evaluator can vary by a few ulps across consecutive
# actions; this tolerance is still far below a meaningful metric change.
REPRO_TOLERANCE = 1e-6

# These are the canonical names of fields that are deliberately not passed to
# the pipeline.  The public aliases below are retained in the artifact because
# they are the wording used by the product contract and API review.
EXCLUDED_INPUT_COLUMNS = [
    "year",
    "diagnosis",
    "diagnosis_code",
    "facility",
    "severity",
    "mortality",
    "disposition",
    "payment",
    "medical_surgical",
    "procedure",
    "charges",
    "costs",
    "los",
    "los_capped",
    "in_scope",
    "valid_money",
]
PUBLIC_LEAKAGE_FIELDS = [
    "total_charges",
    "total_costs",
    "length_of_stay",
    "discharge_disposition",
    "operating_room_procedure",
    "post_discharge_fields",
]

REPRO_METRIC_FIELDS = (
    "threshold_amount",
    "train_rows",
    "test_rows",
    "accuracy",
    "precision",
    "recall",
    "f1",
    "auc",
)


def _finite_number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    number = float(value)
    return number if math.isfinite(number) else default


def _classification_metrics(counts: dict[str, Any], auc: float) -> dict[str, Any]:
    """Calculate stable binary metrics from the test-set confusion counts."""

    test_rows = int(counts.get("n") or 0)
    tp = int(counts.get("tp") or 0)
    fp = int(counts.get("fp") or 0)
    fn = int(counts.get("fn") or 0)
    tn = int(counts.get("tn") or 0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / test_rows if test_rows else 0.0
    return {
        "test_rows": test_rows,
        "accuracy": _finite_number(accuracy),
        "precision": _finite_number(precision),
        "recall": _finite_number(recall),
        "f1": _finite_number(f1),
        "auc": _finite_number(auc),
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def _build_pipeline() -> Pipeline:
    indexers = [
        StringIndexer(
            inputCol=name,
            outputCol=f"{name}_idx",
            handleInvalid="keep",
            stringOrderType="alphabetAsc",
        )
        for name in FEATURES
    ]
    encoder = OneHotEncoder(
        inputCols=[f"{name}_idx" for name in FEATURES],
        outputCols=[f"{name}_vec" for name in FEATURES],
        dropLast=False,
        handleInvalid="keep",
    )
    assembler = VectorAssembler(
        inputCols=[f"{name}_vec" for name in FEATURES],
        outputCol="features",
    )
    classifier = LogisticRegression(
        featuresCol="features",
        labelCol="label",
        maxIter=100,
        regParam=0.05,
        elasticNetParam=0.0,
    )
    return Pipeline(stages=[*indexers, encoder, assembler, classifier])


def _extract_feature_metadata(model: Any) -> tuple[dict[str, dict[str, Any]], int]:
    """Export category weights and verify the encoder/model vector boundary."""

    encoder_model = model.stages[len(FEATURES)]
    category_sizes = [int(size) for size in encoder_model.categorySizes]
    if len(category_sizes) != len(FEATURES):
        raise ValueError(
            f"独热编码类别数与特征数不一致: category_sizes={category_sizes}, "
            f"features={len(FEATURES)}"
        )

    coefficients = list(model.stages[-1].coefficients)
    expected_width = sum(category_size + 1 for category_size in category_sizes)
    if expected_width != len(coefficients):
        raise ValueError(
            "导出系数与独热编码宽度不一致: "
            f"category_sizes={category_sizes}, expected_width={expected_width}, "
            f"coefficients={len(coefficients)}"
        )

    metadata: dict[str, dict[str, Any]] = {}
    offset = 0
    for index, (name, category_size) in enumerate(zip(FEATURES, category_sizes)):
        indexer_model = model.stages[index]
        labels = [str(label) for label in indexer_model.labels]
        # The encoder sees the StringIndexer invalid bucket as one input
        # category, then keeps one more output slot for its own invalid-index
        # handling.  Therefore categorySizes is labels + 1 and the coefficient
        # width is categorySizes + 1 for this fixed dropLast=False pipeline.
        if len(labels) + 1 != category_size:
            raise ValueError(
                f"StringIndexer标签数与categorySizes不一致: feature={name}, "
                f"labels={len(labels)}, encoder_category_size={category_size}"
            )

        width = category_size + 1
        weights = {
            label: float(coefficients[offset + label_index])
            for label_index, label in enumerate(labels)
        }
        # StringIndexer(handleInvalid=keep) maps an unseen/null value to the
        # final index; with dropLast=False the matching encoder column is the
        # additional slot after the learned categories.
        weights["OTHER"] = float(coefficients[offset + len(labels)])
        public_name = PUBLIC_NAMES[name]
        metadata[public_name] = {
            "input_column": name,
            "categories": labels,
            "learned_category_size": len(labels),
            "encoder_category_size": category_size,
            "encoded_width": width,
            "unknown_bucket": "OTHER",
            "unknown_index": len(labels),
            "encoder_invalid_index": category_size,
            "encoder_invalid_weight": float(coefficients[offset + category_size]),
            "weights": weights,
        }
        offset += width

    if offset != len(coefficients):
        raise ValueError(
            f"导出系数偏移未闭合: offset={offset}, coefficients={len(coefficients)}"
        )
    return metadata, len(coefficients)


def _run_once(
    train: DataFrame,
    test: DataFrame,
    *,
    threshold: float,
    train_rows: int,
    data_version: str,
    model_version: str,
    generated_at: str,
) -> dict[str, dict[str, Any]]:
    train_labeled = train.withColumn(
        "label",
        (F.col("charges") >= F.lit(threshold)).cast("double"),
    )
    test_labeled = test.withColumn(
        "label",
        (F.col("charges") >= F.lit(threshold)).cast("double"),
    )

    model = _build_pipeline().fit(train_labeled)
    predictions = model.transform(test_labeled).cache()
    try:
        counts_row = predictions.agg(
            F.count("*").alias("n"),
            F.min("label").alias("label_min"),
            F.max("label").alias("label_max"),
            F.sum(
                ((F.col("prediction") == 1) & (F.col("label") == 1)).cast("long")
            ).alias("tp"),
            F.sum(
                ((F.col("prediction") == 1) & (F.col("label") == 0)).cast("long")
            ).alias("fp"),
            F.sum(
                ((F.col("prediction") == 0) & (F.col("label") == 1)).cast("long")
            ).alias("fn"),
            F.sum(
                ((F.col("prediction") == 0) & (F.col("label") == 0)).cast("long")
            ).alias("tn"),
        ).first()
        counts = counts_row.asDict()

        auc = 0.0
        if (
            counts["n"]
            and counts["label_min"] is not None
            and counts["label_min"] != counts["label_max"]
        ):
            auc = BinaryClassificationEvaluator(
                labelCol="label",
                rawPredictionCol="rawPrediction",
                metricName="areaUnderROC",
                # Zero disables the default 1000-bin downsampling and keeps
                # the evaluator on the exact score ordering for reproducible
                # comparisons on the full test set.
                numBins=0,
            ).evaluate(predictions)
        evaluated = _classification_metrics(counts, auc)
        feature_metadata, coefficient_count = _extract_feature_metadata(model)
        metrics = {
            "model_version": model_version,
            "data_version": data_version,
            "generated_at": generated_at,
            "threshold_amount": threshold,
            "train_rows": train_rows,
            "test_rows": evaluated["test_rows"],
            "accuracy": evaluated["accuracy"],
            "precision": evaluated["precision"],
            "recall": evaluated["recall"],
            "f1": evaluated["f1"],
            "auc": evaluated["auc"],
            "confusion_matrix": evaluated["confusion_matrix"],
            "feature_names": list(PUBLIC_NAMES.values()),
            "excluded_input_columns": list(EXCLUDED_INPUT_COLUMNS),
            "seed": SEED,
        }
        artifact = {
            "artifact_type": "pyspark_logistic_regression",
            "model_version": model_version,
            "data_version": data_version,
            "threshold_amount": threshold,
            "classification_threshold": 0.5,
            "intercept": float(model.stages[-1].intercept),
            "feature_names": list(PUBLIC_NAMES.values()),
            "source_feature_columns": list(FEATURES),
            "feature_weights": {
                name: details["weights"]
                for name, details in feature_metadata.items()
            },
            "feature_metadata": feature_metadata,
            "coefficient_count": coefficient_count,
            "seed": SEED,
            "excluded_input_columns": list(EXCLUDED_INPUT_COLUMNS),
            "excluded_leakage_fields": list(PUBLIC_LEAKAGE_FIELDS),
        }
        return {"artifact": artifact, "metrics": metrics}
    finally:
        predictions.unpersist()


def _numeric_equal(left: Any, right: Any, tolerance: float = REPRO_TOLERANCE) -> bool:
    if isinstance(left, int) and isinstance(right, int):
        return left == right
    return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)


def _flatten_coefficients(artifact: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for feature_name in artifact["feature_names"]:
        values.extend(
            float(value)
            for value in artifact["feature_weights"][feature_name].values()
        )
        values.append(
            float(artifact["feature_metadata"][feature_name]["encoder_invalid_weight"])
        )
    return values


def _feature_schema(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return categorical/width metadata without numerical coefficient values."""

    ignored = {"weights", "encoder_invalid_weight"}
    return {
        feature_name: {
            key: value
            for key, value in details.items()
            if key not in ignored
        }
        for feature_name, details in artifact["feature_metadata"].items()
    }


def compare_repetitions(results: list[dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Compare repeated runs while ignoring the intentionally generated timestamp."""

    run_summaries = [
        {
            "run": index + 1,
            "model_version": result["metrics"]["model_version"],
            "data_version": result["metrics"]["data_version"],
            "threshold_amount": result["metrics"]["threshold_amount"],
            "train_rows": result["metrics"]["train_rows"],
            "test_rows": result["metrics"]["test_rows"],
            "accuracy": result["metrics"]["accuracy"],
            "precision": result["metrics"]["precision"],
            "recall": result["metrics"]["recall"],
            "f1": result["metrics"]["f1"],
            "auc": result["metrics"]["auc"],
            "confusion_matrix": result["metrics"]["confusion_matrix"],
            "coefficient_count": result["artifact"]["coefficient_count"],
        }
        for index, result in enumerate(results)
    ]
    if len(results) < 2:
        return {
            "status": "NOT_RUN",
            "runs": len(results),
            "checks": {},
            "run_summaries": run_summaries,
        }

    first_metrics = results[0]["metrics"]
    first_artifact = results[0]["artifact"]
    checks: dict[str, bool] = {
        **{field: True for field in REPRO_METRIC_FIELDS},
        "confusion_matrix": True,
        "data_version": True,
        "model_version": True,
        "feature_metadata": True,
        "coefficients": True,
    }
    first_coefficients = _flatten_coefficients(first_artifact)
    max_delta = 0.0
    for result in results[1:]:
        current_metrics = result["metrics"]
        current_artifact = result["artifact"]
        for field in REPRO_METRIC_FIELDS:
            checks[field] &= _numeric_equal(
                first_metrics[field], current_metrics[field]
            )
        checks["confusion_matrix"] &= (
            first_metrics["confusion_matrix"] == current_metrics["confusion_matrix"]
        )
        checks["data_version"] &= (
            first_metrics["data_version"] == current_metrics["data_version"]
        )
        checks["model_version"] &= (
            first_metrics["model_version"] == current_metrics["model_version"]
        )
        checks["feature_metadata"] &= _feature_schema(
            first_artifact
        ) == _feature_schema(current_artifact)

        current_coefficients = _flatten_coefficients(current_artifact)
        if len(first_coefficients) != len(current_coefficients):
            checks["coefficients"] = False
            continue
        max_delta = max(
            max_delta,
            max(
                (
                    abs(left - right)
                    for left, right in zip(first_coefficients, current_coefficients)
                ),
                default=0.0,
            ),
        )
    checks["coefficients"] &= max_delta <= REPRO_TOLERANCE

    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "runs": len(results),
        "tolerance": REPRO_TOLERANCE,
        "checks": checks,
        "coefficient_max_abs_delta": max_delta,
        "run_summaries": run_summaries,
    }


def _snapshot_payload(
    metrics: dict[str, Any], artifact: dict[str, Any]
) -> dict[str, Any]:
    metric_rows = [
        {
            "key": "train_rows",
            "label": "训练集",
            "value": metrics["train_rows"],
            "unit": "条",
        },
        {
            "key": "test_rows",
            "label": "测试集",
            "value": metrics["test_rows"],
            "unit": "条",
        },
        *[
            {
                "key": key,
                "label": "Accuracy" if key == "accuracy" else key.upper(),
                "value": metrics[key],
                "unit": "%",
            }
            for key in ("accuracy", "precision", "recall", "f1", "auc")
        ],
    ]
    confusion = metrics["confusion_matrix"]
    return {
        "title": "高费用病例分类模型",
        "description": "使用入院时可得类别字段预测高费用记录，仅供运营分析。",
        "options": {
            "model_version": artifact["model_version"],
            "data_version": artifact["data_version"],
            "threshold_amount": artifact["threshold_amount"],
            "classification_threshold": artifact["classification_threshold"],
            "feature_names": artifact["feature_names"],
            "artifact_type": artifact["artifact_type"],
        },
        "metrics": metric_rows,
        "sections": [
            {
                "key": "confusion",
                "title": "混淆矩阵",
                "type": "table",
                "items": [
                    {"name": key.upper(), "value": value}
                    for key, value in confusion.items()
                ],
            }
        ],
    }


def _merge_snapshot(
    snapshot_path: Path,
    *,
    data_version: str,
    metrics: dict[str, Any],
    artifact: dict[str, Any],
) -> None:
    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    validate_snapshot_document(document)
    if document.get("data_version") != data_version:
        raise ValueError(
            "模型与分析快照的 data_version 不一致: "
            f"model={data_version}, snapshot={document.get('data_version')}"
        )
    document["records"] = [
        row
        for row in document["records"]
        if not (
            row.get("module_key") == "high_cost_model"
            and row.get("entity_key") == "metrics"
        )
    ]
    document["records"].append(
        {
            "module_key": "high_cost_model",
            "entity_key": "metrics",
            "payload": _snapshot_payload(metrics, artifact),
        }
    )
    validate_snapshot_document(document)
    snapshot_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="把模型指标合并进待发布的统一快照",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="连续训练次数；验收复现使用 2，首轮结果写入 artifact/metrics",
    )
    parser.add_argument(
        "--reproducibility",
        type=Path,
        help="写入重复训练比较结果 JSON",
    )
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions 必须大于等于 1")
    input_path = args.input.resolve()
    if not input_path.is_file():
        parser.error(f"输入文件不存在: {input_path}")

    digest = fingerprint(input_path)
    data_version = build_data_version(input_path, digest)
    model_version = f"high_cost_lr_seed_{SEED}_{digest[:12]}"

    snapshot_generated_at = None
    if args.snapshot:
        snapshot_document = json.loads(args.snapshot.read_text(encoding="utf-8"))
        validate_snapshot_document(snapshot_document)
        snapshot_generated_at = snapshot_document["generated_at"]
    generated_at = snapshot_generated_at or datetime.now(UTC).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")

    spark = (
        SparkSession.builder.master("local[*]")
        .appName("yishuyunce-high-cost-model")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    frame = None
    train_base = None
    test_base = None
    try:
        raw = (
            spark.read.option("header", "true")
            .option("inferSchema", "false")
            .option("mode", "FAILFAST")
            .csv(str(input_path))
        )
        frame = clean_frame(raw).where(
            F.col("in_scope") & F.col("valid_money") & F.col("charges").isNotNull()
        ).persist(StorageLevel.MEMORY_AND_DISK)
        scoped_rows = frame.count()
        if scoped_rows == 0:
            raise ValueError("清洗后没有可用于训练的 2021 有效收费记录")

        train_base, test_base = frame.randomSplit([0.8, 0.2], seed=SEED)
        train_base = train_base.persist(StorageLevel.MEMORY_AND_DISK)
        test_base = test_base.persist(StorageLevel.MEMORY_AND_DISK)
        train_rows = train_base.count()
        test_rows = test_base.count()
        if train_rows == 0 or test_rows == 0:
            raise ValueError(
                f"随机切分后训练/测试集为空: train_rows={train_rows}, test_rows={test_rows}"
            )

        threshold_row = train_base.agg(
            F.percentile_approx("charges", 0.75, 10000).alias("q")
        ).first()
        threshold = threshold_row["q"] if threshold_row else None
        if threshold is None:
            raise ValueError("无法从训练集收费计算 P75 阈值")
        threshold = float(threshold)

        results = [
            _run_once(
                train_base,
                test_base,
                threshold=threshold,
                train_rows=train_rows,
                data_version=data_version,
                model_version=model_version,
                generated_at=generated_at,
            )
            for _ in range(args.repetitions)
        ]
        reproducibility = compare_repetitions(results)
        if reproducibility["status"] == "FAIL":
            raise ValueError(
                "重复训练未通过复现检查: "
                + json.dumps(reproducibility, ensure_ascii=False)
            )
        artifact = results[0]["artifact"]
        metrics = dict(results[0]["metrics"])
        metrics["scoped_rows"] = scoped_rows
        metrics["reproducibility"] = reproducibility
    finally:
        if test_base is not None:
            test_base.unpersist()
        if train_base is not None:
            train_base.unpersist()
        if frame is not None:
            frame.unpersist()
        spark.stop()

    _write_json(args.artifact, artifact)
    _write_json(args.metrics, metrics)
    if args.reproducibility:
        _write_json(args.reproducibility, reproducibility)
    if args.snapshot:
        _merge_snapshot(
            args.snapshot,
            data_version=data_version,
            metrics=metrics,
            artifact=artifact,
        )

    print(
        json.dumps(
            {
                "status": "PASS",
                "model_version": model_version,
                "data_version": data_version,
                "train_rows": metrics["train_rows"],
                "test_rows": metrics["test_rows"],
                "threshold_amount": metrics["threshold_amount"],
                "reproducibility": reproducibility,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
