"""Small interface over all published analytics snapshot records."""

from __future__ import annotations

from copy import deepcopy

from shared.analytics_snapshot_contract import (
    SnapshotContractError,
    normalize_utc_timestamp,
    validate_data_version,
    validate_payload,
)

from ..errors import InvalidServiceResultError


def _format_utc(value) -> str:
    return normalize_utc_timestamp(value)


class AnalyticsSnapshotService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def get(self, module_key: str, entity_key: str) -> dict:
        try:
            record = self.repository.fetch(module_key, entity_key)
            payload = deepcopy(validate_payload(record["payload"]))
            version = validate_data_version(record["data_version"])
            result = dict(payload)
            result["data_version"] = version
            result["generated_at"] = _format_utc(record["generated_at"])
            return result
        except (KeyError, TypeError, OverflowError, SnapshotContractError) as error:
            raise InvalidServiceResultError() from error
