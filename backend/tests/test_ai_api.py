from __future__ import annotations

import json
from uuid import UUID
from urllib.error import HTTPError, URLError

import pytest

import app.services.ai_assistant as ai_assistant_module
from app import create_app
from app.services.ai_assistant import DeepSeekChatClient


FIXTURE_VERSION = "fixture:sparcs_full_analytics:v1"


def tool_call(name: str = "get_dashboard_overview", arguments: str = "{}", call_id: str = "call-1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


class ScriptedAIClient:
    def __init__(self, first=None, final=None):
        self.calls = 0
        self.messages = []
        self.first = first or {"role": "assistant", "content": None, "tool_calls": [tool_call()]}
        self.final = final or {
            "role": "assistant",
            "content": "基于 get_dashboard_overview 的已验证汇总，当前整体运营指标已完成分析。",
        }

    def complete(self, messages, tools=None):
        self.calls += 1
        self.messages.append(messages)
        return self.first if self.calls == 1 else self.final


class RaisingAIClient:
    def __init__(self, error):
        self.error = error

    def complete(self, messages, tools=None):
        raise self.error


class EmptyFinalAIClient(ScriptedAIClient):
    def __init__(self):
        super().__init__(final={"role": "assistant", "content": ""})


class NoToolCallAIClient:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        return {"role": "assistant", "content": "router returned no tool call"}


class ConversationAIClient:
    def __init__(self):
        self.calls = 0
        self.messages = []
        self.tools = []

    def complete(self, messages, tools=None):
        self.calls += 1
        self.messages.append(messages)
        self.tools.append(tools)
        return {
            "role": "assistant",
            "content": "你好！我是医数云策的 AI 医疗运营分析助手。",
        }


class StreamConversationAIClient(ConversationAIClient):
    def stream_complete(self, messages, tools=None):
        yield "你好！我是医数云策的 "
        yield "AI 医疗运营分析助手。"


class StreamAnalyticsAIClient(ScriptedAIClient):
    def stream_complete(self, messages, tools=None):
        yield "基于 "
        yield "get_dashboard_overview 的已验证汇总，已完成回答。"


class StreamFailureAIClient:
    def stream_complete(self, messages, tools=None):
        raise TimeoutError("secret upstream response and API key")


class BrokenAnalyticsRepository:
    def fetch(self, module_key, entity_key):
        raise RuntimeError("database password and prompt must stay private")


def build_app(ai_client=None, api_key=None, **kwargs):
    return create_app(
        {
            "TESTING": True,
            "TOP10_DATA_SOURCE": "fixture",
            "ANALYTICS_DATA_SOURCE": "fixture",
            "HIGH_COST_MODEL_PATH": None,
            "DEEPSEEK_API_KEY": api_key,
        },
        ai_client=ai_client,
        **kwargs,
    )


def assert_trace(response):
    body = response.get_json()
    assert body["trace_id"] == response.headers["X-Trace-ID"]
    UUID(body["trace_id"])
    return body


def assert_safe_error(response, status_code, code, *markers):
    assert response.status_code == status_code
    body = assert_trace(response)
    assert body["code"] == code
    assert body["data"] is None
    text = response.get_data(as_text=True)
    assert "Traceback" not in text
    for marker in markers:
        assert marker not in text
    return body


def parse_sse(response):
    events = []
    for block in response.get_data(as_text=True).strip().split("\n\n"):
        lines = block.splitlines()
        event_type = next(line.split(":", 1)[1].strip() for line in lines if line.startswith("event:"))
        data_line = next(line.split(":", 1)[1].strip() for line in lines if line.startswith("data:"))
        events.append((event_type, json.loads(data_line)))
    return events


def test_chat_success_has_stable_traceable_contract_and_analysis_evidence():
    ai_client = ScriptedAIClient()
    question = "概括当前运营情况"
    response = build_app(ai_client=ai_client).test_client().post(
        "/api/v1/ai/chat",
        json={"message": f"  {question}  "},
    )

    assert response.status_code == 200
    body = assert_trace(response)
    assert set(body) == {"code", "message", "data", "trace_id"}
    assert body["code"] == "OK"
    data = body["data"]
    assert set(data) == {
        "answer",
        "tool_trace",
        "sources",
        "data_versions",
        "chart",
        "report",
        "boundary",
    }
    assert data["answer"]
    assert data["data_versions"] == [FIXTURE_VERSION]
    assert data["tool_trace"] == [
        {
            "tool": "get_dashboard_overview",
            "status": "success",
            "data_version": FIXTURE_VERSION,
        }
    ]
    source = data["sources"][0]
    assert {"tool", "title", "metrics", "data_version"}.issubset(source)
    assert source["sections"]
    assert source["insights"] is not None
    assert source["derived_facts"] is not None
    assert source["data_version"] == FIXTURE_VERSION
    assert data["chart"]["type"] in {"bar", "pie", "table", "status"}
    assert data["report"] == {"title": "医数云策洞察简报", "printable": True}
    assert data["boundary"]
    assert ai_client.messages[0][1]["content"] == question

    analysis_messages = ai_client.messages[1]
    assert analysis_messages[1] == {"role": "user", "content": question}
    evidence = json.loads(next(item for item in analysis_messages if item["role"] == "tool")["content"])
    assert evidence["data_version"] == FIXTURE_VERSION
    assert evidence["sections"]
    assert evidence["derived_facts"]
    context = json.loads(analysis_messages[-1]["content"])
    assert context["answerability"]["status"] == "answerable"


@pytest.mark.parametrize(
    "kind,expected_code",
    [
        ("non-json", "INVALID_REQUEST_FORMAT"),
        ("missing", "INVALID_REQUEST_FIELD"),
        ("extra", "INVALID_REQUEST_FIELD"),
        ("empty", "INVALID_REQUEST_FIELD"),
        ("too-long", "INVALID_REQUEST_FIELD"),
    ],
)
def test_chat_rejects_invalid_request_shapes(kind, expected_code):
    client = build_app(ai_client=ScriptedAIClient()).test_client()
    if kind == "non-json":
        response = client.post(
            "/api/v1/ai/chat",
            data="not-json TOP_SECRET_PROMPT",
            content_type="text/plain",
        )
    else:
        payloads = {
            "missing": {},
            "extra": {"message": "safe", "prompt": "TOP_SECRET_PROMPT"},
            "empty": {"message": " \t\n"},
            "too-long": {"message": "x" * 1001},
        }
        response = client.post("/api/v1/ai/chat", json=payloads[kind])

    body = assert_safe_error(response, 400, expected_code, "TOP_SECRET_PROMPT", "not-json")
    assert body["message"]


@pytest.mark.parametrize("method", ["get", "put", "patch", "delete", "options", "head"])
def test_chat_is_post_only(method):
    client = build_app(ai_client=ScriptedAIClient()).test_client()
    response = getattr(client, method)("/api/v1/ai/chat")
    assert response.status_code == 405
    if method != "head":
        assert_trace(response)["code"] == "METHOD_NOT_ALLOWED"


def test_chat_without_key_returns_safe_configuration_error():
    response = build_app().test_client().post(
        "/api/v1/ai/chat",
        json={"message": "概括运营情况 TOP_SECRET_PROMPT"},
    )
    assert_safe_error(response, 500, "SERVER_MISCONFIGURED", "TOP_SECRET_PROMPT", "Authorization")


def make_timeout():
    return TimeoutError("secret-key prompt timeout")


def make_http_error():
    return HTTPError(
        url="https://api.deepseek.com/chat/completions",
        code=502,
        msg="secret-key prompt upstream failure",
        hdrs=None,
        fp=None,
    )


def make_network_error():
    return URLError("secret-key prompt network failure")


def make_connection_reset():
    return ConnectionResetError("secret-key prompt connection reset")


@pytest.mark.parametrize(
    "error_factory",
    [make_timeout, make_http_error, make_network_error, make_connection_reset],
    ids=["timeout", "http", "network", "connection-reset"],
)
def test_real_client_failures_return_redacted_upstream_error(monkeypatch, error_factory):
    error = error_factory()
    monkeypatch.setattr(ai_assistant_module, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    ai_client = DeepSeekChatClient(
        api_key="secret-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout=20,
    )
    response = build_app(ai_client=ai_client).test_client().post(
        "/api/v1/ai/chat",
        json={"message": "当前整体运营情况 TOP_SECRET_PROMPT"},
    )
    assert_safe_error(response, 503, "UPSTREAM_SERVICE_ERROR", "secret-key", "TOP_SECRET_PROMPT", "Authorization")


def test_empty_final_answer_returns_upstream_error():
    response = build_app(ai_client=EmptyFinalAIClient()).test_client().post(
        "/api/v1/ai/chat",
        json={"message": "概括运营情况"},
    )
    assert_safe_error(response, 503, "UPSTREAM_SERVICE_ERROR")


def test_unsupported_question_without_tool_call_returns_controlled_api_response():
    ai_client = NoToolCallAIClient()
    response = build_app(ai_client=ai_client).test_client().post(
        "/api/v1/ai/chat",
        json={"message": "今年费用比去年上涨了吗？"},
    )

    assert response.status_code == 200
    data = assert_trace(response)["data"]
    assert data["answer"]
    assert data["tool_trace"] == []
    assert data["sources"] == []
    assert data["data_versions"] == []
    assert data["chart"] is None
    assert data["boundary"]
    assert ai_client.calls == 0


def test_simple_conversation_returns_empty_evidence_contract():
    ai_client = ConversationAIClient()
    response = build_app(ai_client=ai_client).test_client().post(
        "/api/v1/ai/chat",
        json={"message": "你好"},
    )

    assert response.status_code == 200
    data = assert_trace(response)["data"]
    assert set(data) == {
        "answer",
        "tool_trace",
        "sources",
        "data_versions",
        "chart",
        "report",
        "boundary",
    }
    assert data["answer"]
    assert data["tool_trace"] == []
    assert data["sources"] == []
    assert data["data_versions"] == []
    assert data["chart"] is None
    assert data["boundary"]
    assert ai_client.calls == 1
    assert ai_client.tools == [None]


def test_stream_conversation_returns_sse_stages_deltas_and_empty_evidence():
    response = build_app(ai_client=StreamConversationAIClient()).test_client().post(
        "/api/v1/ai/chat/stream",
        json={"message": "你好"},
    )

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["X-Accel-Buffering"] == "no"
    events = parse_sse(response)
    assert [event_type for event_type, _ in events] == [
        "stage",
        "stage",
        "stage",
        "delta",
        "delta",
        "done",
    ]
    assert [data["stage"] for event_type, data in events if event_type == "stage"] == [
        "preparing",
        "understanding",
        "generation",
    ]
    assert "".join(data["text"] for event_type, data in events if event_type == "delta") == (
        "你好！我是医数云策的 AI 医疗运营分析助手。"
    )
    done = events[-1][1]
    assert "answer" not in done
    assert done["sources"] == []
    assert done["data_versions"] == []
    assert done["chart"] is None


def test_stream_analytics_returns_provenance_metadata_after_analysis_deltas():
    response = build_app(ai_client=StreamAnalyticsAIClient()).test_client().post(
        "/api/v1/ai/chat/stream",
        json={"message": "概括当前运营情况"},
    )

    assert response.status_code == 200
    events = parse_sse(response)
    assert [data["stage"] for event_type, data in events if event_type == "stage"] == [
        "preparing",
        "understanding",
        "routing",
        "evidence",
        "analysis",
        "generation",
    ]
    done = events[-1][1]
    assert events[-1][0] == "done"
    assert "answer" not in done
    assert done["tool_trace"][0]["tool"] == "get_dashboard_overview"
    assert done["sources"][0]["data_version"] == FIXTURE_VERSION
    assert done["data_versions"] == [FIXTURE_VERSION]
    assert done["chart"]


def test_stream_upstream_failure_is_sanitized():
    response = build_app(ai_client=StreamFailureAIClient()).test_client().post(
        "/api/v1/ai/chat/stream",
        json={"message": "你好"},
    )

    assert response.status_code == 200
    events = parse_sse(response)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "UPSTREAM_SERVICE_ERROR"
    text = response.get_data(as_text=True)
    assert "secret upstream response" not in text
    assert "API key" not in text


def test_stream_analytics_without_tool_call_returns_sanitized_error():
    response = build_app(ai_client=NoToolCallAIClient()).test_client().post(
        "/api/v1/ai/chat/stream",
        json={"message": "当前整体运营怎么样？"},
    )

    assert response.status_code == 200
    events = parse_sse(response)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "UPSTREAM_SERVICE_ERROR"
    assert events[-1][1]["message"] == "The AI answer did not use a verified analytics tool."


def test_tool_dependency_failure_is_not_exposed():
    response = build_app(
        ai_client=ScriptedAIClient(),
        analytics_repository=BrokenAnalyticsRepository(),
    ).test_client().post(
        "/api/v1/ai/chat",
        json={"message": "概括运营情况"},
    )
    assert_safe_error(
        response,
        503,
        "UPSTREAM_SERVICE_ERROR",
        "database password",
        "prompt",
        "Traceback",
    )
