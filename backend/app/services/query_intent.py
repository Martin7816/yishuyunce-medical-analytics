"""Deterministic intent hints for natural-language aggregate questions.

The LLM remains responsible for understanding and explaining a question, but
high-confidence domain phrases must not be left entirely to a probabilistic
router.  This module translates a small, auditable subset of Chinese and
English phrases into the existing semantic query vocabulary.  It never reads
data, builds SQL, or bypasses the query-plan validator.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


_AGE_RANGE_PATTERN = re.compile(
    r"(?P<start>\d{1,3})\s*(?:岁|周岁)?\s*(?:-|~|～|至|到)\s*"
    r"(?P<end>\d{1,3})\s*(?:岁|周岁)?",
    re.IGNORECASE,
)
_AGE_UPPER_PATTERN = re.compile(
    r"(?P<age>\d{1,3})\s*(?:岁|周岁)?\s*(?:以上|及以上|或以上|\+)",
    re.IGNORECASE,
)
_AGE_SINGLE_PATTERN = re.compile(r"(?P<age>\d{1,3})\s*(?:岁|周岁)", re.IGNORECASE)
_ENGLISH_AGE_PATTERN = re.compile(
    r"(?P<age>\d{1,3})\s*[- ]?year[- ]?old", re.IGNORECASE
)

_DISEASE_PATTERN = re.compile(
    r"(?:疾病|病种|诊断|什么病|哪种病|哪些病|得病|患病|常见病|"
    r"disease|diagnosis|illness|condition)",
    re.IGNORECASE,
)
_CASE_COUNT_PATTERN = re.compile(
    r"(?:病例|病例量|病例数|病案量|记录数|数量|多少|最多|排名|"
    r"最常见|常见|最容易|容易得|分布|\btop\b|\branking\b|\brank\b|"
    r"\bcase(?:s)?\b|\bcount\b|\bnumber\b|\bmost common\b)",
    re.IGNORECASE,
)
_RANKING_PATTERN = re.compile(
    r"(?:最多|最高|最低|最短|最长|排名|排行|\btop\b|\branking\b|\brank\b|"
    r"最常见|最容易|容易得|最忙|第一|前\s*\d+|\bhighest\b|\blowest\b|"
    r"\blongest\b|\bshortest\b|\bmost common\b|\bbusiest\b)",
    re.IGNORECASE,
)
_DISTRIBUTION_PATTERN = re.compile(
    r"(?:分布|结构|构成|占比|比例|distribution|breakdown|composition|share)",
    re.IGNORECASE,
)
_COMPARISON_PATTERN = re.compile(
    r"(?:比较|对比|差异|哪个更|相比|compare|comparison|difference|versus|vs\.)",
    re.IGNORECASE,
)
_LIMIT_PATTERN = re.compile(r"(?:\btop\s*|前\s*)(?P<limit>\d{1,2})", re.IGNORECASE)
_DIMENSION_PATTERNS = {
    "hospital": re.compile(
        r"(?:医院|机构|院区|hospital|hospitals|facility|facilities)",
        re.IGNORECASE,
    ),
    "diagnosis": re.compile(
        r"(?:疾病|病种|诊断|什么病|哪种病|哪些病|得病|患病|"
        r"disease|diagnosis|illness|condition)",
        re.IGNORECASE,
    ),
    "age_group": re.compile(
        r"(?:年龄|年龄组|年龄段|岁|周岁|age|age\s*group|year[- ]?old)",
        re.IGNORECASE,
    ),
    "gender": re.compile(
        r"(?:性别|男性|女性|男生|女生|gender|sex|male|female)",
        re.IGNORECASE,
    ),
    "severity": re.compile(
        r"(?:严重程度|病情|重症|轻症|severity|acuity|severe)",
        re.IGNORECASE,
    ),
    "payment": re.compile(
        r"(?:支付|付款|医保|保险|payer|payment|medicare|medicaid|"
        r"insurance)",
        re.IGNORECASE,
    ),
    "admission_type": re.compile(
        r"(?:入院|住院方式|入院方式|急诊入院|admission)",
        re.IGNORECASE,
    ),
}
_MEASURE_PATTERNS = {
    "avg_los": re.compile(
        r"(?:平均住院|住院时长|住院时间|住院天数|平均停留|"
        r"average\s+length\s+of\s+stay|length\s+of\s+stay|\blos\b)",
        re.IGNORECASE,
    ),
    "avg_charges": re.compile(
        r"(?:平均费用|平均收费|收费|账单|花费|charges?|fees?|bill(?:ing)?)",
        re.IGNORECASE,
    ),
    "avg_costs": re.compile(
        r"(?:平均成本|成本|costs?)",
        re.IGNORECASE,
    ),
    "emergency_rate": re.compile(
        r"(?:急诊率|急诊比例|emergency\s+rate)", re.IGNORECASE
    ),
    "surgical_rate": re.compile(
        r"(?:手术率|手术比例|手术相关率|surgical\s+rate)", re.IGNORECASE
    ),
    "severe_rate": re.compile(
        r"(?:重症率|严重率|严重程度比例|severe\s+rate)", re.IGNORECASE
    ),
}
_GENDER_BOTH_PATTERN = re.compile(r"(?:男女|男女性别|both\s+genders?)", re.IGNORECASE)
_FEMALE_PATTERN = re.compile(
    r"(?:女性|女生|女人|女\s*性|female|woman|women|\bF\b)", re.IGNORECASE
)
_MALE_PATTERN = re.compile(
    r"(?:男性|男生|男人|男\s*性|male|man|men|\bM\b)", re.IGNORECASE
)

_AGE_BUCKETS = (
    (0, 17, "0 to 17"),
    (18, 29, "18 to 29"),
    (30, 49, "30 to 49"),
    (50, 69, "50 to 69"),
)


@dataclass(frozen=True, slots=True)
class NaturalLanguageIntent:
    """A bounded, non-executable interpretation of a user question."""

    dimensions: tuple[str, ...] = ()
    measures: tuple[str, ...] = ()
    filters: tuple[dict[str, Any], ...] = ()
    notes: tuple[str, ...] = ()
    disease_case_ranking: bool = False
    ranking_requested: bool = False
    distribution_requested: bool = False
    comparison_requested: bool = False
    requested_limit: int | None = None

    @property
    def has_explicit_filter(self) -> bool:
        return bool(self.filters)

    @property
    def has_structured_intent(self) -> bool:
        """Whether the question has enough semantics for aggregate planning."""

        # ``dimensions=[]`` is a valid aggregate-overall query, for example
        # “当前病例数量” or “平均费用是多少？”.
        return bool(self.measures)


def _age_bucket(age: int) -> str:
    for lower, upper, label in _AGE_BUCKETS:
        if lower <= age <= upper:
            return label
    return "70 or Older"


def _range_bucket(start: int, end: int) -> str | None:
    if start > end or start < 0 or end > 120:
        return None
    for lower, upper, label in _AGE_BUCKETS:
        if start <= lower and end >= upper:
            return label
    if start >= 70:
        return "70 or Older"
    # A partial natural-language range is still resolved to the smallest
    # published bucket containing its lower bound.  The note makes that
    # coarsening visible to the answer generator.
    return _age_bucket(start)


def _extract_age(
    question: str,
) -> tuple[str | tuple[str, ...] | None, str | None]:
    upper = _AGE_UPPER_PATTERN.search(question)
    if upper:
        try:
            age = int(upper.group("age"))
        except (TypeError, ValueError):
            age = -1
        if age >= 70:
            return "70 or Older", None
        if 0 <= age < 70:
            age_start = _age_bucket(age)
            bucket_labels = [label for _, _, label in _AGE_BUCKETS]
            bucket_labels.append("70 or Older")
            start_index = bucket_labels.index(age_start)
            values = tuple(bucket_labels[start_index:])
            return values, f"{age}岁以上已按发布年龄组映射为{'、'.join(values)}"

    range_match = _AGE_RANGE_PATTERN.search(question)
    if range_match:
        try:
            start = int(range_match.group("start"))
            end = int(range_match.group("end"))
        except (TypeError, ValueError):
            return None, None
        bucket = _range_bucket(start, end)
        if bucket is None:
            return None, None
        exact = bucket == f"{start} to {end}"
        note = None if exact else f"{start}至{end}岁已按发布年龄组映射为{bucket}"
        return bucket, note

    single = _AGE_SINGLE_PATTERN.search(question) or _ENGLISH_AGE_PATTERN.search(
        question
    )
    if not single:
        return None, None
    try:
        age = int(single.group("age"))
    except (TypeError, ValueError):
        return None, None
    if not 0 <= age <= 120:
        return None, None
    bucket = _age_bucket(age)
    return bucket, f"{age}岁已按发布年龄组映射为{bucket}"


def _extract_gender(question: str) -> str | None:
    if _GENDER_BOTH_PATTERN.search(question):
        return None
    if _FEMALE_PATTERN.search(question):
        return "F"
    if _MALE_PATTERN.search(question):
        return "M"
    return None


def infer_natural_language_intent(question: object) -> NaturalLanguageIntent:
    """Return only deterministic hints that are safe for plan normalization."""

    if not isinstance(question, str) or not question.strip():
        return NaturalLanguageIntent()
    normalized = question.strip()
    age_value, age_note = _extract_age(normalized)
    gender_value = _extract_gender(normalized)
    has_disease = _DISEASE_PATTERN.search(normalized) is not None
    has_case_count = _CASE_COUNT_PATTERN.search(normalized) is not None
    ranking_requested = _RANKING_PATTERN.search(normalized) is not None
    distribution_requested = _DISTRIBUTION_PATTERN.search(normalized) is not None
    comparison_requested = _COMPARISON_PATTERN.search(normalized) is not None
    limit_match = _LIMIT_PATTERN.search(normalized)
    requested_limit: int | None = None
    if limit_match:
        try:
            parsed_limit = int(limit_match.group("limit"))
        except (TypeError, ValueError):
            parsed_limit = 0
        if parsed_limit > 0:
            # The shared query contract deliberately caps result size at 10.
            requested_limit = min(parsed_limit, 10)
    explicit_measures = tuple(
        measure_id
        for measure_id, pattern in _MEASURE_PATTERNS.items()
        if pattern.search(normalized)
    )
    has_case_measure = has_case_count or ranking_requested or distribution_requested

    filters: list[dict[str, Any]] = []
    notes: list[str] = []
    if age_value is not None:
        age_operator = "in" if isinstance(age_value, tuple) else "eq"
        age_filter_value: str | list[str] = (
            list(age_value) if isinstance(age_value, tuple) else age_value
        )
        filters.append(
            {
                "dimension": "age_group",
                "operator": age_operator,
                "value": age_filter_value,
            }
        )
        if age_note:
            notes.append(age_note)
    if gender_value is not None:
        filters.append(
            {"dimension": "gender", "operator": "eq", "value": gender_value}
        )

    # Known published enum values can be converted to filters without asking
    # the model to guess their spelling.  Unknown hospital/diagnosis values
    # remain the planner's responsibility and are still validator-checked.
    payment_aliases = (
        ("Medicare", "Medicare"),
        ("Medicaid", "Medicaid"),
        ("Private Health Insurance", "Private Health Insurance"),
        ("Self-Pay", "Self-Pay"),
        ("自费", "Self-Pay"),
    )
    for alias, value in payment_aliases:
        if re.search(re.escape(alias), normalized, re.IGNORECASE):
            filters.append(
                {"dimension": "payment", "operator": "eq", "value": value}
            )
            break

    if "入院" in normalized or re.search(r"admission\s*(type)?", normalized, re.I):
        admission_aliases = (
            ("急诊", "Emergency"),
            ("择期", "Elective"),
            ("新生儿", "Newborn"),
            ("紧急", "Urgent"),
            ("创伤", "Trauma"),
        )
        for alias, value in admission_aliases:
            if alias in normalized:
                filters.append(
                    {
                        "dimension": "admission_type",
                        "operator": "eq",
                        "value": value,
                    }
                )
                break

    disease_case_ranking = has_disease and has_case_measure and ranking_requested
    if disease_case_ranking:
        notes.append(
            "本结果统计住院出院记录中的病例量，不等同于一般人群患病率或个体患病风险"
        )
    elif "case_count" in explicit_measures or has_case_measure:
        notes.append("病例量指住院出院记录数，不等同于一般人群患病率或个体患病风险")

    dimensions: list[str] = [
        dimension_id
        for dimension_id, pattern in _DIMENSION_PATTERNS.items()
        if pattern.search(normalized)
    ]
    # An explicit value such as “男性” or “50岁” is a filter, not a GROUP BY
    # dimension.  Phrases such as “不同性别/年龄段” remain dimensions.
    if gender_value is not None:
        dimensions = [item for item in dimensions if item != "gender"]
    if age_value is not None:
        dimensions = [item for item in dimensions if item != "age_group"]
    filter_dimensions = {
        item.get("dimension")
        for item in filters
        if isinstance(item, Mapping)
    }
    dimensions = [item for item in dimensions if item not in filter_dimensions]

    if disease_case_ranking:
        dimensions = ["diagnosis"]

    measures = explicit_measures
    if not measures and has_case_measure:
        measures = ("case_count",)
    return NaturalLanguageIntent(
        dimensions=tuple(dict.fromkeys(dimensions)),
        measures=measures,
        filters=tuple(filters),
        notes=tuple(dict.fromkeys(notes)),
        disease_case_ranking=disease_case_ranking,
        ranking_requested=ranking_requested,
        distribution_requested=distribution_requested,
        comparison_requested=comparison_requested,
        requested_limit=requested_limit,
    )


# Keep this allowlist aligned with the server-owned capability compiler.  The
# deterministic planner is only a recovery path for high-confidence wording;
# it must never manufacture a new aggregate shape.
_DETERMINISTIC_DIMENSION_SHAPES = {
    frozenset(),
    frozenset({"hospital"}),
    frozenset({"diagnosis"}),
    frozenset({"age_group"}),
    frozenset({"gender"}),
    frozenset({"severity"}),
    frozenset({"payment"}),
    frozenset({"admission_type"}),
    frozenset({"age_group", "diagnosis"}),
    frozenset({"gender", "diagnosis"}),
    frozenset({"hospital", "severity"}),
    frozenset({"payment", "age_group"}),
}


def build_deterministic_query_plan(
    question: object,
) -> dict[str, Any] | None:
    """Build a safe plan for a small, auditable high-confidence intent subset.

    This function never reads data and never creates SQL.  It is deliberately
    narrower than the LLM planner and is used only when the provider is
    unavailable or transiently fails.  The returned document still has to pass
    ``QueryPlanValidator`` and ``SafeQueryCompiler`` downstream.
    """

    intent = infer_natural_language_intent(question)
    if not intent.has_structured_intent:
        return None
    if frozenset(intent.dimensions) not in _DETERMINISTIC_DIMENSION_SHAPES:
        return None

    sort = []
    if intent.ranking_requested:
        sort = [{"by": intent.measures[0], "direction": "desc"}]

    return {
        "version": "query_analytics-v1",
        "dimensions": list(intent.dimensions),
        "measures": list(intent.measures),
        "filters": [dict(item) for item in intent.filters],
        "sort": sort,
        "limit": intent.requested_limit or 10,
    }


def merge_query_plan_with_intent(
    question: object, document: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Normalize high-confidence explicit filters before plan validation.

    The returned object still has to pass ``QueryPlanValidator``.  This is a
    correction layer for ambiguous Chinese phrasing, not an alternative query
    compiler and not a permission to add arbitrary fields.
    """

    if not isinstance(document, Mapping):
        return document
    intent = infer_natural_language_intent(question)
    if not intent.has_structured_intent:
        return document
    if not (
        intent.filters
        or intent.requested_limit is not None
        or intent.ranking_requested
        or intent.distribution_requested
        or intent.comparison_requested
    ):
        return document

    normalized = deepcopy(dict(document))
    normalized["dimensions"] = list(intent.dimensions)
    normalized["measures"] = list(intent.measures)

    existing_filters = normalized.get("filters")
    deterministic_filter_dimensions = {
        item["dimension"]
        for item in intent.filters
        if isinstance(item.get("dimension"), str)
    }
    # These dimensions have deterministic phrase/value extraction above. Any
    # provider-guessed value for them must not survive when it conflicts with
    # the user's wording (for example a hallucinated age filter).
    replaced_filter_dimensions = deterministic_filter_dimensions | {
        "age_group",
        "gender",
        "payment",
        "admission_type",
    }
    preserved: list[dict[str, Any]] = []
    if isinstance(existing_filters, list):
        for item in existing_filters:
            if not isinstance(item, Mapping):
                continue
            dimension = item.get("dimension")
            if dimension not in replaced_filter_dimensions:
                preserved.append(dict(item))

    normalized["filters"] = [dict(item) for item in intent.filters] + preserved
    if intent.ranking_requested:
        sort_measure = intent.measures[0]
        normalized["sort"] = [{"by": sort_measure, "direction": "desc"}]
    else:
        selected = set(intent.dimensions) | set(intent.measures)
        raw_sort = normalized.get("sort")
        sort_items = raw_sort if isinstance(raw_sort, list) else []
        normalized["sort"] = [
            dict(item)
            for item in sort_items
            if isinstance(item, Mapping)
            and item.get("by") in selected
        ]
    limit = intent.requested_limit or normalized.get("limit", 10)
    normalized["limit"] = (
        limit
        if isinstance(limit, int)
        and not isinstance(limit, bool)
        and 1 <= limit <= 10
        else 10
    )
    return normalized


def query_scope_notes(question: object) -> tuple[str, ...]:
    """Return user-visible caveats for deterministic filters and measures."""

    return infer_natural_language_intent(question).notes


__all__ = [
    "NaturalLanguageIntent",
    "build_deterministic_query_plan",
    "infer_natural_language_intent",
    "merge_query_plan_with_intent",
    "query_scope_notes",
]
