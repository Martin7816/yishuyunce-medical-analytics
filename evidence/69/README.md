# Issue #69 前端验收证据：支付方式分析

验收日期：2026-08-19（Asia/Shanghai）。共享交付分支：`frontend/multi-page-dashboard`，由 PR #97 承载。

## 交付范围

- `/payments` 明确使用支付页配置，顶部提供 `payment_type`、`age_group` 两个筛选和始终可见的“清空筛选”。
- 首屏顺序固定为标题/统计说明/版本胶囊、筛选、fixture 边界提示、3 个 KPI；四个 section 严格按 API 顺序形成两列桌面布局：`payment` 与 `charges` 首行，`age` 与 `diseases` 次行，720px 以下单列。
- 共享 renderer 负责 loading/success/empty/error/retry、请求竞态保护、响应式布局、单位显示、稳定错误码提示和版本 footer；前端不聚合、排序、截断或换算正式指标。
- 图表仅渲染冻结的 `bar` 类型，长名称在坐标轴省略但 tooltip 返回完整名称；fixture 版本在指标前显示联调提示。

## 验收矩阵

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| U-01 | 布局层级 | PASS：标题、双筛选、清空、3 KPI、四 section、页脚顺序清楚 | [`payment-fixture-desktop.png`](l4-page/payment-fixture-desktop.png) |
| U-02 | 正常数据 | PASS：fixture 与真实 wildcard 均为 3 指标、`payment/charges/age/diseases` 四区；单位、顺序、版本完整 | [`fixture-api.json`](l3-api/fixture-api.json)、[`real-api-summary.json`](l3-api/real-api-summary.json)、[`payment-real-desktop.png`](l4-page/payment-real-desktop.png) |
| U-03 | 四态与 retry | PASS：loading 清空旧数据；合法空组合无指标/图；错误显示稳定 code、trace 入口和 retry；retry 恢复 success | [`payment-empty.png`](l4-page/payment-empty.png)、[`payment-error.png`](l4-page/payment-error.png)、[`browser-summary.json`](l4-page/browser-summary.json) |
| U-04 | 筛选行为 | PASS：只发 `payment_type`、`age_group`；真实 `Medicare + 70 or Older` 返回 565,451 条；fixture 合法未发布组合进入 empty | [`fixture-api.json`](l3-api/fixture-api.json)、[`browser-summary.json`](l4-page/browser-summary.json) |
| U-05 | 响应式 | PASS：1280px `scrollWidth=1265`、390px `scrollWidth=375`，均无正文横向溢出；移动端 section 单列 | [`payment-mobile.png`](l4-page/payment-mobile.png)、[`browser-summary.json`](l4-page/browser-summary.json) |
| U-06 | 安全与可访问性 | PASS：select 有 label，loading 使用 `aria-busy`，error 使用 alert，图表使用 `role=img`；只接受预定义图表类型 | `AnalysisPage.vue`、`AnalyticsChart.vue`、`PageState.vue` |
| U-07 | 真实联调 | PASS：真实版本贯穿 API/UI，9 个支付枚举、5 个年龄枚举、60 个组合；#67 已完成 MySQL payload 核对，页面真实 success 已复现 | [`real-api-summary.json`](l3-api/real-api-summary.json)、[`payment-real-desktop.png`](l4-page/payment-real-desktop.png)、[`evidence/67/README.md`](../67/README.md) |

## 构建与回归

```text
cd frontend; npm ci; npm run build
PASS — Vite 8.2.1，621 modules transformed
Note: existing AnalyticsChart chunk is larger than 500 kB after minification.

python -m pytest backend/tests data/tests -q
63 passed, 6 skipped

git diff --check
PASS
```

API fixture 还验证了未知参数 `400 INVALID_QUERY_PARAMETER`、请求体 `400 INVALID_REQUEST_FORMAT`、非 GET `405 METHOD_NOT_ALLOWED`，且每次响应的 `X-Trace-ID` 与 `trace_id` 一致。真实数据的 MySQL 事务发布、60 个 payment keys 和 `payload_mismatch=0` 沿用 #67 独立证据；本 Issue 不重复提交全量快照。

## 已知边界与交接

- `fixture:sparcs_full_analytics:v1` 仅用于并行联调与四态截图，不代表真实全量结论。
- 真实 wildcard 与有限组合使用 #67 的同一 `data_version/generated_at`；下游复现方式见 [`handoff.md`](l5-handoff/handoff.md)。
