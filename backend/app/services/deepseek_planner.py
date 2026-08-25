"""DeepSeek adapter for the strict ``query_analytics-v1`` planner contract.

The adapter deliberately depends on an injected structured-output client.  It
does not call the legacy chat/tool client, parse JSON from a message's
``content`` field, or expose a database representation to the model.  The
client boundary is therefore easy to replace with a real DeepSeek transport
without changing validation or the downstream analytics pipeline.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol, runtime_checkable

from shared.query_plan_contract import (
    QUERY_ANALYTICS_SCHEMA,
    QUERY_ANALYTICS_VERSION,
    QueryPlan,
)

from .ai_evidence import assess_question_scope, is_simple_conversation
from .query_plan_validator import QueryPlanValidationError, QueryPlanValidator
from .semantic_registry import SemanticRegistry, semantic_registry


DEEPSEEK_PLANNER_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "query_analytics_v1",
        "strict": True,
        "schema": QUERY_ANALYTICS_SCHEMA,
    },
}

# Descriptive aliases make the intended API boundary explicit to callers.
QUERY_PLAN_RESPONSE_FORMAT = DEEPSEEK_PLANNER_RESPONSE_FORMAT
STRUCTURED_QUERY_PLAN_RESPONSE_FORMAT = DEEPSEEK_PLANNER_RESPONSE_FORMAT


DEEPSEEK_PLANNER_SYSTEM_PROMPT = """You are a medical operations analytics planner.
Return exactly one JSON object that conforms to query_analytics-v1.
Use only canonical semantic dimension and measure IDs supported by the schema.
The object may contain only version, dimensions, measures, filters, sort, and
limit. Do not return prose, explanations, SQL, table names, physical fields,
joins, patient-level data, or executable expressions. A question outside the
supported aggregate analytics scope must not be converted into a query plan.

The exact required shape is:
{"version":"query_analytics-v1","dimensions":["diagnosis"],"measures":["case_count"],"filters":[],"sort":[{"by":"case_count","direction":"desc"}],"limit":10}
Use the exact key "by" inside sort items, never "field". Use lowercase
canonical IDs and lowercase sort directions. Use "diagnosis", never the alias
"disease". Do not shorten the version to "v1" and do not add any other key.

Canonical measure mapping is strict: case counts use "case_count", average
length of stay uses "avg_los", average charges or fees use "avg_charges", and
average costs use "avg_costs". Do not invent variants such as "avg_cost".
For a Medicare average-charge question, the canonical shape is:
{"version":"query_analytics-v1","dimensions":[],"measures":["avg_charges"],"filters":[{"dimension":"payment","operator":"eq","value":"Medicare"}],"sort":[],"limit":1}
"""


_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_FORBIDDEN_QUESTION_PATTERN = re.compile(
    r"(?:"
    r"\b(?:select|insert|update|delete|drop|alter|truncate|union|sql)\b"
    r"|\b(?:table|join|field|mrn|ssn)\b"
    r"|\bpatient(?:[- ]level|[- ]data|[- ]records?|[- ]details?|[_ ]id)\b"
    r"|--|/\*|\*/|;"
    r"|个人明细|个人级|身份证|姓名"
    r")",
    re.IGNORECASE,
)

_ANALYTICS_HINTS = (
    "analytics",
    "analysis",
    "metric",
    "metrics",
    "medical",
    "healthcare",
    "hospital",
    "hospitals",
    "facility",
    "facilities",
    "diagnosis",
    "disease",
    "age",
    "gender",
    "sex",
    "severity",
    "payment",
    "payer",
    "admission",
    "case",
    "cases",
    "count",
    "counts",
    "average",
    "avg",
    "charge",
    "charges",
    "cost",
    "costs",
    "los",
    "rate",
    "rates",
    "emergency",
    "surgical",
    "severe",
    "rank",
    "ranking",
    "top",
    "compare",
    "comparison",
    "distribution",
    "share",
    "breakdown",
    "group",
    "show",
    "how many",
    "volume",
    "patient",
    "patients",
    "医院",
    "诊断",
    "疾病",
    "年龄",
    "性别",
    "严重",
    "支付",
    "入院",
    "病例",
    "患者",
    "病人",
    "数量",
    "费用",
    "成本",
    "平均",
    "比例",
    "排名",
    "分布",
    "比较",
    "按",
)


@runtime_checkable
class StructuredDeepSeekClientProtocol(Protocol):
    """Client boundary for a provider's native structured-output operation."""

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_format: Mapping[str, Any],
    ) -> object:
        """Return a provider-parsed structured object or response envelope."""


