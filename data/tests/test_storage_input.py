from __future__ import annotations

import sys
from pathlib import Path

import pytest


DATA_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_ROOT / "src"))

from storage_input import DataSource, fingerprint_source  # noqa: E402


def test_local_fixture_source_keeps_fixture_boundary():
    source = DataSource.from_arguments(
        str(DATA_ROOT / "fixtures" / "sparcs_mvp_sample.csv")
    )

    assert source.kind == "file"
    assert source.name == "sparcs_mvp_sample.csv"
    assert source.is_fixture is True


def test_hdfs_source_uses_explicit_content_fingerprint():
    source = DataSource.from_arguments(
        "hdfs://hadoop001:9000/project/yishuyunce/raw/sparcs/2021/data.csv"
    )
    digest = "a" * 64

    assert source.kind == "hdfs"
    assert source.name == "data.csv"
    assert fingerprint_source(source, digest) == digest


def test_remote_source_requires_a_verified_sha256():
    source = DataSource.from_arguments("hdfs://hadoop001:9000/project/data.csv")

    with pytest.raises(ValueError, match="--input-sha256"):
        fingerprint_source(source)


def test_hive_table_is_validated_and_keeps_table_reference():
    source = DataSource.from_arguments(
        hive_table="analytics_check.sparcs_2021_raw_issue39"
    )

    assert source.kind == "hive"
    assert source.reference == "analytics_check.sparcs_2021_raw_issue39"
    assert source.name == "sparcs_2021_raw_issue39"

    with pytest.raises(ValueError, match="Hive 表名"):
        DataSource.from_arguments(hive_table="analytics_check.raw;drop")
