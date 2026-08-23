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
