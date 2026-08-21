# Issue #68 后端验收证据：支付方式分析 API

验收日期：2026-08-19（Asia/Shanghai）。共享交付分支：`backend/analytics-api`；本 Issue 使用共享 PR #94，不创建重复功能分支或 PR。

## Question 与实现

通过统一 `AnalyticsSnapshotService` 读取 `payments` 快照，交付 `GET /api/v1/payments/overview`，使路由只负责白名单、枚举校验、固定 entity_key 和统一响应，不复制查询或指标逻辑。

- 路由：`backend/app/routes/analytics.py`
- 统一 Service：`backend/app/services/analytics_snapshot.py`
- Fixture/MySQL adapters：`backend/app/repositories/analytics_snapshot.py`
- 独立测试：`backend/tests/test_payments_api.py`
- API 文档：`docs/05-api.md`
- 公共契约：`docs/07-terminal-product-contract.md` 第 1、1.1、2.1、3 节

## 验收矩阵

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| A-01 | 请求白名单 | PASS：仅接受 `payment_type`、`age_group`；未知、非法和重复参数均为 `400 INVALID_QUERY_PARAMETER` | `backend/tests/test_payments_api.py`；fixture 14 passed；real summary |
| A-02 | 正常与空 | PASS：wildcard 为 `200 OK`，响应保留版本/时间和 `payment`、`charges`、`age`、`diseases` 四区；合法未发布组合为 `200` 且 `metrics/sections=[]` | `test_payment_wildcard_returns_the_published_payload_without_recalculation`、`test_payment_filters_use_service_seam_and_frozen_entity_order` |
| A-03 | 失败映射 | PASS：`RESULT_NOT_READY`/`DATABASE_UNAVAILABLE` 为 503，损坏结果/配置为 500；请求体和方法错误分别为 400/405，响应不泄密 | `backend/tests/test_payments_api.py`；real summary |
| A-04 | 读取 seam | PASS：支付路由只调用 `_filtered_snapshot` → `AnalyticsSnapshotService.get`，源码无 SQL、CSV、聚合、排序或指标计算 | `backend/app/routes/analytics.py`、`backend/app/services/analytics_snapshot.py` |
| A-05 | 真实联调 | PASS：`ANALYTICS_DATA_SOURCE=mysql`；wildcard、支付单筛选、年龄单筛选、组合筛选均 200；MySQL 支付行 60、版本/时间各 1，wildcard payload/version/time 与 API 全部一致 | [`l3-api/real-api-summary.json`](l3-api/real-api-summary.json)；#67 发布证据 |
| A-06 | 下游交接 | PASS：#69 可直接使用 endpoint、两个白名单参数、四个 section 和稳定错误码；合法空组合按 200 空态处理 | `docs/05-api.md`、Issue #68 Resolution 评论 |

## Fixture 验证

```text
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_payments_api.py
14 passed

backend\.venv\Scripts\python.exe -m pytest -q backend/tests
95 passed
```

覆盖场景包括：无筛选、两个单筛选、允许组合、合法空组合、未知/非法/重复参数、GET 请求体、HEAD/OPTIONS/POST/PUT/DELETE、模块未发布、MySQL 不可用、payload 损坏和 MySQL 配置缺失。

## 真实 MySQL/API 验证

本机使用未提交的 `backend/.env`，只切换读取配置为 `ANALYTICS_DATA_SOURCE=mysql`；没有把密码或连接串写入仓库。通过 Flask `TestClient` 请求 API，并使用绑定参数直接读取 `analysis_snapshot_result` 对照 wildcard 行。

- `data_version`：`sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`
- `generated_at`：`2026-08-19T00:00:00.000000Z`
- wildcard：`record_count=2,101,588`，9 个支付枚举，5 个年龄枚举，四个 section
- `payment_type=Medicare`：`record_count=826,250`
- `age_group=70 or Older`：`record_count=619,644`
- `payment_type=Medicare&age_group=70 or Older`：`record_count=565,451`
- 未知参数、非法枚举、重复参数：400；GET body：400；POST：405
- `payment_rows=60`、`distinct_data_versions=1`、`distinct_generated_at=1`
- wildcard `payload_match=true`、`data_version_match=true`、`generated_at_match=true`

支付快照的完整发布、60 个键和独立数据核对由上游 #67 证据提供；本文件只记录后端 API 的独立读取与响应复验。

## 下游交接

#69 前端直接调用：

```text
GET /api/v1/payments/overview
GET /api/v1/payments/overview?payment_type=<options.payment_type>&age_group=<options.age_group>
```

成功响应按 `data.sections` 原序渲染；不要在前端重新聚合、排序或换算。客户端按 HTTP 状态和 `code` 判断错误，合法但未发布的组合按 `200 + metrics=[] + sections=[]` 展示空态。
