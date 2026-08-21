# Issue #80 后端 AI 接口验收证据

Issue：[#80 AI 后端接口](https://github.com/Martin7816/yishuyunce-medical-analytics/issues/80)

分支：`ai/deepseek-assistant`

## 1. Question 与交付范围

稳定提供 `POST /api/v1/ai/chat`，让前端获得可核验的回答来源，并在 Key 缺失、超时、HTTP、断网、坏响应、空回答和白名单工具失败时返回安全错误。

本次交付包含：

- `backend/app/routes/intelligence.py`：AI 接口只接受 POST，关闭自动 OPTIONS；路由不拼接 DeepSeek 请求或执行工具。
- `backend/app/services/ai_assistant.py`：请求字段校验、DeepSeek/工具边界隔离、白名单工具结果校验、来源与版本追踪、预定义图表和完整成功响应。
- `backend/app/errors.py`：移除重复的 `UpstreamServiceError` 定义。
- `backend/tests/test_ai_api.py`：接口级成功、请求边界、方法、配置缺失、外部失败和敏感信息隔离测试。
- `backend/tests/test_ai_assistant.py`：补充多 source 版本不一致仍完整暴露的测试。
- `docs/05-api.md`：补齐请求/成功响应/错误矩阵和 #81 前端交接。

## 2. 验收矩阵

| 编号 | 场景/检查项 | 执行动作 | 预期结果 | 证据 | 状态 |
|---|---|---|---|---|---|
| AI-01 | JSON 请求边界 | 非 JSON、非对象、缺失/额外字段、空白消息、1001 字符消息 | 400，分别为 `INVALID_REQUEST_FORMAT` 或 `INVALID_REQUEST_FIELD` | `backend/tests/test_ai_api.py` | PASS |
| AI-02 | 成功响应 | fixture + FakeAIClient POST `/api/v1/ai/chat` | 200；包含 answer、tool_trace、sources、data_versions、chart、report、boundary；至少一个 source/version | `backend/tests/test_ai_api.py::test_chat_success_has_stable_traceable_contract` | PASS |
| AI-03 | trace_id | 检查成功与错误响应头/正文 | `X-Trace-ID` 与正文 `trace_id` 相同 | `assert_trace` helper 与全量 API 回归 | PASS |
| AI-04 | 无 Key | 不注入 `DEEPSEEK_API_KEY` 发送有效请求 | 500 `SERVER_MISCONFIGURED`，不返回 prompt/Authorization/堆栈 | `test_chat_without_key_returns_safe_configuration_error` | PASS |
| AI-05 | 失败网络 | 模拟 Timeout、HTTP 502、URLError、ConnectionResetError | 503 `UPSTREAM_SERVICE_ERROR`，错误正文只含安全文案和 trace_id | `test_real_client_failures_return_redacted_upstream_error` | PASS |
| AI-06 | FakeAIClient 工具矩阵 | 0/1/2/3 次调用、未知工具、坏参数、空回答、八个白名单工具 | 0/>2/未知/坏参数/空回答拒绝；合法来源、工具轨迹和版本保留 | `backend/tests/test_ai_assistant.py`（26 项） | PASS |
| AI-07 | 多 source 版本 | 两个工具返回不同 `data_version` | 每个 source 的版本和完整 `data_versions` 均保留，不隐藏冲突 | `test_multiple_source_versions_remain_visible` | PASS |
| AI-08 | API 文档与交接 | 对照 `docs/05-api.md` | 请求字段、成功字段、错误码、图表类型和 #81 使用字段已冻结 | `docs/05-api.md` 第 5 节 | PASS |

## 3. 自动化执行结果

```text
python -m pytest -q backend/tests/test_ai_assistant.py backend/tests/test_ai_api.py
45 passed

python -m pytest -q backend/tests
173 passed

python -m py_compile backend/app/services/ai_assistant.py backend/app/routes/intelligence.py backend/app/errors.py
PASS
```

## 4. 真实 Key 与脱敏边界

当前执行环境的 `backend/.env` 不含 `DEEPSEEK_API_KEY`，本次没有伪造或声称完成新的实时 Key 请求；密钥从未读取、输出、提交或写入日志/evidence。

共享 `DeepSeekChatClient` 的真实 Key 证据已经在 [evidence/79/execution-record.md](../79/execution-record.md) 第 9—12 节记录：API 连通、Q01—Q09 工具路由、真实 20 秒超时和安全红队均 PASS，且只记录脱敏状态/工具结果，没有保存 Key、Authorization 或完整敏感日志。#80 的接口复用同一客户端，并新增了接口层失败与脱敏回归测试；当前环境的实时 Key 复验需在配置 Key 后按同一命令补跑，不能用 fixture 代替。

所有错误响应的 `data` 为 `null`，不会返回 Key、Authorization、用户 prompt、SQL、堆栈、数据库地址、口令或住院明细。

## 5. #81 下游交接

前端从统一信封读取：

- `data.answer`
- `data.tool_trace[]`: `tool`, `status`, `data_version`
- `data.sources[]`: `tool`, `title`, `metrics`, `data_version`
- `data.data_versions[]`
- `data.chart`: 仅使用 `bar`、`pie`、`table`、`status`
- `data.report`
- `data.boundary`

前端错误态按 HTTP 状态和 `code` 处理：400 `INVALID_REQUEST_FORMAT` / `INVALID_REQUEST_FIELD`，405 `METHOD_NOT_ALLOWED`，500 `SERVER_MISCONFIGURED`，503 `UPSTREAM_SERVICE_ERROR`；所有状态展示 `trace_id`，不展示错误详情或密钥。
