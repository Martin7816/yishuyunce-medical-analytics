# Issue #72 后端数据质量接口验收证据

验收日期：2026-08-20（Asia/Shanghai）
工作流：`backend/analytics-api`
接口：`GET /api/v1/data-quality/summary`

## 交付范围

- 路由固定读取 `data_quality/summary`，不在 Route 中复制 SQL、CSV 读取、聚合、排序或任务控制。
- `data_version` 是唯一可选查询参数，只接受当前已发布版本；请求白名单、重复参数、请求体和 HTTP 方法边界沿用公共契约。
- fixture 与 MySQL 使用同一个 `AnalyticsSnapshotService.get(module_key, entity_key)` seam。
- 错误映射保持 `400` 参数/格式错误、`503` 未发布或数据库不可用、`500` 配置/结果契约错误，响应不泄露内部信息。

## 验收矩阵

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| A-01 | 请求白名单与实体键 | PASS：只接受 `data_version`，调用 `(data_quality, summary)` | [`test_data_quality_api.py`](../../backend/tests/test_data_quality_api.py) |
| A-02 | 正常、显式版本与合法空 payload | PASS：统一信封、版本/时间保留，空 `metrics/sections` 仍为 200 | 同上；[`fixture-response.json`](l3-api/fixture-response.json) |
| A-03 | 失败映射与安全边界 | PASS：未知/重复/非法版本为 400，未发布/DB 为 503，损坏 payload 为 500；details 只含安全字段名 | 同上 |
| A-04 | Service seam | PASS：fixture 和 MySQL 都经 `AnalyticsSnapshotService`；测试确认 MySQL 使用绑定参数和同一实体键 | 同上 |
| A-05 | 真实联调 | PASS（沿用已发布批次证据）：真实 MySQL 模式接口返回 200，版本与其他模块一致 | [`Issue #39 API 证据`](../39/l3-api/real-mysql-summary.txt) |
| A-06 | 下游交接 | PASS：endpoint、请求参数、响应字段、错误码和复现命令已写入 API 文档，可交给 #73 | [`docs/05-api.md`](../../docs/05-api.md) |

## 自动化结果

专项测试：

```text
python -m pytest -q backend/tests/test_data_quality_api.py
9 passed, 1 warning in 0.26s
```

完整后端与数据回归：

```text
python -m pytest -q backend/tests data/tests
118 passed, 6 skipped, 1 warning in 2.06s
```

唯一 warning 是测试缓存目录权限不足，不影响测试结果；没有把它伪装成业务失败。

## TestClient 代表性响应

| 请求 | HTTP/code | 说明 |
|---|---|---|
| `GET /api/v1/data-quality/summary` | `200 / OK` | fixture payload、版本、时间和 section 顺序原样交付 |
| `GET ...?data_version=fixture:sparcs_full_analytics:v1` | `200 / OK` | 当前版本显式传入仍成功 |
| `GET ...?unexpected=select` | `400 / INVALID_QUERY_PARAMETER` | details 只有 `unexpected` |
| `GET ...?data_version=not-published` | `400 / INVALID_QUERY_PARAMETER` | 不把未知版本当作空结果 |
| GET 携带 `{}` 请求体 | `400 / INVALID_REQUEST_FORMAT` | 只读接口拒绝请求体 |
| `POST`、`OPTIONS` | `405 / METHOD_NOT_ALLOWED` | 只允许 GET；HEAD 因 HTTP 语义不返回响应体 |
| 快照未发布 / MySQL 不可用 | `503 / RESULT_NOT_READY` 或 `DATABASE_UNAVAILABLE` | 不生成假数据 |
| payload section 类型损坏 | `500 / SERVICE_RESULT_INVALID` | 不把契约错误降级为空结果 |

每次响应都带 `trace_id`，成功响应的 `X-Trace-ID` 与正文一致；错误响应的 `data` 为 `null`。

## 真实 MySQL 边界

真实批次和 MySQL/API 证据已在 #39 留存：`ANALYTICS_DATA_SOURCE=mysql` 下，`GET /api/v1/data-quality/summary` 返回 HTTP 200，使用统一版本：

```text
sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219
```

fixture 只证明接口契约和异常边界；真实全量指标、存储状态和最终页面验收仍以 #39、#70、#73 的独立证据为准。

## 下游交接

- #73 使用 `/api/v1/data-quality/summary`，只渲染返回顺序和值，不触发任务、不访问数据库、不重算指标。
- 数据质量 payload 的 `data_version`、`generated_at`、`metrics`、`sections` 和状态值来自统一快照；公共字段冲突回到 #38/#70，不在本接口新增第二套契约。
- 本地 `backend/analytics-api` 工作树已准备代码、测试、文档和证据变更；提交、推送、合并 PR 及 Issue Resolution 仍由工作流维护者按仓库权限流程处理。
