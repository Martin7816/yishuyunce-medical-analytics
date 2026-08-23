from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.errors import ServerMisconfiguredError, UpstreamServiceError

import app.services.ai_assistant as ai_assistant_module
from app.repositories.analytics_snapshot import FixtureAnalyticsSnapshotRepository
from app.services.ai_assistant import (
    ANALYSIS_SYSTEM_PROMPT,
    AIAssistantService,
    ROUTING_SYSTEM_PROMPT,
    TOOL_TO_SNAPSHOT,
    DeepSeekChatClient,
    tool_definitions,
)
from app.services.ai_evidence import (
    assess_answerability,
    assess_question_scope,
    build_safe_evidence,
)
from app.services.analytics_snapshot import AnalyticsSnapshotService


EXPECTED_TOOLS = {
    "get_dashboard_overview",
    "get_hospital_overview",
    "get_disease_overview",
    "get_cohort_summary",
    "get_cost_overview",
    "get_risk_overview",
    "get_payment_overview",
    "get_model_metrics",
}

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "fixtures"
    / "analytics_snapshot_success.json"
)


def tool_call(name: str = "get_dashboard_overview", call_id: str = "call-1", arguments: str = "{}"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


class FakeAIClient:
    def __init__(self, first_tool: str = "get_dashboard_overview", final: str | None = None):
        self.calls = 0
        self.messages: list[list[dict]] = []
        self.tools: list[list[dict] | None] = []
        self.first_tool = first_tool
        self.final = final or "基于 get_dashboard_overview 的已验证汇总，当前运营指标已完成分析。"

    def complete(self, messages, tools=None):
        self.calls += 1
        self.messages.append(messages)
        self.tools.append(tools)
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [tool_call(self.first_tool)],
            }
        return {"role": "assistant", "content": self.final}


def build_service(client):
    repository = FixtureAnalyticsSnapshotRepository(FIXTURE_PATH)
    analytics = AnalyticsSnapshotService(repository)
    return AIAssistantService(analytics, client)


def test_tool_definitions_are_strict_and_semantically_distinct():
    definitions = tool_definitions()

    assert len(definitions) == 8
    assert set(TOOL_TO_SNAPSHOT) == EXPECTED_TOOLS
    names = {item["function"]["name"] for item in definitions}
    descriptions = [item["function"]["description"] for item in definitions]
    assert names == EXPECTED_TOOLS
    assert len(set(descriptions)) == 8

    for item in definitions:
        function = item["function"]
        parameters = function["parameters"]
        assert "用于" in function["description"]
        assert "不接受参数" in function["description"]
        assert parameters == {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }


def test_single_tool_call_returns_traceable_source_and_safe_sections():
    client = FakeAIClient()
    result = build_service(client).chat({"message": "当前整体运营怎么样？"})

    assert client.calls == 2
    assert result["answer"]
    assert result["tool_trace"] == [
        {
            "tool": "get_dashboard_overview",
            "status": "success",
            "data_version": "fixture:sparcs_full_analytics:v1",
        }
    ]
    source = result["sources"][0]
    assert source["tool"] == "get_dashboard_overview"
    assert source["metrics"]
    assert source["sections"]
    assert "insights" in source
    assert "derived_facts" in source
    assert source["boundary"]
    assert source["answerability"]["status"] == "answerable"
    assert result["data_versions"] == ["fixture:sparcs_full_analytics:v1"]


class NoToolCallAIClient:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {"role": "assistant", "content": "我无法确定工具。"}
        return {"role": "assistant", "content": "当前数据不能支持该判断。"}


@pytest.mark.parametrize(
    "question",
    ["当前整体运营怎么样？", "医院病例量和费用有什么关系？"],
)
def test_zero_tool_calls_are_rejected_for_answerable_or_partial_question(question):
    with pytest.raises(UpstreamServiceError, match="did not use a verified analytics tool"):
        build_service(NoToolCallAIClient()).chat({"message": question})


@pytest.mark.parametrize(
    "question",
    [
        "今年费用比去年上涨了吗？",
        "这个病人应该接受什么治疗？",
    ],
)
def test_unsupported_or_unsafe_question_returns_controlled_answer_without_tool(question):
    client = NoToolCallAIClient()
    result = build_service(client).chat({"message": question})

    assert client.calls == 0
    assert result["answer"]
    assert result["tool_trace"] == []
    assert result["sources"] == []
    assert result["data_versions"] == []
    assert result["chart"] is None
    assert result["boundary"]


class TooManyToolCallsAIClient:
    def complete(self, messages, tools=None):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                tool_call("get_dashboard_overview", "call-1"),
                tool_call("get_cost_overview", "call-2"),
                tool_call("get_risk_overview", "call-3"),
            ],
        }


def test_more_than_two_tool_calls_are_rejected():
    with pytest.raises(UpstreamServiceError, match="exceeded the two-tool-call limit"):
        build_service(TooManyToolCallsAIClient()).chat({"message": "综合分析运营、成本和风险"})


