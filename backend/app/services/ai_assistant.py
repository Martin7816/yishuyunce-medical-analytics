"""DeepSeek routing and grounded analytics analysis."""

from __future__ import annotations

import json
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
    validate_answer_grounding,
)


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

CHART_TYPES = frozenset({"bar", "pie", "table", "status"})
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


class AIAssistantService:
    def __init__(self, analytics_service, client) -> None:
        self.analytics = analytics_service
        self.client = client

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
    def _chart(sources: list[dict]) -> dict | None:
        if not sources or not sources[0]["metrics"]:
            return None
        chart_type = "bar"
        if chart_type not in CHART_TYPES:
            raise UpstreamServiceError()
        return {
            "type": chart_type,
            "title": sources[0]["title"],
            "items": [
                {"name": item["label"], "value": item["value"]}
                for item in sources[0]["metrics"][:8]
            ],
        }

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

    def chat(self, document: object) -> dict:
        if not isinstance(document, dict):
            raise InvalidRequestError("INVALID_REQUEST_FORMAT", "A JSON object is required.")
        if set(document) != {"message"}:
            raise InvalidRequestError("INVALID_REQUEST_FIELD", "Only message is accepted.")
        question = document.get("message")
        if not isinstance(question, str) or not question.strip() or len(question.strip()) > 1000:
            raise InvalidRequestError("INVALID_REQUEST_FIELD", "message must contain 1 to 1000 characters.")
        question = question.strip()

        intrinsic_answerability = assess_question_scope(question)
        if intrinsic_answerability is not None:
            return self._controlled_no_tool_result(intrinsic_answerability)

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
        analysis_messages = self._analysis_messages(question, analysis_calls, sources, answerability)
        final = self._complete(analysis_messages)
        answer = final.get("content")
        if not isinstance(answer, str) or not answer.strip():
            raise UpstreamServiceError("The AI returned an empty answer.")
        if not validate_answer_grounding(answer, sources, answerability):
            answer = self._grounded_fallback_answer(answerability, sources)
        result = {
            "answer": answer.strip(),
            "tool_trace": tool_trace,
            "sources": sources,
            "data_versions": sorted(versions),
            "chart": self._chart(sources),
            "report": {"title": "医数云策洞察简报", "printable": True},
            "boundary": "Aggregated inpatient discharge records; no patient-level diagnosis or causal claim.",
        }
        if set(result) != CHAT_RESULT_FIELDS or not result["sources"] or not result["data_versions"]:
            raise UpstreamServiceError()
        return result
