from __future__ import annotations

from app.services.analytics_agent import (
    AnalyticsAgentOrchestrator,
    UnsupportedAnalyticsRequest,
)
from shared.query_result_contract import QueryResultContract


PROVENANCE = {
    "batch_id": "agg-test",
    "data_version": "fixture:aggregate:v1",
    "formula_version": "aggregate-additive-v1",
    "registry_version": "aggregate-registry-v1",
}
METADATA = {
    "source": "analytics_aggregate_fact",
    "generated_at": "2026-08-25T00:00:00Z",
    "privacy_boundary": "aggregate_only",
}


def plan_document():
    return {
        "version": "query_analytics-v1",
        "dimensions": ["hospital"],
        "measures": ["case_count"],
        "filters": [],
        "sort": [{"by": "case_count", "direction": "desc"}],
        "limit": 4,
    }


def result_document(rows):
    plan = plan_document()
    return QueryResultContract(
        query_id="query-agent-test",
        query_plan=plan,
        dimensions=("hospital",),
        measures=("case_count",),
        filters=(),
        rows=tuple(rows),
        row_count=len(rows),
        truncated=False,
        provenance=PROVENANCE,
        metadata=METADATA,
    )


class FakePlanner:
    def __init__(self, plan=None, error=None):
        self.plan = plan if plan is not None else plan_document()
        self.error = error
        self.questions = []

    def generate_plan(self, question):
        self.questions.append(question)
        if self.error is not None:
            raise self.error
        return self.plan


class FakeAggregateRepository:
    def __init__(self, result):
        self.result = result
        self.queries = []

    def execute(self, query):
        self.queries.append(query)
        return self.result


def make_agent(planner=None, repository=None, **kwargs):
    planner = planner or FakePlanner()
    repository = repository or FakeAggregateRepository(
        result_document(
            [
                {"hospital": "Hospital A", "case_count": 20},
                {"hospital": "Hospital B", "case_count": 10},
            ]
        )
    )
    return AnalyticsAgentOrchestrator(
        planner,
        repository,
        **kwargs,
    ), planner, repository


def test_normal_analytics_flow_runs_pipeline_once():
    agent, planner, repository = make_agent()

    result = agent.run("Which hospitals have the highest case count?")

    assert result["status"] == "ok"
    assert result["query_executed"] is True
    assert result["tool_calls"] == 1
    assert len(planner.questions) == 1
    assert len(repository.queries) == 1
    assert result["evidence"]["sections"]


def test_unsupported_question_returns_safe_result_without_query():
    agent, planner, repository = make_agent()

    result = agent.run("今年费用比去年上涨了吗？")

    assert result["status"] == "unsupported"
    assert result["query_executed"] is False
    assert result["query_result"] is None
    assert planner.questions == []
    assert repository.queries == []


def test_empty_result_is_returned_without_fabricated_evidence():
    planner = FakePlanner()
    repository = FakeAggregateRepository(result_document([]))
    agent = AnalyticsAgentOrchestrator(planner, repository)

    result = agent.run("Show hospital case counts")

    assert result["status"] == "empty"
    assert result["query_result"].row_count == 0
    assert result["evidence"]["sections"][0]["items"] == []
    assert result["evidence"]["chart"] is None


def test_tool_call_limit_blocks_repository_execution():
    agent, planner, repository = make_agent(max_tool_calls=0)

    result = agent.run("Show hospital case counts")

    assert result["status"] == "tool_limit"
    assert result["tool_calls"] == 0
    assert planner.questions == ["Show hospital case counts"]
    assert repository.queries == []


def test_provenance_is_preserved_end_to_end():
    agent, _, _ = make_agent()

    result = agent.run("Show hospital case counts")

    assert result["provenance"] == PROVENANCE
    assert result["query_result"].provenance == PROVENANCE
    assert result["evidence"]["provenance"] == PROVENANCE


def test_distribution_intent_selects_distribution_evidence_projection():
    agent, _, _ = make_agent()

    result = agent.run("不同性别疾病分布")

    assert result["evidence_type"] == "distribution"
    assert result["evidence"]["sections"][0]["type"] == "pie"


def test_conversation_bypasses_planner_and_repository():
    agent, planner, repository = make_agent()

    result = agent.run("hello")

    assert result["status"] == "conversation"
    assert result["conversation_bypassed"] is True
    assert result["query_executed"] is False
    assert planner.questions == []
    assert repository.queries == []


def test_unsafe_question_bypasses_query():
    agent, planner, repository = make_agent()

    result = agent.run("这个病人应该接受什么治疗？")

    assert result["status"] == "unsafe"
    assert result["query_executed"] is False
    assert planner.questions == []
    assert repository.queries == []


def test_individual_patient_aggregate_question_bypasses_query():
    agent, planner, repository = make_agent()

    result = agent.run("\u67d0\u60a3\u8005\u8d39\u7528\u662f\u591a\u5c11\uff1f")

    assert result["status"] == "unsafe"
    assert result["query_executed"] is False
    assert planner.questions == []
    assert repository.queries == []


def test_planner_can_return_explicit_unsupported_request():
    agent, planner, repository = make_agent(
        planner=FakePlanner(error=UnsupportedAnalyticsRequest("not supported"))
    )

    result = agent.run("an unsupported analytics request")

    assert result["status"] == "unsupported"
    assert result["reason"] == "not supported"
    assert repository.queries == []