class UnknownToolAIClient:
    def complete(self, messages, tools=None):
        return {"role": "assistant", "content": None, "tool_calls": [tool_call("run_sql")]}


def test_unknown_tool_is_rejected():
    with pytest.raises(UpstreamServiceError, match="non-whitelisted tool"):
        build_service(UnknownToolAIClient()).chat({"message": "请查询当前整体运营情况"})


@pytest.mark.parametrize(
    "arguments, message",
    [('{"sql": "select * from patients"}', "unsupported tool arguments"), ("{not-valid-json", "invalid tool arguments"), ("[]", "unsupported tool arguments")],
)
def test_tool_arguments_must_be_empty_json_object(arguments, message):
    class InvalidArgumentsClient:
        def complete(self, messages, tools=None):
            return {"role": "assistant", "content": None, "tool_calls": [tool_call(arguments=arguments)]}

    with pytest.raises(UpstreamServiceError, match=message):
        build_service(InvalidArgumentsClient()).chat({"message": "请查询运营情况"})


class EmptyAnswerAIClient:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call()]}
        return {"role": "assistant", "content": ""}


def test_empty_final_answer_is_rejected():
    with pytest.raises(UpstreamServiceError, match="empty answer"):
        build_service(EmptyAnswerAIClient()).chat({"message": "概括运营情况"})


class SelectedToolAIClient(FakeAIClient):
    pass


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
def test_every_whitelisted_tool_can_be_executed(tool_name):
    result = build_service(SelectedToolAIClient(tool_name)).chat({"message": "当前整体运营怎么样？"})
    assert result["tool_trace"][0]["tool"] == tool_name
    assert result["sources"][0]["tool"] == tool_name
    assert result["sources"][0]["metrics"]
    assert result["data_versions"] == ["fixture:sparcs_full_analytics:v1"]


def test_two_whitelisted_tools_can_be_combined():
    class TwoToolClient(FakeAIClient):
        def complete(self, messages, tools=None):
            self.calls += 1
            self.messages.append(messages)
            self.tools.append(tools)
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        tool_call("get_dashboard_overview", "call-1"),
                        tool_call("get_cost_overview", "call-2"),
                    ],
                }
            return {
                "role": "assistant",
                "content": "基于 get_dashboard_overview 和 get_cost_overview 的汇总，费用指标已完成比较。",
            }

    result = build_service(TwoToolClient()).chat({"message": "结合整体运营和费用分析"})
    assert [item["tool"] for item in result["tool_trace"]] == [
        "get_dashboard_overview",
        "get_cost_overview",
    ]
    assert len(result["sources"]) == 2
    assert result["data_versions"] == ["fixture:sparcs_full_analytics:v1"]


class QuestionAwareRoutingClient:
    def __init__(self):
        self.calls = 0
        self.messages: list[list[dict]] = []

    def complete(self, messages, tools=None):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            question = messages[-1]["content"]
            if "医院" in question:
                name = "get_hospital_overview"
            elif "疾病" in question:
                name = "get_disease_overview"
            elif "支付" in question:
                name = "get_payment_overview"
            else:
                name = "get_dashboard_overview"
            return {"role": "assistant", "content": None, "tool_calls": [tool_call(name)]}
        name = messages[2]["tool_calls"][0]["function"]["name"]
        return {"role": "assistant", "content": f"基于 {name} 的证据，已完成回答。"}


@pytest.mark.parametrize(
    "question, expected_tool",
    [
        ("哪些医院病例量最高？", "get_hospital_overview"),
        ("疾病结构有什么特点？", "get_disease_overview"),
        ("支付方式结构如何？", "get_payment_overview"),
    ],
)
def test_routing_prompt_receives_user_question_and_selects_matching_tool(question, expected_tool):
    client = QuestionAwareRoutingClient()
    result = build_service(client).chat({"message": question})
    assert client.messages[0][1]["content"] == question
    assert result["tool_trace"][0]["tool"] == expected_tool


def test_analysis_round_receives_question_safe_evidence_and_answerability():
    client = FakeAIClient("get_cost_overview", "基于 get_cost_overview 的费用证据，平均收费与成本已完成比较。")
    question = "收费与成本之间有什么值得关注的地方？"
    result = build_service(client).chat({"message": question})

    analysis_messages = client.messages[1]
    assert analysis_messages[0]["content"] == ANALYSIS_SYSTEM_PROMPT
    assert analysis_messages[1] == {"role": "user", "content": question}
    tool_messages = [message for message in analysis_messages if message["role"] == "tool"]
    assert len(tool_messages) == 1
    evidence = json.loads(tool_messages[0]["content"])
    assert evidence["data_version"] == result["data_versions"][0]
    assert evidence["sections"]
    assert evidence["derived_facts"]
    context = json.loads(analysis_messages[-1]["content"])
    assert context["answerability"]["status"] in {"answerable", "partially_answerable"}
    assert "instruction" in context


