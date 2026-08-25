import json

from app.services.ai_assistant import DeepSeekChatClient


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_structured_schema_is_translated_to_deepseek_json_output(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeHTTPResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"version":"query_analytics-v1"}',
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("app.services.ai_assistant.urlopen", fake_urlopen)
    client = DeepSeekChatClient(
        "test-key", "https://example.test", "deepseek-v4-flash", 20
    )

    result = client.complete_structured(
        [{"role": "user", "content": "return JSON"}],
        {
            "type": "json_schema",
            "json_schema": {"name": "query", "strict": True, "schema": {}},
        },
    )

    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 4096
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert captured["timeout"] == 20
    assert result == {"parsed": {"version": "query_analytics-v1"}}


def test_structured_json_object_format_is_preserved(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeHTTPResponse(
            {
                "choices": [
                    {"message": {"content": '{"answer_text":"ok"}'}}
                ]
            }
        )

    monkeypatch.setattr("app.services.ai_assistant.urlopen", fake_urlopen)
    client = DeepSeekChatClient(
        "test-key", "https://example.test", "deepseek-v4-flash", 20
    )

    client.complete_structured(
        [{"role": "user", "content": "return JSON"}],
        {"type": "json_object"},
    )

    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["response_format"] == {"type": "json_object"}


def test_structured_thinking_can_be_disabled_for_legacy_models(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeHTTPResponse(
            {"choices": [{"message": {"content": '{"answer_text":"ok"}'}}]}
        )

    monkeypatch.setattr("app.services.ai_assistant.urlopen", fake_urlopen)
    client = DeepSeekChatClient(
        "test-key",
        "https://example.test",
        "deepseek-chat",
        20,
        thinking_mode="disabled",
    )

    client.complete_structured(
        [{"role": "user", "content": "return JSON"}],
        {"type": "json_object"},
    )

    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["temperature"] == 0.0
    assert "thinking" not in body
    assert "reasoning_effort" not in body
