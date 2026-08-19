# Issue #44 后端接口独立验收证据

验收范围：运营驾驶舱只读接口、AnalyticsSnapshotService seam、请求边界、错误映射、API 文档和真实快照交接。

## 验收结论

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| A-01 | 请求白名单与严格 GET-only | PASS | backend/app/routes/analytics.py、backend/app/routes/parameters.py、backend/tests/test_analytics_api.py |
| A-02 | 正常响应与合法空结果 | PASS | fixture 统一信封、X-Trace-ID、data_version/generated_at；合法枚举未发布时返回 200 空结果 |
| A-03 | 失败映射与信息安全 | PASS | INVALID_QUERY_PARAMETER、INVALID_REQUEST_FORMAT、RESULT_NOT_READY、DATABASE_UNAVAILABLE、SERVICE_RESULT_INVALID 测试 |
| A-04 | 读取 seam | PASS | Route 只调用 AnalyticsSnapshotService.get(module_key, entity_key)；MySQL SQL 仅在 Repository |
| A-05 | 真实 MySQL 快照交接 | PASS（既有真实记录） | evidence/39、evidence/45 的真实 MySQL/API 记录 |
| A-06 | 下游交接 | PASS | docs/05-api.md 已写明 endpoint、请求限制、响应信封、错误码和版本字段 |

## 自动化结果

    python -m pytest backend/tests data/tests -q
    50 passed, 1 skipped

覆盖统一信封和追踪头、未知/重复查询参数、GET body、HEAD/OPTIONS/其他方法、合法空结果、实体键顺序、配置/数据库/结果损坏错误及敏感信息不泄露。#48 在同一 backend/analytics-api 工作流分支补充的接口测试与 #44 共用这套只读边界；共享分支保留 #40 基线。

## 真实数据边界

已合并的真实快照记录显示：

- data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219；
- MySQL analysis_snapshot_result 发布后 691 条记录，版本和生成时间各唯一；
- GET /api/v1/dashboard/overview 曾返回 HTTP 200，8 个指标、5 个分区，版本与快照一致。

2026-08-19 本机重新切换真实配置时，上游 hadoop001 不可达，接口按契约返回 503 DATABASE_UNAVAILABLE；该结果仅作为依赖失败映射复核，不冒充真实成功。既有 #39/#45 记录是本次真实联调通过证据；本次边界变更不改变 MySQL 查询、快照结构或业务数值。

## 下游交接

前端调用 GET /api/v1/dashboard/overview，不发送 query/body；读取 data.metrics、data.sections、data_version、generated_at，并使用 HTTP 状态、code 和 trace_id 判断错误。fixture 只用于确定性联调，不代表真实全量结论。