def test_routing_and_analysis_prompts_have_separate_responsibilities():
    assert "工具路由器" in ROUTING_SYSTEM_PROMPT
    assert "选择" in ROUTING_SYSTEM_PROMPT
    assert "回答用户的原问题" in ANALYSIS_SYSTEM_PROMPT
    assert "机械复述" in ANALYSIS_SYSTEM_PROMPT
    assert "不得进行因果推断" in ANALYSIS_SYSTEM_PROMPT


def test_security_boundaries_are_present_in_routing_prompt():
    assert "禁止生成SQL" in ROUTING_SYSTEM_PROMPT
    assert "个人诊断" in ROUTING_SYSTEM_PROMPT
    assert "治疗" in ROUTING_SYSTEM_PROMPT
    assert "因果结论" in ROUTING_SYSTEM_PROMPT


def test_safe_evidence_does_not_copy_unknown_or_executable_fields():
    snapshot = AnalyticsSnapshotService(FixtureAnalyticsSnapshotRepository(FIXTURE_PATH)).get(
        "costs", "diagnosis=*|facility=*|severity=*"
    )
    snapshot["internal_sql"] = "select * from patients"
    snapshot["metrics"][0]["debug_html"] = "<script>alert(1)</script>"
    evidence = build_safe_evidence("get_cost_overview", snapshot)

    assert "internal_sql" not in evidence
    serialized = json.dumps(evidence, ensure_ascii=False).lower()
    assert "select * from patients" not in serialized
    assert "<script" not in serialized


def test_derived_facts_include_ranking_ratio_and_group_difference_when_available():
    analytics = AnalyticsSnapshotService(FixtureAnalyticsSnapshotRepository(FIXTURE_PATH))
    cost = build_safe_evidence(
        "get_cost_overview", analytics.get("costs", "diagnosis=*|facility=*|severity=*")
    )
    hospital = build_safe_evidence("get_hospital_overview", analytics.get("hospitals", "index"))

    cost_fact_keys = {fact["key"] for fact in cost["derived_facts"]}
    hospital_fact_types = {fact["type"] for fact in hospital["derived_facts"]}
    assert "charge_cost_gap" in cost_fact_keys
    assert "charge_cost_ratio" in cost_fact_keys
    assert "ranking" in hospital_fact_types
    assert "group_difference" in hospital_fact_types


def test_answerability_classifies_unsafe_unsupported_and_partial_questions():
    analytics = AnalyticsSnapshotService(FixtureAnalyticsSnapshotRepository(FIXTURE_PATH))
    cost = build_safe_evidence(
        "get_cost_overview", analytics.get("costs", "diagnosis=*|facility=*|severity=*")
    )
    hospital = build_safe_evidence("get_hospital_overview", analytics.get("hospitals", "index"))

    assert assess_answerability("这个病人应该接受什么治疗？", [cost])["status"] == "unsafe"
    assert assess_answerability("今年费用比去年上涨了吗？", [cost])["status"] == "unsupported"
    assert assess_answerability("为什么某医院费用这么高？", [cost])["status"] == "unsupported"
    assert assess_answerability("医院病例量和费用有什么关系？", [hospital])["status"] == "partially_answerable"
    assert assess_question_scope("当前整体运营怎么样？") is None
    assert assess_question_scope("hello") is None
    assert assess_question_scope("今年费用比去年上涨了吗？")["status"] == "unsupported"


def test_cross_cost_and_risk_question_is_partial_without_joint_grain():
    analytics = AnalyticsSnapshotService(FixtureAnalyticsSnapshotRepository(FIXTURE_PATH))
    cost = build_safe_evidence(
        "get_cost_overview", analytics.get("costs", "diagnosis=*|facility=*|severity=*")
    )
    risk = build_safe_evidence("get_risk_overview", analytics.get("risks", "age=*|diagnosis=*"))

    result = assess_answerability("请结合费用和风险分析当前运营问题。", [cost, risk])
    assert result["status"] == "partially_answerable"
    assert result["limitations"]


class NonObjectArgumentsAIClient:
    def complete(self, messages, tools=None):
        return {"role": "assistant", "content": None, "tool_calls": [tool_call(arguments="[]")]}


def test_non_object_tool_arguments_are_rejected():
    with pytest.raises(UpstreamServiceError, match="unsupported tool arguments"):
        build_service(NonObjectArgumentsAIClient()).chat({"message": "查询运营情况"})


def test_deepseek_client_without_api_key_fails_closed():
    client = DeepSeekChatClient(
        api_key=None,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout=20,
    )
    with pytest.raises(ServerMisconfiguredError):
        client.complete([{"role": "user", "content": "hello"}])


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: TimeoutError("simulated timeout"),
        lambda: ai_assistant_module.URLError("simulated network failure"),
        lambda: ai_assistant_module.HTTPError(
            url="https://api.deepseek.com/chat/completions",
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=None,
        ),
    ],
)
def test_deepseek_provider_failures_become_upstream_errors(monkeypatch, error_factory):
    monkeypatch.setattr(ai_assistant_module, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error_factory()))
    client = DeepSeekChatClient(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout=20,
    )
    with pytest.raises(UpstreamServiceError):
        client.complete([{"role": "user", "content": "hello"}])
