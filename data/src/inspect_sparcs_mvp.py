"""核验 SPARCS CSV 的读取、字段和疾病病例量 TOP10 可行性。

这个脚本只做侦察，不会修改原始 CSV，也不会删除重复记录。默认输出适合写入
docs/01-data-and-feasibility.md 的 JSON 摘要；完整原始数据不要放进仓库。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


INTEGER = re.compile(r"^[+-]?\d+$")
DECIMAL = re.compile(r"^[+-]?(?:\d[\d,]*)(?:\.\d+)?$")
EXPECTED_NUMERIC = {
    "Discharge Year": {"integer"},
    "Length of Stay": {"integer"},
    "Zip Code - 3 digits": {"integer"},
    "Birth Weight": {"integer", "decimal"},
    "Total Charges": {"integer", "decimal"},
    "Total Costs": {"integer", "decimal"},
}


def clean(value: str) -> str:
    return value.strip()


def value_kind(value: str) -> str:
    value = clean(value)
    if not value:
        return "empty"
    if INTEGER.fullmatch(value):
        return "integer"
    if DECIMAL.fullmatch(value):
        return "decimal"
    return "text"


def summarize_kinds(kinds: Counter[str]) -> str:
    nonempty = sum(count for kind, count in kinds.items() if kind != "empty")
    if not nonempty:
        return "empty"
    numeric = kinds["integer"] + kinds["decimal"]
    if numeric == nonempty:
        return "integer" if kinds["decimal"] == 0 else "decimal"
    if kinds["text"] == nonempty:
        return "text"
    return "mixed"


def iter_rows(csv_path: Path) -> Iterable[list[str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.reader(handle)


def inspect(csv_path: Path, diagnosis_field: str, top_n: int) -> dict[str, object]:
    rows = iter_rows(csv_path)
    try:
        header = next(rows)
    except StopIteration as exc:
        raise ValueError("CSV 没有表头") from exc

    if len(header) != len(set(header)):
        raise ValueError("CSV 表头存在重复列名")
    if diagnosis_field not in header:
        raise ValueError(f"找不到诊断字段: {diagnosis_field}")

    diagnosis_index = header.index(diagnosis_field)
    missing = Counter()
    kinds = {name: Counter() for name in header}
    diagnosis_counts: Counter[str] = Counter()
    anomaly_values = {name: Counter() for name in EXPECTED_NUMERIC}
    sample_rows: list[list[str]] = []
    row_count = 0
    malformed_rows = 0

    for row in rows:
        row_count += 1
        if len(row) != len(header):
            malformed_rows += 1
            continue
        if len(sample_rows) < 5:
            sample_rows.append(row)
        for name, value in zip(header, row):
            stripped = clean(value)
            kind = value_kind(stripped)
            kinds[name][kind] += 1
            if not stripped:
                missing[name] += 1
            elif name in EXPECTED_NUMERIC and kind not in EXPECTED_NUMERIC[name]:
                anomaly_values[name][stripped] += 1

        diagnosis = clean(row[diagnosis_index])
        if diagnosis:
            diagnosis_counts[diagnosis] += 1

    field_summary = []
    for name in header:
        missing_count = missing[name]
        field_summary.append(
            {
                "name": name,
                "kind": summarize_kinds(kinds[name]),
                "missing": missing_count,
                "nonempty": row_count - malformed_rows - missing_count,
            }
        )

    return {
        "file": csv_path.name,
        "size_bytes": csv_path.stat().st_size,
        "columns": len(header),
        "rows": row_count,
        "malformed_rows": malformed_rows,
        "diagnosis_field": diagnosis_field,
        "diagnosis_nonempty_distinct": len(diagnosis_counts),
        "diagnosis_top": [
            {"name": name, "case_count": count}
            for name, count in sorted(
                diagnosis_counts.items(), key=lambda item: (-item[1], item[0])
            )[:top_n]
        ],
        "numeric_anomalies": {
            name: [
                {"value": value, "count": count}
                for value, count in values.most_common(20)
            ]
            for name, values in anomaly_values.items()
        },
        "sample_rows": [dict(zip(header, row)) for row in sample_rows],
        "fields": field_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "--diagnosis-field",
        default="CCSR Diagnosis Description",
        help="MVP 的疾病分组字段",
    )
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    result = inspect(args.csv_path, args.diagnosis_field, args.top)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
