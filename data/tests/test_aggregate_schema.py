from __future__ import annotations

from pathlib import Path


SCHEMA = (
    Path(__file__).resolve().parents[1] / "sql" / "003-aggregate-fact.sql"
).read_text(encoding="utf-8")


def test_schema_uses_mysql8_exact_internal_storage():
    assert SCHEMA.count("ENGINE = InnoDB") == 3
    assert "DEFAULT CHARACTER SET = utf8mb4" in SCHEMA
    assert "COLLATE = utf8mb4_bin" in SCHEMA
    assert "CHARACTER SET ascii COLLATE ascii_bin" in SCHEMA


def test_schema_enforces_single_active_batch_and_active_pointer_status():
    assert "GENERATED ALWAYS AS" in SCHEMA
    assert "CASE WHEN `status` = 'ACTIVE' THEN 1 ELSE NULL END" in SCHEMA
    assert "uq_aggregate_batch_single_active" in SCHEMA
    assert "UNIQUE KEY `uq_aggregate_batch_status` (`batch_id`, `status`)" in SCHEMA
    assert "`batch_status`" in SCHEMA
    assert "`batch_status` = 'ACTIVE'" in SCHEMA
    assert "FOREIGN KEY (`batch_id`, `batch_status`)" in SCHEMA
    assert "REFERENCES `analytics_aggregate_batch` (`batch_id`, `status`)" in SCHEMA


def test_schema_does_not_keep_the_redundant_batch_prefix_index():
    assert "idx_aggregate_fact_batch" not in SCHEMA
