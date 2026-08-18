"""Small interface over all published analytics snapshot records."""

from __future__ import annotations

from datetime import UTC, datetime

from ..errors import InvalidServiceResultError


def _format_utc(value) -> str:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ValueError("invalid generated_at")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


class AnalyticsSnapshotService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def get(self, module_key: str, entity_key: str) -> dict:
        try:
            record = self.repository.fetch(module_key, entity_key)
            payload = record["payload"]
            version = record["data_version"]
            if not isinstance(payload, dict) or not isinstance(version, str) or not version:
                raise ValueError("invalid snapshot")
            result = dict(payload)
            result["data_version"] = version
            result["generated_at"] = _format_utc(record["generated_at"])
            return result
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidServiceResultError() from error
