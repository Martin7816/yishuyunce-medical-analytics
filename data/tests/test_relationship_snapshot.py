from __future__ import annotations

from pathlib import Path
import sys


DATA_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_ROOT / "src"))

from verify_relationships_snapshot import scan_source  # noqa: E402


EDGE_SAMPLE = DATA_ROOT / "fixtures" / "dashboard_edge_sample.csv"


def test_independent_relation_scan_freezes_bins_denominators_and_empty_groups():
    expected, raw_rows, scoped_rows, charges = scan_source(EDGE_SAMPLE, 200.0)

    assert (raw_rows, scoped_rows) == (4, 3)
    assert expected["facility_case_counts"] == {"F001": 2, "F002": 1}
    assert expected["facilities"]["F001"] == {
        "label": "Hospital A",
        "count": 2,
        "los": 6.0,
        "charges": 300.0,
        "severe": 1,
        "severity_valid": 1,
    }
    assert sorted(charges) == [100.0, 200.0]

    wildcard_cost = expected["cost_relation"][(None, None, None)]
    assert list(wildcard_cost) == [
        ("2-3天", "Major"),
        ("4-6天", "未分类"),
    ]
    assert wildcard_cost[("2-3天", "Major")]["count"] == 1
    assert wildcard_cost[("4-6天", "未分类")]["high"] == 1

    major_cell = expected["risk_matrix"][(None, None, "0 to 17", "Major")]
    assert major_cell == {"count": 1, "high": 1}
