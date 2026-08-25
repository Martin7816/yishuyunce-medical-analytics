"""Input adapters for local files, HDFS paths, and Hive tables.

The analytics transformations deliberately do not know where the raw data is
stored.  This module keeps the storage change at the input boundary so the
same ``clean_frame`` and aggregation code can run against a local teaching
fixture, an HDFS CSV, or a Hive external table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse


REMOTE_SCHEMES = frozenset({"hdfs", "viewfs", "s3", "s3a", "abfs", "abfss"})
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
HIVE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


@dataclass(frozen=True)
class DataSource:
    """A validated raw-data reference independent of the storage backend."""

    kind: str
    reference: str
    name: str
    local_path: Path | None = None
    is_fixture: bool = False

    @property
    def is_local(self) -> bool:
        return self.kind == "file"

    @property
    def is_hdfs(self) -> bool:
        return self.kind == "hdfs"

    @property
    def version_path(self) -> Path:
        """Return a path-like value used only for stable version naming."""

        return self.local_path or Path(self.name)

    @classmethod
    def from_arguments(
        cls,
        input_value: str | None = None,
        hive_table: str | None = None,
    ) -> "DataSource":
        if bool(input_value) == bool(hive_table):
            raise ValueError("必须且只能指定 --input 或 --hive-table")

        if hive_table:
            table = _validate_hive_table(hive_table)
            return cls(
                kind="hive",
                reference=table,
                name=table.rsplit(".", 1)[-1],
            )

        value = input_value.strip()
        parsed = urlparse(value) if "://" in value else None
        if parsed is not None and parsed.scheme in REMOTE_SCHEMES:
            name = PurePosixPath(unquote(parsed.path)).name
            if not name:
                raise ValueError(f"远程输入缺少文件名: {value}")
            return cls(kind="hdfs", reference=value, name=name)

        if parsed is not None and parsed.scheme:
            raise ValueError(
                f"不支持的输入协议 {parsed.scheme!r}；请使用本地路径、HDFS URI 或 --hive-table"
            )

        path = Path(value).expanduser().resolve()
        return cls(
            kind="file",
            reference=str(path),
            name=path.name,
            local_path=path,
            is_fixture=any(part.lower() == "fixtures" for part in path.parts),
        )


def _validate_hive_table(value: str) -> str:
    table = value.strip()
    if not HIVE_IDENTIFIER_PATTERN.fullmatch(table):
        raise ValueError(
            "Hive 表名必须是 table 或 database.table，且只能包含字母、数字和下划线"
        )
    return table


def add_source_arguments(parser: Any, *, required: bool) -> None:
    """Add the common source selector to an argparse parser."""

    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument(
        "--input",
        help="本地 CSV 路径或 HDFS URI，例如 hdfs://namenode:8020/project/yishuyunce/raw/...",
    )
    group.add_argument(
        "--hive-table",
        help="Hive 外部表名，例如 analytics_check.sparcs_2021_raw_issue39",
    )
    parser.add_argument(
        "--input-sha256",
        help=(
            "远程 HDFS/Hive 输入对应原始文件的 SHA-256；本地输入不需要。"
            "可在虚拟机中使用 hdfs dfs -cat ... | sha256sum 计算。"
        ),
    )
    parser.add_argument(
        "--data-version",
        help=(
            "可选的已确认批次版本。Hive 表名不是原始文件名时，"
            "用此参数保持分析快照、TOP10 和模型的 data_version 一致。"
        ),
    )


def read_source(spark: Any, source: DataSource) -> Any:
    """Read raw input while leaving all downstream transformations unchanged."""

    if source.kind == "hive":
        return spark.table(source.reference)
    return (
        spark.read.option("header", "true")
        .option("inferSchema", "false")
        .option("mode", "FAILFAST")
        .csv(source.reference)
    )


def ensure_local_source_exists(source: DataSource) -> None:
    if source.local_path is not None and not source.local_path.is_file():
        raise ValueError(f"输入文件不存在: {source.local_path}")


def fingerprint_source(source: DataSource, explicit_sha256: str | None = None) -> str:
    """Return a content fingerprint for local or explicitly verified remote input."""

    if explicit_sha256:
        digest = explicit_sha256.strip().lower()
        if not SHA256_PATTERN.fullmatch(digest):
            raise ValueError("--input-sha256 必须是 64 位十六进制 SHA-256")
        return digest

    if source.local_path is None:
        raise ValueError(
            "HDFS/Hive 输入需要提供 --input-sha256；"
            "请先在虚拟机中核对原始文件后传入其 SHA-256"
        )

    from analytics_metadata import sha256_file

    return sha256_file(source.local_path)
