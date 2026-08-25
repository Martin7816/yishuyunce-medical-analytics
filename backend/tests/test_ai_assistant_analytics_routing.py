from __future__ import annotations

import json
from pathlib import Path

from app import create_app
from app.services.ai_assistant import AIAssistantService, is_new_analytics_question
from app.services.analytics_snapshot import AnalyticsSnapshotService
from app.services.evidence_answer_generator import (
    AnswerResult,
    EvidenceAnswerOutputError,
)
from app.repositories.analytics_snapshot import FixtureAnalyticsSnapshotRepository


PROVENANCE = {
    "batch_id": "agg-routing-test",
    "data_version": "fixture:aggregate:routing-v1",
    "formula_version": "aggregate-additive-v1",
    "registry_version": "analytics-semantic-v1",
}

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "fixtures"
    / "analytics_snapshot_success.json"
)


def tool_call():
    return {
        "id": "legacy-call-1",
        "type": "function",
        "function": {
            "name": "get_dashboard_overview",
            "arguments": "{}",
        },
    }


def safe_evidence():
    return {
        "query_id": "query-routing-1",
        "title": "Hospital ranking",
        "description": "Validated aggregate case counts.",
        "data_version": PROVENANCE["data_version"],
        "metrics": [],
        "sections": [
            {
                "key": "hospital_ranking",
                "title": "Hospital ranking",
                "type": "bar",
                "items": [{"name": "Hospital A", "value": 50}],
            }
        ],
        "facts": [],
        "derived_facts": [],
        "provenance": PROVENANCE,
        "chart": None,
    }


class LegacyClient:
    def __init__(self):
        self.complete_calls = []
        self.stream_calls = []

    def complete(self, messages, tools=None):
        self.complete_calls.append((messages, tools))
        if tools:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call()]}
        return {"role": "assistant", "content": "Hello from the legacy conversation path."}

    def stream_complete(self, messages, tools=None):
        self.stream_calls.append((messages, tools))
        yield "legacy stream answer"


class FakeAnalyticsAgent:
    def __init__(self, result=None):
        self.result = result or {
            "status": "ok",
            "evidence": safe_evidence(),
            "provenance": PROVENANCE,
        }
        self.questions = []
        self.evidence_type = "ranking"

    def run(self, question):
        self.questions.append(question)
        return self.result


class FakeAnswerGenerator:
    def __init__(self):
        self.calls = []

    def generate(self, question, evidence):
        self.calls.append((question, evidence))
        return AnswerResult(
            status="ok",
            answer_text="Hospital A has 50 cases.",
            used_evidence_ids=("query-routing-1",),
            provenance=PROVENANCE,
        )


class FailingAnswerGenerator(FakeAnswerGenerator):
    def generate(self, question, evidence):
        raise EvidenceAnswerOutputError("provider unavailable")

    def deterministic_fallback(self, question, evidence):
        return AnswerResult(
            status="ok",
            answer_text="根据已核验的汇总数据：Hospital A: 50。",
            used_evidence_ids=("query-routing-1",),
            provenance=PROVENANCE,
        )


def make_service(client, agent=None, answer_generator=None):
    analytics = AnalyticsSnapshotService(FixtureAnalyticsSnapshotRepository(FIXTURE_PATH))
    return AIAssistantService(
        analytics,
        client,
        analytics_agent=agent,
        answer_generator=answer_generator,
    )


def parse_sse(response):
    events = []
    for block in response.get_data(as_text=True).strip().split("\n\n"):
        lines = block.splitlines()
        event_type = next(
            line.split(":", 1)[1].strip()
            for line in lines
            if line.startswith("event:")
        )
        data = next(
            json.loads(line.split(":", 1)[1].strip())
            for line in lines
            if line.startswith("data:")
        )
        events.append((event_type, data))
    return events


def test_new_semantic_query_is_classified_without_matching_legacy_overview():
    assert is_new_analytics_question("Show case_count by hospital and severity") is True
    assert is_new_analytics_question("Summarize current operations") is False


def test_chinese_aggregate_intents_route_to_new_analytics_agent():
    questions = (
        "哪些疾病病例最多？",
        "哪些诊断数量最高？",
        "不同年龄段平均住院时间？",
        "Medicare平均费用？",
        "不同性别疾病分布？",
        "不同年龄段病例情况？",
    )

    assert all(is_new_analytics_question(question) for question in questions)


def test_filtered_chinese_disease_question_enters_new_agent():
    assert is_new_analytics_question("50岁男性最容易得什么病") is True


