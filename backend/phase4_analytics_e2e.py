"""Read-only Phase 4 Analytics Agent acceptance runner.

This runner deliberately uses a static planner and a deterministic structured
answer client.  It exercises the real classifier, validator, compiler,
MySQL aggregate repository, evidence adapter, answer grounding checks, and
SSE event contract without making a DeepSeek request.
"""

from __future__ import annotations

import json

from app import create_app
from app.services.ai_assistant import AIAssistantService, is_new_analytics_question
from app.services.analytics_agent import AnalyticsAgentOrchestrator
from app.services.evidence_answer_generator import EvidenceAnswerGenerator


DATA_VERSION = (
    "sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219"
)

QUESTIONS = (
    "\u54ea\u4e9b\u75be\u75c5\u75c5\u4f8b\u6570\u91cf\u6700\u591a\uff1f",
    "\u4e0d\u540c\u5e74\u9f84\u6bb5\u7684\u5e73\u5747\u4f4f\u9662\u65f6\u95f4\u662f\u591a\u5c11\uff1f",
    "Medicare \u60a3\u8005\u5e73\u5747\u8d39\u7528\u662f\u591a\u5c11\uff1f",
    "\u4e0d\u540c\u6027\u522b\u75be\u75c5\u5206\u5e03\u60c5\u51b5\uff1f",
)

PLANS = {
    QUESTIONS[0]: {
        "version": "query_analytics-v1",
        "dimensions": ["diagnosis"],
        "measures": ["case_count"],
        "filters": [],
        "sort": [{"by": "case_count", "direction": "desc"}],
        "limit": 10,
    },
    QUESTIONS[1]: {
        "version": "query_analytics-v1",
        "dimensions": ["age_group"],
        "measures": ["avg_los"],
        "filters": [],
        "sort": [{"by": "avg_los", "direction": "desc"}],
        "limit": 10,
    },
    QUESTIONS[2]: {
        "version": "query_analytics-v1",
        "dimensions": [],
        "measures": ["avg_charges"],
        "filters": [
            {"dimension": "payment", "operator": "eq", "value": "Medicare"}
        ],
        "sort": [],
        "limit": 1,
    },
    QUESTIONS[3]: {
        "version": "query_analytics-v1",
        "dimensions": ["gender", "diagnosis"],
        "measures": ["case_count"],
        "filters": [],
        "sort": [{"by": "case_count", "direction": "desc"}],
        "limit": 10,
    },
}


class StaticPlanner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_plan(self, question: str) -> dict:
        self.calls.append(question)
        return PLANS[question]


class RecordingRepository:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.queries = []
        self.results = []

    def execute(self, query):
        self.queries.append(query)
        result = self.delegate.execute(query)
        self.results.append(result)
        return result


class DeterministicAnswerClient:
    """Return a grounded structured answer without an external model call."""

    def complete_structured(self, messages, response_format):
        measure_labels = {
            "case_count": "Case count",
            "avg_los": "Average length of stay",
            "avg_charges": "Average charges",
            "avg_costs": "Average costs",
            "emergency_rate": "Emergency rate",
            "surgical_rate": "Surgical rate",
            "severe_rate": "Severe rate",
        }
        payload = json.loads(messages[1]["content"])
        envelope = payload["evidence"][0]
        evidence = envelope["evidence"]
        if evidence.get("metrics"):
            metric = evidence["metrics"][0]
            answer = f"{metric['label']}: {metric['value']}."
        else:
            section = evidence["sections"][0]
            item = section["items"][0]
            measures = evidence.get("query_plan", {}).get("measures", [])
            label = measure_labels.get(measures[0], "value") if measures else "value"
            answer = f"{item['name']}: {item['value']} ({label})."
        return {
            "parsed": {
                "answer_text": answer,
                "used_evidence_ids": [envelope["evidence_id"]],
            }
        }


def run() -> dict:
    app = create_app({"TESTING": True})
    planner = StaticPlanner()
    repository = RecordingRepository(app.extensions["aggregate_query_repository"])
    agent = AnalyticsAgentOrchestrator(
        planner,
        repository,
        diagnosis_label_resolver=app.extensions["diagnosis_label_catalog"],
    )
    answer_generator = EvidenceAnswerGenerator(DeterministicAnswerClient())
    service = AIAssistantService(
        app.extensions["analytics_snapshot_service"],
        object(),
        analytics_agent=agent,
        answer_generator=answer_generator,
    )

    records = []
    for question in QUESTIONS:
        before = len(repository.results)
        events = list(service.stream_chat({"message": question}))
        stages = [
            data["stage"]
            for event_type, data in events
            if event_type == "stage"
        ]
        answer = "".join(
            data["text"]
            for event_type, data in events
            if event_type == "delta"
        )
        done = events[-1][1]
        query_result = repository.results[-1] if len(repository.results) > before else None
        compiled_query = repository.queries[-1] if len(repository.queries) > before else None
        evidence = done["sources"][0] if done["sources"] else None
        records.append(
            {
                "question": question,
                "route": (
                    "analytics_agent"
                    if is_new_analytics_question(question)
                    else "other"
                ),
                "planner_called": question in planner.calls,
                "query_plan": PLANS[question],
                "compiled_query": (
                    compiled_query.to_document()
                    if compiled_query is not None
                    else None
                ),
                "query_result": (
                    query_result.to_document() if query_result is not None else None
                ),
                "status": "success" if done["sources"] else "safe_refusal",
                "answer": answer,
                "evidence": evidence,
                "provenance": (
                    evidence.get("provenance") if evidence is not None else None
                ),
                "chart": evidence.get("chart") if evidence is not None else None,
                "sse": {
                    "event_types": [event_type for event_type, _ in events],
                    "stages": stages,
                    "done": events[-1][0] == "done",
                    "internal_details_exposed": any(
                        token in json.dumps(events, ensure_ascii=False).lower()
                        for token in ("sql", "planner reasoning", "query_plan")
                    ),
                },
            }
        )

    return {
        "mysql_read_timeout": app.config["MYSQL_READ_TIMEOUT"],
        "aggregate_repository": type(
            app.extensions["aggregate_query_repository"]
        ).__name__,
        "data_version": DATA_VERSION,
        "cases": records,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
