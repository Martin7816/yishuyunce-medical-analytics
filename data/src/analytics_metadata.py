"""Shared metadata rules for reproducible analytics artifacts."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse


KNOWN_SOURCE_NAME = (
    "Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_name(source: Path | str) -> str:
    value = str(source)
    parsed = urlparse(value) if "://" in value else None
    if parsed is not None and parsed.scheme:
        return Path(unquote(parsed.path)).name or value.rsplit("/", 1)[-1]
    return Path(value).name


def build_data_version(
    csv_path: Path | str,
    digest: str,
    *,
    fixture: bool | None = None,
) -> str:
    """Build a stable version without exposing a local absolute path."""

    source_name = _source_name(csv_path)
    if source_name == KNOWN_SOURCE_NAME:
        version = f"sparcs_2021_20231012_sha256_{digest}"
    else:
        safe_name = re.sub(
            r"[^A-Za-z0-9._-]+", "_", Path(source_name).stem
        ).strip("._-")
        version = f"{safe_name or 'sparcs_input'}_sha256_{digest}"
    if fixture is None:
        fixture = any(part.lower() == "fixtures" for part in Path(str(csv_path)).parts)
    if fixture:
        return f"fixture:{version}"
    return version


def normalize_generated_at(value: str | None) -> str:
    """Return the single six-microsecond UTC representation used by snapshots."""

    if value is None:
        parsed = datetime.now(UTC)
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("--generated-at 必须包含时区")
        parsed = parsed.astimezone(UTC)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")
