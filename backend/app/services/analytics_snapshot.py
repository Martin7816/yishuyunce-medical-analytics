"""Small interface over all published analytics snapshot records."""

from __future__ import annotations

from copy import deepcopy

from shared.analytics_snapshot_contract import (
    SnapshotContractError,
    normalize_utc_timestamp,
    validate_data_version,
    validate_disease_semantics,
    validate_payload,
    validate_payload_metadata,
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
            validate_disease_semantics(payload, module_key, entity_key)
            version = validate_data_version(record["data_version"])
            validate_payload_metadata(payload, version, record["generated_at"])
            result = dict(payload)
            result["data_version"] = version
            result["generated_at"] = _format_utc(record["generated_at"])
            return result
        except (KeyError, TypeError, OverflowError, SnapshotContractError) as error:
            raise InvalidServiceResultError() from error
