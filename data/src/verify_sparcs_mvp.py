"""用独立的 CSV 计数逻辑核对 SPARCS MVP 样本和侦察脚本结果。

本脚本不导入 inspect_sparcs_mvp.py 的实现，避免用同一套逻辑重复证明自己。
它对诊断字段重新读取、清洗、计数和排序，再调用侦察脚本比较两套结果。
完整原始 CSV 只通过命令行传入，不写入仓库。
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE = REPO_ROOT / "data" / "fixtures" / "sparcs_mvp_sample.csv"
DEFAULT_EXPECTED = REPO_ROOT / "data" / "fixtures" / "sparcs_mvp_expected_top10.json"
DEFAULT_INSPECTOR = REPO_ROOT / "data" / "src" / "inspect_sparcs_mvp.py"
DIAGNOSIS_FIELD = "CCSR Diagnosis Description"


def independently_summarize(csv_path: Path, top_n: int = 10) -> dict[str, Any]:
    """只使用标准库独立计算记录数、缺失数和 TOP10。"""

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV 没有表头: {csv_path}") from exc

        try:
            diagnosis_index = header.index(DIAGNOSIS_FIELD)
        except ValueError as exc:
            raise ValueError(f"找不到诊断字段: {DIAGNOSIS_FIELD}") from exc

        rows = 0
        malformed_rows = 0
        counts: Counter[str] = Counter()
        for row in reader:
            rows += 1
            if len(row) != len(header):
                malformed_rows += 1
                continue
            diagnosis = row[diagnosis_index].strip()
            if diagnosis:
                counts[diagnosis] += 1

    top = [
        {"name": name, "case_count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
            :top_n
        ]
    ]
    return {
        "rows": rows,
        "malformed_rows": malformed_rows,
        "diagnosis_nonempty_rows": sum(counts.values()),
        "diagnosis_nonempty_distinct": len(counts),
        "top10": top,
    }


def run_inspector(inspector: Path, csv_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(inspector), str(csv_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def assert_equal(scope: str, name: str, expected: Any, actual: Any) -> None:
    if expected != actual:
        raise AssertionError(
            f"{scope} {name} 不一致: expected={expected!r}, actual={actual!r}"
        )


def verify_one(
    scope: str,
    csv_path: Path,
    inspector: Path,
    expected: dict[str, Any] | None,
) -> dict[str, Any]:
    independent = independently_summarize(csv_path)
    inspected = run_inspector(inspector, csv_path)

    for name in (
        "rows",
        "malformed_rows",
        "diagnosis_nonempty_distinct",
    ):
        assert_equal(scope, name, independent[name], inspected[name])
    assert_equal(scope, "top10", independent["top10"], inspected["diagnosis_top"])

    if expected is not None:
        for name in (
            "rows",
            "malformed_rows",
            "diagnosis_nonempty_rows",
            "diagnosis_nonempty_distinct",
            "top10",
        ):
            assert_equal(scope, name, expected[name], independent[name])

    return {
        "input": csv_path.name,
        "rows": independent["rows"],
        "malformed_rows": independent["malformed_rows"],
        "diagnosis_nonempty_rows": independent["diagnosis_nonempty_rows"],
        "diagnosis_nonempty_distinct": independent["diagnosis_nonempty_distinct"],
        "top10": independent["top10"],
    }


def check_required_values(csv_path: Path, required_values: dict[str, list[str]]) -> None:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        values = {name: set() for name in required_values}
        for row in reader:
            for name in values:
                values[name].add((row.get(name) or "").strip())
    for name, expected_values in required_values.items():
        for value in expected_values:
            if value not in values[name]:
                raise AssertionError(f"sample 缺少预期特殊值: {name}={value!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument("--inspector", type=Path, default=DEFAULT_INSPECTOR)
    parser.add_argument(
        "--full-source",
        type=Path,
        help="可选的本地完整 SPARCS CSV；传入后同时核对全量基线",
    )
    args = parser.parse_args()

    expected_document = json.loads(args.expected.read_text(encoding="utf-8"))
    sample_expected = expected_document["sample"]
    check_required_values(args.sample, sample_expected["required_values"])
    checks = [verify_one("sample", args.sample, args.inspector, sample_expected)]

    if args.full_source:
        checks.append(
            verify_one(
                "full_scan",
                args.full_source,
                args.inspector,
                expected_document["full_scan"],
            )
        )

    print(json.dumps({"status": "PASS", "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
