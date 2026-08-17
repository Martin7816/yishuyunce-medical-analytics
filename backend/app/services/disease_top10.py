"""Validation and serialization for published service results."""

from __future__ import annotations

from datetime import UTC, datetime

from ..errors import InvalidServiceResultError


EXPECTED_METRIC = "disease_case_count_top10"
EXPECTED_UNIT = "discharge_records"


def _format_utc(value) -> str:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ValueError("generated_at must be a datetime or ISO-8601 string")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


class DiseaseTop10Service:
    def __init__(self, repository) -> None:
        self.repository = repository

    def get_top10(self) -> dict:
        snapshot = self.repository.fetch()
        try:
            return self._validate_and_serialize(snapshot)
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidServiceResultError() from error

    @staticmethod
    def _validate_and_serialize(snapshot: dict) -> dict:
        if snapshot["metric"] != EXPECTED_METRIC:
            raise ValueError("unexpected metric")
        if snapshot["unit"] != EXPECTED_UNIT:
            raise ValueError("unexpected unit")
        if not isinstance(snapshot["data_version"], str) or not snapshot["data_version"]:
            raise ValueError("missing data version")

        generated_at = _format_utc(snapshot["generated_at"])
        items = snapshot["items"]
        if not isinstance(items, list) or len(items) > 10:
            raise ValueError("invalid item count")

        row_metadata = snapshot.get("_row_metadata")
        if row_metadata is not None:
            if len(row_metadata) != len(items):
                raise ValueError("metadata row count mismatch")
            expected_metadata = {
                "unit": snapshot["unit"],
                "data_version": snapshot["data_version"],
                "generated_at": generated_at,
            }
            for metadata in row_metadata:
                candidate = {
                    "unit": metadata["unit"],
                    "data_version": metadata["data_version"],
                    "generated_at": _format_utc(metadata["generated_at"]),
                }
                if candidate != expected_metadata:
                    raise ValueError("mixed batch metadata")

        names = set()
        serialized_items = []
        previous_sort_key = None
        for expected_rank, item in enumerate(items, start=1):
            rank = item["rank"]
            name = item["diagnosis_name"]
            count = item["case_count"]
            if (
                isinstance(rank, bool)
                or not isinstance(rank, int)
                or rank != expected_rank
            ):
                raise ValueError("ranks must be continuous")
            if not isinstance(name, str) or not name or len(name) > 255:
                raise ValueError("invalid diagnosis name")
            if name in names:
                raise ValueError("duplicate diagnosis name")
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError("invalid case count")
            sort_key = (-count, name)
            if previous_sort_key is not None and sort_key < previous_sort_key:
                raise ValueError("published rows violate the frozen sort order")
            previous_sort_key = sort_key
            names.add(name)
            serialized_items.append(
                {
                    "rank": rank,
                    "diagnosis_name": name,
                    "case_count": count,
                }
            )

        return {
            "metric": EXPECTED_METRIC,
            "unit": EXPECTED_UNIT,
            "data_version": snapshot["data_version"],
            "generated_at": generated_at,
            "items": serialized_items,
        }