class DeepSeekPlannerError(ValueError):
    """Base error for fail-closed planner failures."""


class UnsupportedPlannerIntent(DeepSeekPlannerError):
    """The question is not eligible for aggregate analytics planning."""


class StructuredOutputError(DeepSeekPlannerError):
    """The provider did not return a native structured object."""


class PlannerOutputValidationError(DeepSeekPlannerError):
    """The structured object is not a valid query_analytics-v1 plan."""


def _contains_hint(question: str, hint: str) -> bool:
    if any(ord(character) > 127 for character in hint):
        return hint in question
    if " " in hint:
        return hint in question.casefold()
    return re.search(rf"\b{re.escape(hint)}\b", question, re.IGNORECASE) is not None


def _looks_like_analytics_question(
    question: str, registry: SemanticRegistry
) -> bool:
    """Require a small deterministic analytics-intent signal before routing."""

    if any(_contains_hint(question, hint) for hint in _ANALYTICS_HINTS):
        return True

    for spec in registry.dimensions.values():
        if any(_contains_hint(question, alias) for alias in (spec.id, *spec.aliases)):
            return True
    for spec in registry.measures.values():
        if any(_contains_hint(question, alias) for alias in (spec.id, spec.display_name)):
            return True
    return False


def _validate_question(question: object, registry: SemanticRegistry) -> str:
    if not isinstance(question, str) or not question.strip():
        raise UnsupportedPlannerIntent("question must be a non-empty string")

    normalized = question.strip()
    if len(normalized) > 512:
        raise UnsupportedPlannerIntent("question exceeds the planner input limit")
    if _CONTROL_CHARACTER_PATTERN.search(normalized):
        raise UnsupportedPlannerIntent("question contains control characters")
    if _FORBIDDEN_QUESTION_PATTERN.search(normalized):
        raise UnsupportedPlannerIntent("question contains forbidden query content")

    scope = assess_question_scope(normalized)
    if scope is not None:
        status = str(scope.get("status") or "unsupported")
        reason = str(scope.get("reason") or "question is outside safe analytics scope")
        raise UnsupportedPlannerIntent(f"{status}: {reason}")
    if is_simple_conversation(normalized):
        raise UnsupportedPlannerIntent("conversation is not an analytics intent")
    if not _looks_like_analytics_question(normalized, registry):
        raise UnsupportedPlannerIntent(
            "question does not identify a supported aggregate analytics intent"
        )
    return normalized


def _extract_structured_document(response: object) -> Mapping[str, Any]:
    """Extract only provider-parsed objects; never parse free-text content."""

    if isinstance(response, QueryPlan):
        return response.to_document()
    if not isinstance(response, Mapping):
        raise StructuredOutputError("structured planner response must be an object")

    # Some injected clients return the parsed JSON object directly.
    if "version" in response:
        return response

    for key in ("parsed", "structured_output", "output", "json_schema", "json"):
        candidate = response.get(key)
        if isinstance(candidate, Mapping):
            return candidate
        if candidate is not None:
            raise StructuredOutputError(
                f"structured planner response field {key} must be an object"
            )

    # Also accept the common provider envelope, but only its parsed field.
    choices = response.get("choices")
    if isinstance(choices, list) and len(choices) == 1:
        choice = choices[0]
        if isinstance(choice, Mapping):
            message = choice.get("message")
            if isinstance(message, Mapping):
                for key in ("parsed", "structured_output", "json_schema", "json"):
                    candidate = message.get(key)
                    if isinstance(candidate, Mapping):
                        return candidate
                    if candidate is not None:
                        raise StructuredOutputError(
                            f"structured planner message field {key} must be an object"
                        )

    raise StructuredOutputError(
        "planner response did not contain a provider-parsed structured object"
    )


