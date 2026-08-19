# Issue #44 后端接口独立验收证据

执行日期：2026-08-19（Asia/Shanghai）  
验收范围：统一 `AnalyticsSnapshotService` 读取、运营驾驶舱接口请求边界、错误映射、实体键顺序、API 文档和真实快照交接。

## 验收矩阵

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| A-01 | 请求白名单与严格 GET-only | PASS | `backend/app/routes/analytics.py`；`test_dashboard_get_body_is_rejected`、`test_chunked_dashboard_get_body_is_rejected`、`test_analytics_endpoints_reject_implicit_head_and_options` |
| A-02 | 正常响应与合法空结果 | PASS | `test_dashboard_success_uses_the_frozen_read_interface`、`test_filter_entity_key_order_is_frozen_for_downstream_modules`；fixture 版本 `fixture:sparcs_full_analytics:v1` |
| A-03 | 失败映射与信息安全 | PASS | `test_dashboard_dependency_errors_keep_stable_public_mapping`；`data=null`，不返回 SQL、密码或内部异常 |
| A-04 | 读取 seam | PASS | 路由只通过 `analytics_snapshot_service.get(module_key, entity_key)` 读取；MySQL 查询集中在 `backend/app/repositories/analytics_snapshot.py`，无 CSV/聚合逻辑 |
| A-05 | 真实 MySQL 快照交接 | PASS（既有真实记录） | [`evidence/39/README.md`](../39/README.md)、[`evidence/39/l3-api/real-mysql-summary.txt`](../39/l3-api/real-mysql-summary.txt)、[`evidence/45/l4-page/real-overview-api.json`](../45/l4-page/real-overview-api.json) |
| A-06 | 下游交接 | PASS | [`docs/05-api.md`](../../docs/05-api.md)；正式调用 `GET /api/v1/dashboard/overview`，统一信封、版本字段和错误码已写明 |

## 本次自动化结果

```text
$ python -m pytest backend/tests data/tests -q
46 passed in 0.68s
```

覆盖内容包括：成功信封与 `X-Trace-ID`、未知参数、GET body（含无 `Content-Length` 的 chunked 请求）、HEAD/OPTIONS、合法空筛选、稳定 `entity_key` 顺序、未发布结果、数据库不可用、配置错误、损坏快照和敏感信息不泄露。

## 真实数据边界

真实快照交接沿用已合并的数据验收记录：

- `data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`；
- MySQL `analysis_snapshot_result` 发布后 691 条记录，版本和生成时间各唯一；
- `GET /api/v1/dashboard/overview` 曾在真实 MySQL 模式返回 HTTP 200，8 个指标和 5 个分区，版本与快照一致。

2026-08-19 本机再次切到真实 `.env` 请求时，`hadoop001` 当前不可达，接口按契约返回 `503 DATABASE_UNAVAILABLE`；这次结果作为依赖失败映射复核，不冒充真实成功。此前真实成功记录见上方 #39/#45 证据；本次代码变更只增加请求边界校验，不改变 MySQL 查询、快照结构或业务数值。

## 下游交接

- 前端按 `GET /api/v1/dashboard/overview` 调用，不发送 query/body；读取 `data.metrics`、`data.sections`、`data_version`、`generated_at`，并使用 `code`、HTTP 状态和 `trace_id` 判断错误。
- 合法但未发布的具体筛选由其他分析接口返回 200 空结果；整个模块未发布返回 `503 RESULT_NOT_READY`。
- fixture 版本只用于联调，不代表真实全量结论。
