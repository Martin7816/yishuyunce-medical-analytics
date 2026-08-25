"""Backend-only orchestration for safe aggregate analytics questions.

The planner is an injected protocol.  This module intentionally contains no
LLM client, SSE behavior, frontend contract, or conversation generation.  It
only coordinates the already validated Phase 2 components.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from shared.query_plan_contract import QueryPlan
from shared.query_result_contract import QueryResultContract

from .ai_evidence import assess_question_scope, is_simple_conversation
from .diagnosis_label_catalog import DiagnosisLabelResolver
from .query_evidence_adapter import QueryEvidenceAdapter
from .query_plan_validator import QueryPlanValidationError, QueryPlanValidator
from .safe_query_compiler import (
    CompiledAggregateQuery,
    SafeQueryCompiler,
    SafeQueryCompilerError,
)
from .semantic_registry import SemanticRegistry


MAX_AGENT_TOOL_CALLS = 4


@runtime_checkable
class PlannerProtocol(Protocol):
    """Model-independent planner boundary for a future LLM integration."""

    def generate_plan(self, question: str) -> QueryPlan | Mapping[str, Any]:
        ...


@runtime_checkable
class AggregateQueryProtocol(Protocol):
    """Minimal repository boundary required by the orchestrator."""

    def execute(self, query: CompiledAggregateQuery) -> QueryResultContract:
        ...


class AnalyticsAgentError(ValueError):
    """Base error for deterministic orchestration failures."""


class UnsupportedAnalyticsRequest(AnalyticsAgentError):
    """Raised by a planner that cannot represent a question safely."""


class AgentToolLimitExceeded(AnalyticsAgentError):
    """Raised internally when another aggregate query would exceed the limit."""


def _plan_document(plan: object) -> object:
    to_document = getattr(plan, "to_document", None)
    if callable(to_document):
        return to_document()
    return plan


def _control_result(
    question: str,
    *,
    status: str,
    reason: str,
    limitations: list[str] | None = None,
    conversation_bypassed: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "question": question,
        "answerable": False,
        "query_executed": False,
        "tool_calls": 0,
        "query_plan": None,
        "compiled_query": None,
        "query_result": None,
        "evidence": None,
        "provenance": None,
        "reason": reason,
        "conversation_bypassed": conversation_bypassed,
    }
    if limitations:
        result["limitations"] = list(limitations)
    return result


class AnalyticsAgentOrchestrator:
    """Run one question through the safe analytics pipeline."""

    def __init__(
        self,
        planner: PlannerProtocol,
        aggregate_repository: AggregateQueryProtocol,
        *,
        validator: QueryPlanValidator | None = None,
        compiler: SafeQueryCompiler | None = None,
        evidence_adapter: QueryEvidenceAdapter | None = None,
        diagnosis_label_resolver: DiagnosisLabelResolver | None = None,
        registry: SemanticRegistry | None = None,
        max_tool_calls: int = MAX_AGENT_TOOL_CALLS,
        evidence_type: str = "ranking",
    ) -> None:
        if isinstance(max_tool_calls, bool) or not isinstance(max_tool_calls, int):
            raise ValueError("max_tool_calls must be an integer")
        if max_tool_calls < 0:
            raise ValueError("max_tool_calls must not be negative")
        self.planner = planner
        self.aggregate_repository = aggregate_repository
        self.registry = registry
        self.validator = validator or QueryPlanValidator(registry)
        self.compiler = compiler or SafeQueryCompiler(registry)
        self.evidence_adapter = evidence_adapter or QueryEvidenceAdapter(
            diagnosis_label_resolver=diagnosis_label_resolver
        )
        self.max_tool_calls = max_tool_calls
        self.evidence_type = evidence_type

    def _safe_question_gate(self, question: object) -> dict[str, Any] | None:
        if not isinstance(question, str) or not question.strip():
            return _control_result(
                question if isinstance(question, str) else "",
                status="unsupported",
                reason="question must be a non-empty string",
            )

        normalized_question = question.strip()
        scope = assess_question_scope(normalized_question)
        if scope is not None:
            return _control_result(
                normalized_question,
                status=str(scope.get("status") or "unsupported"),
                reason=str(scope.get("reason") or "question is outside safe analytics scope"),
                limitations=scope.get("limitations"),
            )
        if is_simple_conversation(normalized_question):
            return _control_result(
                normalized_question,
                status="conversation",
                reason="conversation does not enter the analytics agent",
                conversation_bypassed=True,
            )
        return None

    def _unsupported(
        self, question: str, reason: str, *, tool_calls: int = 0
    ) -> dict[str, Any]:
        result = _control_result(
            question,
            status="unsupported",
            reason=reason,
        )
        result["tool_calls"] = tool_calls
        return result

    def _execute_query(
        self,
        compiled: CompiledAggregateQuery,
        *,
        tool_calls: int,
    ) -> tuple[QueryResultContract, int]:
        if tool_calls >= self.max_tool_calls:
            raise AgentToolLimitExceeded(
                f"analytics tool call limit reached: {self.max_tool_calls}"
            )
        execute = getattr(self.aggregate_repository, "execute", None)
        if not callable(execute):
            execute = getattr(self.aggregate_repository, "query", None)
        if not callable(execute):
            raise AnalyticsAgentError(
                "aggregate repository must expose execute or query"
            )
        next_tool_calls = tool_calls + 1
        result = execute(compiled)
        if not isinstance(result, QueryResultContract):
            raise AnalyticsAgentError(
                "aggregate repository must return QueryResultContract"
            )
        return result, next_tool_calls

    def run(self, question: str) -> dict[str, Any]:
        """Run one isolated analytics request; conversation never reaches planner."""

        gate_result = self._safe_question_gate(question)
        if gate_result is not None:
            return gate_result

        normalized_question = question.strip()
        tool_calls = 0
        try:
            planned = self.planner.generate_plan(normalized_question)
        except UnsupportedAnalyticsRequest as error:
            return self._unsupported(normalized_question, str(error))
        except (NotImplementedError, LookupError) as error:
            return self._unsupported(normalized_question, str(error) or "planner does not support this question")

        if planned is None:
            return self._unsupported(
                normalized_question,
                "planner did not produce a supported query plan",
            )

        try:
            validated_plan = self.validator.validate(_plan_document(planned))
            compiled_query = self.compiler.compile(validated_plan)
        except (QueryPlanValidationError, SafeQueryCompilerError) as error:
            return self._unsupported(normalized_question, str(error))

        try:
            query_result, tool_calls = self._execute_query(
                compiled_query,
                tool_calls=tool_calls,
            )
        except AgentToolLimitExceeded as error:
            return {
                **self._unsupported(normalized_question, str(error), tool_calls=tool_calls),
                "status": "tool_limit",
            }

        evidence = self.evidence_adapter.adapt(
            query_result,
            self.evidence_type,
            question=normalized_question,
        )
        status = "empty" if query_result.row_count == 0 else "ok"
        return {
            "status": status,
            "question": normalized_question,
            "answerable": query_result.row_count > 0,
            "query_executed": True,
            "tool_calls": tool_calls,
            "query_plan": validated_plan,
            "compiled_query": compiled_query,
            "query_result": query_result,
            "evidence": evidence,
            "provenance": dict(query_result.provenance),
        }

    def execute(self, question: str) -> dict[str, Any]:
        """Alias for callers that use execute terminology."""

        return self.run(question)


AnalyticsAgent = AnalyticsAgentOrchestrator


def run_analytics_agent(
    question: str,
    planner: PlannerProtocol,
    aggregate_repository: AggregateQueryProtocol,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run one request with an injected planner and aggregate repository."""

    return AnalyticsAgentOrchestrator(
        planner,
        aggregate_repository,
        **kwargs,
    ).run(question)


__all__ = [
    "AggregateQueryProtocol",
    "AnalyticsAgent",
    "AnalyticsAgentError",
    "AnalyticsAgentOrchestrator",
    "AgentToolLimitExceeded",
    "MAX_AGENT_TOOL_CALLS",
    "PlannerProtocol",
    "UnsupportedAnalyticsRequest",
    "run_analytics_agent",
]
