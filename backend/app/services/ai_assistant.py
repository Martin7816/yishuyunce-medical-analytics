"""DeepSeek routing and grounded analytics analysis."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..errors import (
    AppError,
    InvalidRequestError,
    ServerMisconfiguredError,
    UpstreamServiceError,
)
from .ai_evidence import (
    assess_answerability,
    assess_question_scope,
    build_safe_evidence,
    is_patient_level_question,
    is_simple_conversation,
    validate_answer_grounding,
)
from .ai_chart import build_chart_from_evidence
from .analytics_agent import AnalyticsAgentOrchestrator
from .deepseek_planner import DeepSeekPlannerAdapter
from .evidence_answer_generator import (
    AnswerResult,
    EvidenceAnswerGenerator,
    EvidenceAnswerGeneratorError,
)
from .semantic_registry import semantic_registry


TOOL_TO_SNAPSHOT = {
    "get_dashboard_overview": ("dashboard", "overview"),
    "get_hospital_overview": ("hospitals", "index"),
    "get_disease_overview": ("diseases", "index"),
    "get_cohort_summary": ("cohorts", "age=*|gender=*|admission=*"),
    "get_cost_overview": ("costs", "diagnosis=*|facility=*|severity=*"),
    "get_risk_overview": ("risks", "age=*|diagnosis=*"),
    "get_payment_overview": ("payments", "payment=*|age=*"),
    "get_model_metrics": ("high_cost_model", "metrics"),
}

TOOL_DESCRIPTIONS = {
    "get_dashboard_overview": (
        "用于回答当前整体运营概况、总体规模和关键运营指标；返回全局群体汇总，"
        "不用于医院、疾病或患者个体的详细解释。"
    ),
    "get_hospital_overview": (
        "用于回答医院/机构病例量排名、医院指标对比，以及医院层面的收费或运营差异；"
        "返回医院级聚合，不返回患者明细。"
    ),
    "get_disease_overview": (
        "用于回答疾病/病种数量排名、疾病结构和主要诊断分布；返回疾病级聚合，"
        "不能支持个体诊断或治疗建议。"
    ),
    "get_cohort_summary": (
        "用于回答年龄、性别、入院方式等群体结构，以及群体层面的疾病和严重程度分布；"
        "只返回群体汇总。"
    ),
    "get_cost_overview": (
        "用于回答收费、成本、费用结构、收费成本差值/比例和费用与住院时长的汇总关系；"
        "不能解释单个患者或医院费用的因果原因。"
    ),
    "get_risk_overview": (
        "用于回答风险、严重程度、死亡/出院结局、年龄或疾病风险分布；"
        "返回风险群体汇总，不进行患者个体判断。"
    ),
    "get_payment_overview": (
        "用于回答支付方式结构、支付方式对应的病例量或收费汇总，以及支付分布差异；"
        "不返回个人账单或支付原因。"
    ),
    "get_model_metrics": (
        "用于回答高费用模型的 Accuracy、Precision、Recall、F1、AUC 和混淆矩阵；"
        "只描述模型评估快照，不预测具体患者。"
    ),
}

ROUTING_SYSTEM_PROMPT = (
    "你是医数云策 AI 问答的工具路由器。你的唯一任务是理解用户原问题并选择 "
    "1 个最直接相关的白名单工具；只有问题明确包含两个不同主题时才选择 2 个，永远不能超过 2 个。\n"
    "工具选择规则：整体运营用 get_dashboard_overview；医院/机构用 get_hospital_overview；"
    "疾病/病种用 get_disease_overview；年龄、性别、入院方式或群体结构用 get_cohort_summary；"
    "收费、成本或费用用 get_cost_overview；风险、严重程度或结局用 get_risk_overview；"
    "支付方式用 get_payment_overview；高费用模型评估指标用 get_model_metrics。\n"
    "若问题是医院病例量与费用的关系，选择 get_hospital_overview 和 get_cost_overview；"
    "若问题明确要求费用与风险的联合分析，选择 get_cost_overview 和 get_risk_overview；"
    "若问题要求从疾病规模和风险中筛选重点疾病，选择 get_disease_overview 和 get_risk_overview。\n"
    "只允许调用下列工具，所有工具参数必须是空对象 {}：\n"
    + "\n".join(f"- {name}: {description}" for name, description in TOOL_DESCRIPTIONS.items())
    + "\n路由阶段不要回答业务问题，不要编造数据，也不要调用未列出的工具。"
    "如果问题超出汇总能力，仍选择最接近的安全汇总工具，由下一阶段明确说明边界。"
    "正常情况下必须返回 1 到 2 个 tool_calls，不要在路由阶段直接给业务答案。"
    "禁止生成SQL、个人诊断、治疗或因果结论。"
)

CONVERSATION_SYSTEM_PROMPT = (
    "你是‘医数云策’的 AI 医疗运营分析助手。对问候、致谢、告别、身份和能力介绍等普通交流，"
    "请自然、简洁、友好地回答，通常控制在 1～3 个自然段。不要假装读取了数据，不要编造指标、"
    "医院、疾病或数据版本，不要声称执行过分析工具，也不要向用户解释白名单路由、tool call、"
    "answerability 等内部技术概念。用户询问系统能力时，可以介绍你支持医院运营、疾病结构、人群、"
    "费用成本、风险、支付方式和高费用模型评估等聚合分析。不要提供患者诊断、治疗、用药或个体预测。"
)

ANALYSIS_SYSTEM_PROMPT = (
    "你是医数云策的分析型回答助手。请回答用户的原问题，而不是机械复述工具结果。"
    "你只能使用消息中给出的安全证据、derived_facts 和 answerability，不得补造任何工具未提供的数据。\n"
    "回答顺序：先用第一段直接回答问题；随后给出关键数据证据；再提炼最大/最小、排名、"
    "差距、比例、份额、结构特征或明显值得关注的项；最后用简短文字说明统计边界。"
    "事实和解释要分开：解释只能使用‘数据显示’、‘值得进一步关注’、‘可以进一步分析’等表述。\n"
    "只允许从已有汇总数据做简单可验证的加减、除法、排名和份额计算；不得进行因果推断、"
    "医疗诊断、治疗建议、过度收费结论或患者个体判断。涉及 unsupported、unsafe 或"
    "partially_answerable 时，明确说明能回答的部分和不能回答的部分。不要把两个孤立指标说成相关，"
    "不要把观察性汇总说成原因。不要使用 Markdown 表格，除非用户明确要求；不要输出代码或 SQL。"
    "通常回答 2–5 个自然段，复杂的双主题问题回答 6–8 个自然段。"
)

CHAT_RESULT_FIELDS = frozenset(
    {
        "answer",
        "tool_trace",
        "sources",
        "data_versions",
        "chart",
        "report",
        "boundary",
    }
)


_NEW_ANALYTICS_MARKERS = (
    "by",
    "group by",
    "breakdown",
    "distribution",
    "filter",
    "segment",
    "dimension",
    "measure",
    "across",
    "按",
    "分组",
    "分布",
    "筛选",
    "过滤",
    "维度",
    "指标",
    "分别",
)
_ADVANCED_MEASURE_HINTS = (
    "avg_los",
    "avg_charges",
    "avg_costs",
    "emergency_rate",
    "surgical_rate",
    "severe_rate",
    "average length of stay",
    "average charges",
    "average costs",
    "emergency rate",
    "surgical rate",
    "severe rate",
    "平均住院",
    "急诊率",
    "手术率",
    "重症率",
)
# Natural-language hints are intentionally kept at the routing boundary.  The
# semantic registry remains the canonical plan vocabulary; these hints only
# decide whether a question is eligible for the new analytics path.
_CLASSIFIER_DIMENSION_HINTS = {
    "diagnosis": ("\u75be\u75c5", "\u8bca\u65ad", "\u75c5\u79cd"),
    "age_group": ("\u5e74\u9f84", "\u5e74\u9f84\u6bb5", "\u5c81\u4ee5\u4e0a", "\u8001\u4eba"),
    "gender": ("\u6027\u522b", "\u7537\u6027", "\u5973\u6027"),
    "payment": (
        "Medicare",
        "Medicaid",
        "\u533b\u4fdd",
        "\u652f\u4ed8",
        "\u652f\u4ed8\u65b9\u5f0f",
    ),
}
_CLASSIFIER_MEASURE_HINTS = {
    "case_count": (
        "\u75c5\u4f8b",
        "\u75c5\u4f8b\u6570",
        "\u75c5\u4f8b\u91cf",
        "\u8bca\u65ad\u6570\u91cf",
        "\u6570\u91cf",
        "\u5206\u5e03",
        "\u60c5\u51b5",
        "\u4e3b\u8981",
        "\u6700\u5e38\u89c1",
    ),
    "avg_los": (
        "\u5e73\u5747\u4f4f\u9662\u65f6\u95f4",
        "\u5e73\u5747\u4f4f\u9662\u65f6\u957f",
        "\u4f4f\u9662\u65f6\u95f4",
        "\u4f4f\u9662\u65f6\u957f",
        "\u4f4f\u9662\u5929\u6570",
    ),
    "avg_charges": (
        "\u5e73\u5747\u8d39\u7528",
        "\u5e73\u5747\u6536\u8d39",
        "\u8d39\u7528",
        "\u6536\u8d39",
        "\u82b1\u8d39",
    ),
    "avg_costs": ("\u5e73\u5747\u6210\u672c", "\u6210\u672c"),
}
_NEW_ANALYTICS_DIMENSIONS = frozenset(
    {"diagnosis", "age_group", "gender", "payment", "severity", "admission_type"}
)
_COHORT_PATIENT_HINTS = ("患者", "病人", "patient", "patients")

_ANALYTICS_AGENT_PUBLIC_ANSWER = (
    "The aggregate analytics agent cannot safely answer this question "
    "from the available evidence."
)
_ANALYTICS_AGENT_PUBLIC_BOUNDARY = (
    "Aggregated inpatient discharge records; no patient-level diagnosis or "
    "causal claim."
)


def _semantic_alias_matches(question: str, alias: str) -> bool:
    if not isinstance(alias, str) or not alias.strip():
        return False
    normalized = alias.strip()
    if any(ord(character) > 127 for character in normalized):
        return normalized.casefold() in question.casefold()
    # Python's Unicode word boundary treats adjacent CJK characters as word
    # characters, so ``Medicare平均费用`` would not match ``Medicare`` with
    # ``\b``.  Restrict boundaries to ASCII identifier characters instead.
    return (
        re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(normalized)}(?![A-Za-z0-9_])",
            question,
            re.IGNORECASE,
        )
        is not None
    )


def _semantic_mentions(question: str) -> tuple[set[str], set[str]]:
    dimensions: set[str] = set()
    measures: set[str] = set()
    for dimension_id, spec in semantic_registry.dimensions.items():
        aliases = (dimension_id, spec.display_name, *spec.aliases)
        if any(_semantic_alias_matches(question, alias) for alias in aliases):
            dimensions.add(dimension_id)

    for dimension_id, hints in _CLASSIFIER_DIMENSION_HINTS.items():
        if any(_semantic_alias_matches(question, hint) for hint in hints):
            dimensions.add(dimension_id)

    measure_hints = {
        "case_count": ("case_count", "case count", "cases", "病例", "病例量"),
        "avg_los": ("avg_los", "average length of stay", "住院时长"),
        "avg_charges": ("avg_charges", "average charges", "收费", "收费额"),
        "avg_costs": ("avg_costs", "average costs", "costs", "成本"),
        "emergency_rate": ("emergency_rate", "emergency rate", "急诊率"),
        "surgical_rate": ("surgical_rate", "surgical rate", "手术率"),
        "severe_rate": ("severe_rate", "severe rate", "重症率"),
    }
    for measure_id, hints in measure_hints.items():
        if any(_semantic_alias_matches(question, hint) for hint in hints):
            measures.add(measure_id)

    for measure_id, hints in _CLASSIFIER_MEASURE_HINTS.items():
        if any(_semantic_alias_matches(question, hint) for hint in hints):
            measures.add(measure_id)
    return dimensions, measures


def is_new_analytics_question(question: str) -> bool:
    """Identify explicit semantic-query shapes without rerouting legacy intents."""

    if not isinstance(question, str) or not question.strip():
        return False
    normalized = question.strip()
    if is_patient_level_question(normalized):
        return False
    dimensions, measures = _semantic_mentions(normalized)
    if not measures:
        return False
    has_cohort_patient_marker = any(
        _semantic_alias_matches(normalized, alias)
        for alias in _COHORT_PATIENT_HINTS
    )
    if has_cohort_patient_marker and not dimensions:
        return True
    if not dimensions:
        return False
    lowered = normalized.casefold()
    has_new_marker = any(
        marker.casefold() in lowered for marker in _NEW_ANALYTICS_MARKERS
    )
    has_canonical_identifier = any(
        re.search(rf"\b{re.escape(identifier)}\b", normalized, re.IGNORECASE)
        for identifier in (*dimensions, *measures)
        if "_" in identifier
    )
    has_advanced_measure = any(
        hint.casefold() in lowered for hint in _ADVANCED_MEASURE_HINTS
    )
    # Keep the legacy hospital-only natural-language ranking path intact.  A
    # non-hospital semantic dimension with an aggregate measure is a bounded
    # query shape for the new agent, even when the measure is implicit (for
    # example, "disease distribution" means case_count).
    has_new_semantic_dimension = bool(dimensions & _NEW_ANALYTICS_DIMENSIONS)
    if has_new_semantic_dimension and measures:
        return True
    return bool(
        has_new_marker
        or has_canonical_identifier
        or len(dimensions) >= 2
        or has_advanced_measure
    )


def tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": (
                    f"{description} 只读取已验证、版本化的群体汇总；不接受参数，"
                    "不允许 SQL，不访问患者级明细。"
                ),
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }
        for name, description in TOOL_DESCRIPTIONS.items()
    ]


class DeepSeekChatClient:
    def __init__(self, api_key: str | None, base_url: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.model = model
        self.timeout = timeout

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        if not self.api_key:
            raise ServerMisconfiguredError()
        body = {"model": self.model, "messages": messages, "temperature": 0.1}
        if tools:
            body.update({"tools": tools, "tool_choice": "auto"})
        request = Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                document = json.loads(response.read().decode("utf-8"))
            message = document["choices"][0]["message"]
            if not isinstance(message, dict):
                raise TypeError("upstream message must be an object")
            return message
        except (
            HTTPError,
            URLError,
            TimeoutError,
            ConnectionError,
            OSError,
            UnicodeDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise UpstreamServiceError() from error

    def complete_structured(
        self,
        messages: list[dict],
        response_format: Mapping,
    ) -> dict:
        """Request provider-native structured output for the new analytics path.

        The legacy ``complete`` method remains unchanged.  DeepSeek's chat
        endpoint returns structured JSON in ``message.content`` even when a
        JSON-schema response format is requested, so this transport parses it
        once at the provider boundary and exposes only the parsed object to
        the strict planner/answer adapters.
        """

        if not self.api_key:
            raise ServerMisconfiguredError()
        if not isinstance(response_format, Mapping):
            raise UpstreamServiceError()
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            # DeepSeek Chat Completions currently exposes JSON Output rather
            # than the JSON-Schema response format.  The adapters still pass
            # their full internal schemas and validate the parsed object
            # server-side; only the provider transport representation changes.
            "response_format": (
                {"type": "json_object"}
                if response_format.get("type") == "json_schema"
                else dict(response_format)
            ),
            "max_tokens": 2048,
        }
        request = Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                document = json.loads(response.read().decode("utf-8"))
            message = document["choices"][0]["message"]
            if not isinstance(message, dict):
                raise TypeError("upstream message must be an object")
            parsed = message.get("parsed")
            if parsed is None:
                content = message.get("content")
                if isinstance(content, str):
                    parsed = json.loads(content)
                else:
                    parsed = content
            if not isinstance(parsed, dict):
                raise TypeError("structured upstream content must be an object")
            return {"parsed": parsed}
        except (
            HTTPError,
            URLError,
            TimeoutError,
            ConnectionError,
            OSError,
            UnicodeDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise UpstreamServiceError() from error

    def stream_complete(self, messages: list[dict], tools: list[dict] | None = None) -> Iterator[str]:
        if not self.api_key:
            raise ServerMisconfiguredError()
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "stream": True,
        }
        if tools:
            body.update({"tools": tools, "tool_choice": "auto"})
        request = Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        def iter_content() -> Iterator[str]:
            finished = False
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    while True:
                        raw_line = response.readline()
                        if not raw_line:
                            break
                        if isinstance(raw_line, bytes):
                            line = raw_line.decode("utf-8")
                        elif isinstance(raw_line, str):
                            line = raw_line
                        else:
                            raise TypeError("stream line must be text")
                        line = line.rstrip("\r\n")
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("event:"):
                            continue
                        if not line.startswith("data:"):
                            raise ValueError("malformed stream event")
                        payload = line[5:].strip()
                        if not payload:
                            continue
                        if payload == "[DONE]":
                            finished = True
                            break
                        document = json.loads(payload)
                        if not isinstance(document, dict):
                            raise TypeError("stream chunk must be an object")
                        choices = document.get("choices")
                        if not isinstance(choices, list) or not choices:
                            raise ValueError("stream chunk choices are missing")
                        choice = choices[0]
                        if not isinstance(choice, dict):
                            raise TypeError("stream choice must be an object")
                        delta = choice.get("delta")
                        if delta is not None and not isinstance(delta, dict):
                            raise TypeError("stream delta must be an object")
                        if isinstance(delta, dict):
                            content = delta.get("content")
                            if content is not None and not isinstance(content, str):
                                raise TypeError("stream content must be text")
                            if content:
                                yield content
                        if choice.get("finish_reason") is not None:
                            finished = True
                    if not finished:
                        raise UpstreamServiceError()
            except AppError:
                raise
            except (
                HTTPError,
                URLError,
                TimeoutError,
                ConnectionError,
                OSError,
                UnicodeDecodeError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as error:
                raise UpstreamServiceError() from error

        return iter_content()


class AIAssistantService:
    def __init__(
        self,
        analytics_service,
        client,
        *,
        analytics_agent: AnalyticsAgentOrchestrator | None = None,
        answer_generator: EvidenceAnswerGenerator | None = None,
    ) -> None:
        self.analytics = analytics_service
        self.client = client
        self.analytics_agent = analytics_agent
        self.answer_generator = answer_generator

    def _complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        try:
            response = self.client.complete(messages, tools)
        except AppError:
            raise
        except Exception as error:
            # A client implementation is an external boundary. Never let a
            # provider-specific exception or its message reach the API.
            raise UpstreamServiceError() from error
        if not isinstance(response, dict):
            raise UpstreamServiceError()
        return response

    def _stream_complete(self, messages: list[dict], tools: list[dict] | None = None) -> Iterator[str]:
        try:
            chunks = self.client.stream_complete(messages, tools)
            for chunk in chunks:
                if not isinstance(chunk, str):
                    raise UpstreamServiceError()
                if chunk:
                    yield chunk
        except AppError:
            raise
        except Exception as error:
            raise UpstreamServiceError() from error

    @staticmethod
    def _new_analytics_control_result() -> dict:
        """Return a public refusal without exposing planner internals."""

        return {
            "answer": _ANALYTICS_AGENT_PUBLIC_ANSWER,
            "tool_trace": [],
            "sources": [],
            "data_versions": [],
            "chart": None,
            "report": {"title": "Analytics report", "printable": True},
            "boundary": _ANALYTICS_AGENT_PUBLIC_BOUNDARY,
        }

    def _should_route_to_analytics_agent(self, question: str) -> bool:
        return bool(
            self.analytics_agent is not None
            and self.answer_generator is not None
            and is_new_analytics_question(question)
        )

    @staticmethod
    def _public_analytics_result(
        agent_result: Mapping,
        answer_result: AnswerResult,
    ) -> dict:
        evidence = agent_result.get("evidence")
        if not isinstance(evidence, Mapping):
            return AIAssistantService._new_analytics_control_result()

        provenance = answer_result.provenance
        if provenance is None:
            candidate = evidence.get("provenance")
            provenance = dict(candidate) if isinstance(candidate, Mapping) else None
        if not isinstance(provenance, Mapping):
            return AIAssistantService._new_analytics_control_result()
        data_version = provenance.get("data_version")
        if not isinstance(data_version, str) or not data_version:
            return AIAssistantService._new_analytics_control_result()

        # QueryPlan is useful inside the backend pipeline but is not an SSE or
        # chat answer field.  Keep only Safe Evidence and provenance in the
        # public source contract.
        source = dict(evidence)
        source.pop("query_plan", None)
        source["provenance"] = dict(provenance)
        source["data_version"] = data_version
        chart = source.get("chart")
        if not isinstance(chart, Mapping):
            chart = None
        result = {
            "answer": answer_result.answer_text,
            "tool_trace": [
                {
                    "tool": "query_analytics",
                    "status": "success",
                    "data_version": data_version,
                }
            ],
            "sources": [source],
            "data_versions": [data_version],
            "chart": chart,
            "report": {"title": "Analytics report", "printable": True},
            "boundary": _ANALYTICS_AGENT_PUBLIC_BOUNDARY,
        }
        if set(result) != CHAT_RESULT_FIELDS:
            return AIAssistantService._new_analytics_control_result()
        return result

    def _run_analytics_agent(self, question: str) -> dict:
        """Run the new path and collapse all planner details to a safe result."""

        if self.analytics_agent is None or self.answer_generator is None:
            return self._new_analytics_control_result()
        try:
            agent_result = self.analytics_agent.run(question)
        except AppError:
            raise
        except Exception:
            # The public route must not expose provider, planner, SQL, or
            # validator details.  The agent path fails closed on any adapter
            # boundary error.
            return self._new_analytics_control_result()

        if not isinstance(agent_result, Mapping):
            return self._new_analytics_control_result()
        if agent_result.get("status") not in {"ok", "empty"}:
            return self._new_analytics_control_result()
        evidence = agent_result.get("evidence")
        if not isinstance(evidence, Mapping):
            return self._new_analytics_control_result()

        try:
            answer_result = self.answer_generator.generate(
                question,
                evidence,
            )
        except AppError:
            raise
        except EvidenceAnswerGeneratorError:
            return self._new_analytics_control_result()
        except Exception:
            return self._new_analytics_control_result()
        if not isinstance(answer_result, AnswerResult):
            return self._new_analytics_control_result()
        return self._public_analytics_result(agent_result, answer_result)

    def _run_tool(self, name: str, arguments: str) -> dict:
        if not isinstance(name, str):
            raise UpstreamServiceError("The AI requested a non-whitelisted tool.")
        if name not in TOOL_TO_SNAPSHOT:
            raise UpstreamServiceError("The AI requested a non-whitelisted tool.")
        if not isinstance(arguments, str):
            raise UpstreamServiceError("The AI supplied unsupported tool arguments.")
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError as error:
            raise UpstreamServiceError("The AI supplied invalid tool arguments.") from error
        if not isinstance(parsed, dict) or parsed:
            raise UpstreamServiceError("The AI supplied unsupported tool arguments.")
        module, entity = TOOL_TO_SNAPSHOT[name]
        try:
            result = self.analytics.get(module, entity)
        except AppError as error:
            raise UpstreamServiceError() from error
        except Exception as error:
            raise UpstreamServiceError() from error
        if not isinstance(result, dict):
            raise UpstreamServiceError()
        if not isinstance(result.get("title"), str):
            raise UpstreamServiceError()
        if not isinstance(result.get("metrics"), list):
            raise UpstreamServiceError()
        if not isinstance(result.get("data_version"), str) or not result["data_version"]:
            raise UpstreamServiceError()
        return result

    @staticmethod
    def _tool_calls(message: dict) -> list[dict]:
        calls = message.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            raise UpstreamServiceError("The AI answer did not use a verified analytics tool.")
        if len(calls) > 2:
            raise UpstreamServiceError("The AI exceeded the two-tool-call limit.")
        if any(not isinstance(call, dict) for call in calls):
            raise UpstreamServiceError()
        return calls

    @staticmethod
    def _source(name: str, result: dict) -> dict:
        try:
            return build_safe_evidence(name, result)
        except (TypeError, ValueError, KeyError) as error:
            raise UpstreamServiceError() from error

    @staticmethod
    def _analysis_messages(
        question: str,
        calls: list[dict[str, str]],
        sources: list[dict],
        answerability: dict,
    ) -> list[dict]:
        assistant_calls = [
            {
                "id": call["id"],
                "type": "function",
                "function": {"name": call["name"], "arguments": "{}"},
            }
            for call in calls
        ]
        messages: list[dict] = [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": question},
            {"role": "assistant", "content": None, "tool_calls": assistant_calls},
        ]
        for call, source in zip(calls, sources):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(source, ensure_ascii=False),
                }
            )
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "answerability": answerability,
                        "instruction": "请基于以上安全证据回答用户原问题，并明确证据限制。",
                    },
                    ensure_ascii=False,
                ),
            }
        )
        return messages

    @staticmethod
    def _grounded_fallback_answer(answerability: dict, sources: list[dict]) -> str:
        status = answerability.get("status")
        reason = answerability.get("reason") or "当前证据不足。"
        limitations = answerability.get("limitations") or []
        source_titles = "、".join(
            source["title"] for source in sources if isinstance(source.get("title"), str)
        )
        if status == "unsafe":
            return "当前数据仅提供群体汇总，不能支持患者级诊断、治疗建议或个体预测。"
        if status == "unsupported":
            return f"当前数据无法可靠回答该问题：{reason} 现有安全证据仅覆盖：{source_titles}。"
        if status == "partially_answerable":
            limitation = limitations[0] if limitations else "仍存在统计边界。"
            return f"当前数据可以回答汇总层面的部分，但不能完成问题中的全部判断。{limitation}"
        return f"模型回答未能引用已验证证据。请以安全来源‘{source_titles}’中的指标、分组和数据版本为准。"

    @staticmethod
    def _controlled_no_tool_result(answerability: dict) -> dict:
        status = answerability.get("status")
        reason = answerability.get("reason") or "当前数据不足以支持该问题。"
        if status == "unsafe":
            answer = "当前数据仅提供群体汇总，不能支持患者级诊断、治疗建议或个体预测。"
        else:
            answer = f"当前数据无法可靠回答该问题：{reason}"
        return {
            "answer": answer,
            "tool_trace": [],
            "sources": [],
            "data_versions": [],
            "chart": None,
            "report": {"title": "医数云策洞察简报", "printable": True},
            "boundary": "Aggregated inpatient discharge records; no patient-level diagnosis or causal claim.",
        }

    @staticmethod
    def _conversation_result(answer: str) -> dict:
        return {
            "answer": answer.strip(),
            "tool_trace": [],
            "sources": [],
            "data_versions": [],
            "chart": None,
            "report": {"title": "医数云策洞察简报", "printable": True},
            "boundary": "Aggregated inpatient discharge records; no patient-level diagnosis or causal claim.",
        }

    @staticmethod
    def _validate_document(document: object) -> str:
        if not isinstance(document, dict):
            raise InvalidRequestError("INVALID_REQUEST_FORMAT", "A JSON object is required.")
        if set(document) != {"message"}:
            raise InvalidRequestError("INVALID_REQUEST_FIELD", "Only message is accepted.")
        question = document.get("message")
        if not isinstance(question, str) or not question.strip() or len(question.strip()) > 1000:
            raise InvalidRequestError("INVALID_REQUEST_FIELD", "message must contain 1 to 1000 characters.")
        return question.strip()

    def validate_document(self, document: object) -> str:
        """Validate a chat payload before a streaming response is opened."""

        return self._validate_document(document)

    def _prepare_analysis(self, question: str) -> dict:
        routing_messages = [
            {"role": "system", "content": ROUTING_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        first = self._complete(routing_messages, tool_definitions())
        calls = self._tool_calls(first)

        tool_trace: list[dict] = []
        sources: list[dict] = []
        versions: set[str] = set()
        analysis_calls: list[dict[str, str]] = []
        for call in calls:
            function = call.get("function", {})
            if not isinstance(function, dict):
                raise UpstreamServiceError()
            name = function.get("name", "")
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id:
                raise UpstreamServiceError()
            result = self._run_tool(name, function.get("arguments", "{}"))
            versions.add(result["data_version"])
            source = self._source(name, result)
            sources.append(source)
            analysis_calls.append({"id": call_id, "name": name})
            tool_trace.append({"tool": name, "status": "success", "data_version": result["data_version"]})

        answerability = assess_answerability(question, sources)
        for source in sources:
            source["answerability"] = answerability
        return {
            "question": question,
            "tool_trace": tool_trace,
            "sources": sources,
            "versions": versions,
            "answerability": answerability,
            "analysis_messages": self._analysis_messages(
                question, analysis_calls, sources, answerability
            ),
        }

    def _analysis_result(self, prepared: dict, answer: str) -> dict:
        if not isinstance(answer, str) or not answer.strip():
            raise UpstreamServiceError("The AI returned an empty answer.")
        answer = answer.strip()
        if not validate_answer_grounding(
            answer, prepared["sources"], prepared["answerability"]
        ):
            answer = self._grounded_fallback_answer(
                prepared["answerability"], prepared["sources"]
            )
        result = {
            "answer": answer,
            "tool_trace": prepared["tool_trace"],
            "sources": prepared["sources"],
            "data_versions": sorted(prepared["versions"]),
            "chart": build_chart_from_evidence(prepared["question"], prepared["sources"]),
            "report": {"title": "医数云策洞察简报", "printable": True},
            "boundary": "Aggregated inpatient discharge records; no patient-level diagnosis or causal claim.",
        }
        if set(result) != CHAT_RESULT_FIELDS or not result["sources"] or not result["data_versions"]:
            raise UpstreamServiceError()
        return result

    @staticmethod
    def _stream_done_payload(result: dict) -> dict:
        return {
            "tool_trace": result["tool_trace"],
            "sources": result["sources"],
            "data_versions": result["data_versions"],
            "chart": result["chart"],
            "report": result["report"],
            "boundary": result["boundary"],
        }

    @staticmethod
    def _stage(stage: str, label: str) -> tuple[str, dict]:
        return "stage", {"stage": stage, "label": label}

    @staticmethod
    def _delta(text: str) -> tuple[str, dict]:
        return "delta", {"text": text}

    def stream_chat(self, document: object) -> Iterator[tuple[str, dict]]:
        question = self._validate_document(document)
        yield self._stage("preparing", "正在准备回答")
        yield self._stage("understanding", "正在理解问题")

        intrinsic_answerability = assess_question_scope(question)
        if intrinsic_answerability is not None:
            result = self._controlled_no_tool_result(intrinsic_answerability)
            yield self._stage("generation", "正在生成回答")
            yield self._delta(result["answer"])
            yield "done", self._stream_done_payload(result)
            return

        if is_simple_conversation(question):
            yield self._stage("generation", "正在生成回答")
            answer_parts: list[str] = []
            messages = [
                {"role": "system", "content": CONVERSATION_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]
            for chunk in self._stream_complete(messages):
                answer_parts.append(chunk)
                yield self._delta(chunk)
            answer = "".join(answer_parts).strip()
            if not answer:
                raise UpstreamServiceError("The AI returned an empty answer.")
            result = self._conversation_result(answer)
            yield "done", self._stream_done_payload(result)
            return

        if self._should_route_to_analytics_agent(question):
            yield self._stage("querying", "Querying aggregate evidence")
            result = self._run_analytics_agent(question)
            yield self._stage("analyzing", "Analyzing grounded evidence")
            yield self._delta(result["answer"])
            yield self._stage("completed", "Completed")
            yield "done", self._stream_done_payload(result)
            return

        yield self._stage("routing", "正在选择分析工具")
        prepared = self._prepare_analysis(question)
        yield self._stage("evidence", "正在读取已验证数据")
        yield self._stage("analysis", "正在分析关键指标")
        yield self._stage("generation", "正在生成回答")
        answer_parts = []
        for chunk in self._stream_complete(prepared["analysis_messages"]):
            answer_parts.append(chunk)
            yield self._delta(chunk)
        result = self._analysis_result(prepared, "".join(answer_parts))
        yield "done", self._stream_done_payload(result)

    def chat(self, document: object) -> dict:
        question = self._validate_document(document)

        intrinsic_answerability = assess_question_scope(question)
        if intrinsic_answerability is not None:
            return self._controlled_no_tool_result(intrinsic_answerability)

        if is_simple_conversation(question):
            conversation = self._complete(
                [
                    {"role": "system", "content": CONVERSATION_SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ]
            )
            answer = conversation.get("content")
            if not isinstance(answer, str) or not answer.strip():
                raise UpstreamServiceError("The AI returned an empty answer.")
            return self._conversation_result(answer)

        if self._should_route_to_analytics_agent(question):
            return self._run_analytics_agent(question)

        prepared = self._prepare_analysis(question)
        final = self._complete(prepared["analysis_messages"])
        return self._analysis_result(prepared, final.get("content"))