class DeepSeekPlannerAdapter:
    """Turn one natural-language question into a validated immutable plan.

    The adapter is intentionally transport-agnostic.  A production DeepSeek
    client must expose ``complete_structured`` and honor the supplied strict
    JSON-schema response format.  A legacy ``complete`` method is accepted
    only when it explicitly accepts ``response_format``; free-text responses
    are rejected in all cases.
    """

    def __init__(
        self,
        client: StructuredDeepSeekClientProtocol | object,
        *,
        validator: QueryPlanValidator | None = None,
        registry: SemanticRegistry | None = None,
        system_prompt: str = DEEPSEEK_PLANNER_SYSTEM_PROMPT,
    ) -> None:
        if client is None:
            raise ValueError("structured DeepSeek client is required")
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt must be a non-empty string")
        self.client = client
        self.registry = registry or semantic_registry
        self.validator = validator or QueryPlanValidator(self.registry)
        self.system_prompt = system_prompt

    def _messages(self, question: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]

    def _complete_structured(
        self,
        messages: list[dict[str, str]],
        response_format: Mapping[str, Any],
    ) -> object:
        complete_structured = getattr(self.client, "complete_structured", None)
        if callable(complete_structured):
            try:
                return complete_structured(messages, response_format)
            except DeepSeekPlannerError:
                raise
            except Exception as error:
                raise StructuredOutputError(
                    "structured DeepSeek request failed"
                ) from error

        # This fallback is deliberately narrow.  The legacy client has no
        # response_format parameter and therefore cannot be used accidentally.
        complete = getattr(self.client, "complete", None)
        if callable(complete):
            try:
                return complete(messages, response_format=response_format)
            except TypeError as error:
                raise StructuredOutputError(
                    "DeepSeek client does not expose strict structured output"
                ) from error
            except DeepSeekPlannerError:
                raise
            except Exception as error:
                raise StructuredOutputError(
                    "structured DeepSeek request failed"
                ) from error

        raise StructuredOutputError(
            "DeepSeek client must expose complete_structured(messages, response_format)"
        )

    def generate_plan(self, question: str) -> QueryPlan:
        """Generate one validated plan or fail closed without a fallback plan."""

        normalized_question = _validate_question(question, self.registry)
        response_format = deepcopy(DEEPSEEK_PLANNER_RESPONSE_FORMAT)
        response = self._complete_structured(
            self._messages(normalized_question),
            response_format,
        )
        document = _extract_structured_document(response)
        try:
            return self.validator.validate(document)
        except QueryPlanValidationError as error:
            raise PlannerOutputValidationError(str(error)) from error
        except (TypeError, ValueError) as error:
            raise PlannerOutputValidationError(
                "planner response failed query plan validation"
            ) from error

    def plan(self, question: str) -> QueryPlan:
        """Compatibility alias for planner callers using ``plan`` terminology."""

        return self.generate_plan(question)


# Short aliases keep the adapter convenient while preserving one implementation.
DeepSeekPlanner = DeepSeekPlannerAdapter
DeepSeekQueryPlanner = DeepSeekPlannerAdapter


__all__ = [
    "DEEPSEEK_PLANNER_RESPONSE_FORMAT",
    "DEEPSEEK_PLANNER_SYSTEM_PROMPT",
    "DeepSeekPlanner",
    "DeepSeekPlannerAdapter",
    "DeepSeekPlannerError",
    "DeepSeekQueryPlanner",
    "PlannerOutputValidationError",
    "QUERY_PLAN_RESPONSE_FORMAT",
    "STRUCTURED_QUERY_PLAN_RESPONSE_FORMAT",
    "StructuredDeepSeekClientProtocol",
    "StructuredOutputError",
    "UnsupportedPlannerIntent",
]