def test_patient_cohort_aggregate_intents_route_but_individual_patient_does_not():
    assert is_new_analytics_question(
        "Medicare\u60a3\u8005\u5e73\u5747\u8d39\u7528\u662f\u591a\u5c11\uff1f"
    ) is True
    assert is_new_analytics_question("\u60a3\u8005\u6570\u91cf\u662f\u591a\u5c11\uff1f") is True
    assert is_new_analytics_question("\u60a3\u8005\u5206\u5e03\u60c5\u51b5\uff1f") is True
    assert is_new_analytics_question("\u67d0\u60a3\u8005\u8d39\u7528\u662f\u591a\u5c11\uff1f") is False


def test_hospital_case_count_natural_language_enters_generic_agent():
    assert is_new_analytics_question("哪些医院病例量最高？") is True


def test_conversation_bypasses_analytics_agent():
    client = LegacyClient()
    agent = FakeAnalyticsAgent()
    answer_generator = FakeAnswerGenerator()

    result = make_service(client, agent, answer_generator).chat({"message": "hello"})

    assert result["answer"] == "Hello from the legacy conversation path."
    assert agent.questions == []
    assert answer_generator.calls == []
    assert client.complete_calls[0][1] is None


def test_new_analytics_question_uses_agent_and_answer_generator():
    client = LegacyClient()
    agent = FakeAnalyticsAgent()
    answer_generator = FakeAnswerGenerator()

    result = make_service(client, agent, answer_generator).chat(
        {"message": "Show case_count by hospital and severity"}
    )

    assert result["answer"] == "Hospital A has 50 cases."
    assert agent.questions == ["Show case_count by hospital and severity"]
    assert len(answer_generator.calls) == 1
    assert client.complete_calls == []
    assert result["tool_trace"] == [
        {
            "tool": "query_analytics",
            "status": "success",
            "data_version": PROVENANCE["data_version"],
        }
    ]
    assert result["sources"][0]["provenance"] == PROVENANCE
    assert "query_plan" not in result["sources"][0]


def test_model_answer_failure_uses_evidence_only_fallback():
    client = LegacyClient()
    agent = FakeAnalyticsAgent()
    answer_generator = FailingAnswerGenerator()

    result = make_service(client, agent, answer_generator).chat(
        {"message": "Show case_count by hospital and severity"}
    )

    assert result["answer"] == "根据已核验的汇总数据：Hospital A: 50。"
    assert result["data_versions"] == [PROVENANCE["data_version"]]
    assert client.complete_calls == []


def test_legacy_supported_question_keeps_old_tool_path():
    client = LegacyClient()
    agent = FakeAnalyticsAgent()
    answer_generator = FakeAnswerGenerator()

    result = make_service(client, agent, answer_generator).chat(
        {"message": "Summarize current operations"}
    )

    assert result["tool_trace"][0]["tool"] == "get_dashboard_overview"
    assert len(client.complete_calls) == 2
    assert client.complete_calls[0][1]
    assert agent.questions == []
    assert answer_generator.calls == []


def test_new_analytics_sse_keeps_stage_delta_done_shape_and_hides_internal_details():
    client = LegacyClient()
    agent = FakeAnalyticsAgent()
    answer_generator = FakeAnswerGenerator()
    app = create_app(
        {"TESTING": True, "ANALYTICS_DATA_SOURCE": "fixture"},
        ai_client=client,
        analytics_agent=agent,
        answer_generator=answer_generator,
    )

    response = app.test_client().post(
        "/api/v1/ai/chat/stream",
        json={"message": "Show case_count by hospital and severity"},
    )

    assert response.status_code == 200
    events = parse_sse(response)
    assert [event_type for event_type, _ in events].count("done") == 1
    assert [event_type for event_type, _ in events if event_type not in {"stage", "delta", "done"}] == []
    stages = [data["stage"] for event_type, data in events if event_type == "stage"]
    assert stages == ["preparing", "understanding", "querying", "analyzing", "completed"]
    assert "Hospital A has 50 cases." in "".join(
        data["text"] for event_type, data in events if event_type == "delta"
    )
    done = events[-1][1]
    assert done["data_versions"] == [PROVENANCE["data_version"]]
    assert "query_plan" not in done["sources"][0]
    assert "planner" not in response.get_data(as_text=True).lower()
    assert "sql" not in response.get_data(as_text=True).lower()


def test_unsupported_agent_result_is_safe_and_does_not_expose_reason():
    client = LegacyClient()
    agent = FakeAnalyticsAgent(
        {
            "status": "unsupported",
            "reason": "forbidden SQL planner validation details",
            "evidence": None,
        }
    )
    answer_generator = FakeAnswerGenerator()

    result = make_service(client, agent, answer_generator).chat(
        {"message": "Show case_count by hospital and severity"}
    )

    assert result["answer"]
    assert result["sources"] == []
    assert result["data_versions"] == []
    assert "SQL" not in result["answer"]
    assert "forbidden" not in result["answer"]
    assert answer_generator.calls == []
    assert client.complete_calls == []
