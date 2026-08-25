"""独立核对 M1 服务结果契约与固定样例。

本脚本只使用 Python 标准库，重新从固定样例计算 TOP10，再映射成
``disease_case_count_top10_result`` 的当前批次形状。它不连接 MySQL，
用于在服务结果发布前检查字段、类型、单位、版本、排名和排序是否完整。
正式统计口径仍以 docs/02-metrics-and-data-contract.md 为准。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.disease_rules import is_non_disease_diagnosis


DEFAULT_SAMPLE = REPO_ROOT / "data" / "fixtures" / "sparcs_mvp_sample.csv"
DEFAULT_EXPECTED = REPO_ROOT / "data" / "fixtures" / "sparcs_mvp_expected_top10.json"
DIAGNOSIS_FIELD = "CCSR Diagnosis Description"
YEAR_FIELD = "Discharge Year"
UNIT = "discharge_records"


def fail(message: str) -> None:
    raise AssertionError(message)


def assert_equal(name: str, expected: Any, actual: Any) -> None:
    if expected != actual:
        fail(f"{name} 不一致: expected={expected!r}, actual={actual!r}")


def summarize_sample(csv_path: Path) -> list[dict[str, Any]]:
    """从样例重新计算名称和病例量，不读取已有 TOP10 结果。"""

    counts: Counter[str] = Counter()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("CSV 没有表头") from exc

        try:
            diagnosis_index = header.index(DIAGNOSIS_FIELD)
            year_index = header.index(YEAR_FIELD)
        except ValueError as exc:
            raise ValueError("固定样例缺少 TOP10 所需字段") from exc

        for row in reader:
            if len(row) != len(header):
                fail("固定样例存在无法按表头解析的行")
            if row[year_index].strip() != "2021":
                continue
            diagnosis_name = row[diagnosis_index].strip()
            if diagnosis_name and not is_non_disease_diagnosis(diagnosis_name):
                counts[diagnosis_name] += 1

    return [
        {"name": name, "case_count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]


def validate_service_rows(service: dict[str, Any], expected_top10: list[dict[str, Any]]) -> None:
    required = {"data_version", "generated_at", "unit", "rows"}
    if set(service) != required:
        fail(f"service_result 顶层字段必须为 {sorted(required)}，实际为 {sorted(service)}")

    data_version = service["data_version"]
    generated_at = service["generated_at"]
    unit = service["unit"]
    rows = service["rows"]

    if not isinstance(data_version, str) or not data_version:
        fail("data_version 必须是非空字符串")
    if not isinstance(generated_at, str) or not generated_at:
        fail("generated_at 必须是非空字符串")
    if unit != UNIT:
        fail(f"unit 必须固定为 {UNIT!r}")
    if not isinstance(rows, list) or not 0 < len(rows) <= 10:
        fail("service_result.rows 必须包含 1—10 行")

    expected_rows = [
        {
            "rank": rank,
            "diagnosis_name": item["name"],
            "case_count": item["case_count"],
            "unit": UNIT,
            "data_version": data_version,
            "generated_at": generated_at,
        }
        for rank, item in enumerate(expected_top10, start=1)
    ]
    assert_equal("service_result.rows", expected_rows, rows)

    ranks = [row["rank"] for row in rows]
    if ranks != list(range(1, len(rows) + 1)):
        fail(f"rank 必须从 1 连续递增，实际为 {ranks!r}")
    if len({row["diagnosis_name"] for row in rows}) != len(rows):
        fail("同一 data_version 内 diagnosis_name 不能重复")
    if len({row["data_version"] for row in rows}) != 1:
        fail("同一服务结果批次不能混入多个 data_version")
    if len({row["generated_at"] for row in rows}) != 1:
        fail("同一服务结果批次必须使用同一个 generated_at")
    if rows != sorted(rows, key=lambda row: (-row["case_count"], row["diagnosis_name"])):
        fail("service_result.rows 未按病例量降序、名称升序排列")

    for row in rows:
        if not isinstance(row["rank"], int) or isinstance(row["rank"], bool):
            fail("rank 必须是整数")
        if not isinstance(row["diagnosis_name"], str) or not row["diagnosis_name"]:
            fail("diagnosis_name 必须是非空字符串")
        if is_non_disease_diagnosis(row["diagnosis_name"]):
            fail("diagnosis_name 不能是非疾病标签")
        if (
            not isinstance(row["case_count"], int)
            or isinstance(row["case_count"], bool)
            or row["case_count"] <= 0
        ):
            fail("case_count 必须是正整数")
        if row["unit"] != UNIT or row["data_version"] != data_version:
            fail("服务结果行的 unit/data_version 与批次元数据不一致")
        if row["generated_at"] != generated_at:
            fail("服务结果行的 generated_at 与批次元数据不一致")


def validate_generated_service_result(
    service: dict[str, Any], expected_top10: list[dict[str, Any]]
) -> None:
    """Validate the small artifact emitted by the formal PySpark task."""

    required = {"metric", "unit", "data_version", "generated_at", "items"}
    if set(service) != required:
        fail(
            "generated service_result 顶层字段必须为 "
            f"{sorted(required)}，实际为 {sorted(service)}"
        )
    if service["metric"] != "disease_case_count_top10":
        fail("metric 不符合疾病病例量 TOP10 契约")
    if service["unit"] != UNIT:
        fail(f"unit 必须固定为 {UNIT!r}")
    if not isinstance(service["data_version"], str) or not service["data_version"]:
        fail("data_version 必须是非空字符串")
    if not isinstance(service["generated_at"], str) or not service["generated_at"].endswith("Z"):
        fail("generated_at 必须是 UTC ISO-8601 字符串")

    items = service["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        fail("generated service_result.items 必须包含 1—10 项")
    expected_items = [
        {
            "rank": rank,
            "diagnosis_name": item["name"],
            "case_count": item["case_count"],
        }
        for rank, item in enumerate(expected_top10, start=1)
    ]
    assert_equal("generated service_result.items", expected_items, items)

    ranks = [item.get("rank") for item in items]
    if ranks != list(range(1, len(items) + 1)):
        fail(f"rank 必须从 1 连续递增，实际为 {ranks!r}")
    if len({item.get("diagnosis_name") for item in items}) != len(items):
        fail("同一 data_version 内 diagnosis_name 不能重复")
    if items != sorted(items, key=lambda item: (-item["case_count"], item["diagnosis_name"])):
        fail("generated service_result.items 未按病例量降序、名称升序排列")

    for item in items:
        if not isinstance(item.get("rank"), int) or isinstance(item.get("rank"), bool):
            fail("rank 必须是整数")
        if not isinstance(item.get("diagnosis_name"), str) or not item["diagnosis_name"]:
            fail("diagnosis_name 必须是非空字符串")
        if is_non_disease_diagnosis(item["diagnosis_name"]):
            fail("diagnosis_name 不能是非疾病标签")
        if (
            not isinstance(item.get("case_count"), int)
            or isinstance(item.get("case_count"), bool)
            or item["case_count"] <= 0
        ):
            fail("case_count 必须是正整数")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument(
        "--result",
        type=Path,
        help="可选的 PySpark 服务结果工件；传入后核对 full_scan 的独立期望结果",
    )
    parser.add_argument(
        "--expected-scope",
        choices=("sample", "full_scan"),
        default="sample",
        help="--result 对应 expected JSON 中的核对范围",
    )
    args = parser.parse_args()

    expected_document = json.loads(args.expected.read_text(encoding="utf-8"))
    expected_top10 = expected_document["sample"]["top10"]
    actual_top10 = summarize_sample(args.sample)
    assert_equal("sample.top10", expected_top10, actual_top10)
    validate_service_rows(expected_document["service_result"], actual_top10)

    result_summary: dict[str, Any] = {}
    if args.result:
        result_document = json.loads(args.result.read_text(encoding="utf-8"))
        expected_scope = expected_document[args.expected_scope]
        validate_generated_service_result(
            result_document["service_result"], expected_scope["top10"]
        )
        result_summary = {
            "result": args.result.name,
            "result_data_version": result_document["service_result"]["data_version"],
            "result_rows": len(result_document["service_result"]["items"]),
        }

    print(
        json.dumps(
            {
                "status": "PASS",
                "input": args.sample.name,
                "data_version": expected_document["service_result"]["data_version"],
                "rows": len(actual_top10),
                "unit": UNIT,
                **result_summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
