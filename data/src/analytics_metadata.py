"""Shared metadata rules for reproducible analytics artifacts."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path


KNOWN_SOURCE_NAME = (
    "Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_data_version(csv_path: Path, digest: str) -> str:
    """Build a stable version without exposing a local absolute path."""

    if csv_path.name == KNOWN_SOURCE_NAME:
        return f"sparcs_2021_20231012_sha256_{digest}"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", csv_path.stem).strip("._-")
    return f"{safe_name or 'sparcs_input'}_sha256_{digest}"


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
