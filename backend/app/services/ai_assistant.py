"""DeepSeek tool orchestration with a strict analytics whitelist."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..errors import InvalidRequestError, ServerMisconfiguredError, UpstreamServiceError


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


def tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": "Read a verified, versioned aggregate. No SQL and no patient-level data.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }
        for name in TOOL_TO_SNAPSHOT
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
            return document["choices"][0]["message"]
        except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
            raise UpstreamServiceError() from error


class AIAssistantService:
    def __init__(self, analytics_service, client) -> None:
        self.analytics = analytics_service
        self.client = client

    def _run_tool(self, name: str, arguments: str) -> dict:
        if name not in TOOL_TO_SNAPSHOT:
            raise UpstreamServiceError("The AI requested a non-whitelisted tool.")
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError as error:
            raise UpstreamServiceError("The AI supplied invalid tool arguments.") from error
        if not isinstance(parsed, dict) or parsed:
            raise UpstreamServiceError("The AI supplied unsupported tool arguments.")
        module, entity = TOOL_TO_SNAPSHOT[name]
        return self.analytics.get(module, entity)

    def chat(self, document: object) -> dict:
        if not isinstance(document, dict):
            raise InvalidRequestError("INVALID_REQUEST_FORMAT", "A JSON object is required.")
        if set(document) != {"message"}:
            raise InvalidRequestError("INVALID_REQUEST_FIELD", "Only message is accepted.")
        question = document.get("message")
        if not isinstance(question, str) or not question.strip() or len(question.strip()) > 1000:
            raise InvalidRequestError("INVALID_REQUEST_FIELD", "message must contain 1 to 1000 characters.")

        system = (
            "你是医数云策运营分析助手。只能依据以下白名单工具返回的汇总指标回答：\n"
            "- get_dashboard_overview: dashboard overall operational metrics.\n"
            "- get_hospital_overview: hospital operational overview.\n"
            "- get_disease_overview: disease aggregate overview.\n"
            "- get_cohort_summary: cohort aggregate summary.\n"
            "- get_cost_overview: cost aggregate overview.\n"
            "- get_risk_overview: risk aggregate overview.\n"
            "- get_payment_overview: payment aggregate overview.\n"
            "- get_model_metrics: model evaluation metrics.\n"
            "禁止生成SQL、个人诊断、治疗或因果结论。"
            "回答必须说明指标、数据版本和统计边界。"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": question.strip()}]
        tool_trace, sources, versions = [], [], set()
        first = self.client.complete(messages, tool_definitions())
        messages.append(first)
        calls = first.get("tool_calls") or []
        if not calls:
            raise UpstreamServiceError("The AI answer did not use a verified analytics tool.")
        if len(calls) > 2:
            raise UpstreamServiceError("The AI exceeded the two-tool-call limit.")
        for call in calls:
            function = call.get("function", {})
            name = function.get("name", "")
            result = self._run_tool(name, function.get("arguments", "{}"))
            versions.add(result["data_version"])
            source = {
                "tool": name,
                "title": result.get("title"),
                "metrics": result.get("metrics", []),
                "data_version": result["data_version"],
            }
            sources.append(source)
            tool_trace.append({"tool": name, "status": "success", "data_version": result["data_version"]})
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(source, ensure_ascii=False)})
        final = self.client.complete(messages)
        answer = final.get("content")
        if not isinstance(answer, str) or not answer.strip():
            raise UpstreamServiceError("The AI returned an empty answer.")
        chart = None
        if sources and sources[0]["metrics"]:
            chart = {"type": "bar", "title": sources[0]["title"], "items": [{"name": item["label"], "value": item["value"]} for item in sources[0]["metrics"][:8]]}
        return {
            "answer": answer.strip(),
            "tool_trace": tool_trace,
            "sources": sources,
            "data_versions": sorted(versions),
            "chart": chart,
            "report": {"title": "医数云策洞察简报", "printable": True},
            "boundary": "Aggregated inpatient discharge records; no patient-level diagnosis or causal claim.",
        }
