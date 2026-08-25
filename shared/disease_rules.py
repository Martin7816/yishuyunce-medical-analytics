"""Shared rules for excluding non-disease diagnosis labels from disease views."""

from __future__ import annotations


NON_DISEASE_DIAGNOSIS_NAMES = frozenset({"LIVEBORN", "活产儿"})


def is_non_disease_diagnosis(value: object) -> bool:
    """Return whether a raw diagnosis label is not a disease category."""

    if not isinstance(value, str):
        return False
    return value.strip().upper() in NON_DISEASE_DIAGNOSIS_NAMES
