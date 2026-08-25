from __future__ import annotations

import sys
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
sys.path.insert(0, str(DATA_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from publish_aggregate_mysql import _fetch_fact_reconciliation  # noqa: E402


class _Cursor:
    def __init__(self, row):
        self.row = row

    def execute(self, query, params):
        assert "record_count_sum" in query
        assert params == ("test-batch",)

    def fetchone(self):
        return self.row


@pytest.mark.parametrize(
    "row",
    [
        (665580, 2101588),
        {"fact_rows": 665580, "record_count_sum": 2101588},
    ],
)
def test_fact_reconciliation_has_a_stable_mapping_contract(row):
    assert _fetch_fact_reconciliation(_Cursor(row), "test-batch") == {
        "fact_rows": 665580,
        "record_count_sum": 2101588,
    }
