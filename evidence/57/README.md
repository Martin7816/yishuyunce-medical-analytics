# Issue #57 前端验收证据：住院记录群体分析

验收日期：2026-08-19（Asia/Shanghai）。交付分支：`frontend/multi-page-dashboard`。

## 交付范围

- `/cohorts` 继续复用 `AnalysisPage`、`MetricCard`、`AnalyticsChart` 和 `PageState`。
- 三个筛选器严格对应 `age_group`、`gender`、`admission_type`；筛选值直接来自 API `options`，请求使用统一 `withQuery`，前端不拼接实体键、不聚合、不排序、不截断。
- 群体页始终提供“清空筛选”；加载新条件时清除旧指标和图表，合法未发布组合进入空态，服务失败进入错误态并提供 retry。
- 窄屏筛选改为两列自适应网格，控件允许收缩；分析分区保持接口返回顺序，桌面布局自然形成“主要疾病/严重程度”首行和“年龄结构”次行。
- fixture 补充契约要求的年龄结构分区；其年龄计数合计 2,101,588，与 fixture 群体记录数一致。真实快照仍以 #55 的独立证据为准。

## 验收矩阵

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| U-01 | 首屏布局 | PASS：标题、三联筛选、清空、5 个 KPI、3 个图表和页脚均可见 | [`cohorts-fixture-desktop.png`](l4-page/cohorts-fixture-desktop.png) |
| U-02 | API 字段与单位 | PASS：5 个指标、`diseases/severity/age` 三个 section、版本和生成时间原样展示 | [`api-summary.json`](l3-api/api-summary.json) |
| U-03 | 四态与 retry | PASS：fixture success、合法空组合、服务错误均复现；空/错态不保留旧图表 | [`browser-summary.json`](l4-page/browser-summary.json) |
| U-04 | 筛选行为 | PASS：三字段白名单由后端校验；组合筛选按冻结参数顺序请求，未发布组合返回合法空结果 | [`api-summary.json`](l3-api/api-summary.json)、`backend/tests/test_analytics_api.py` |
| U-05 | 响应式 | PASS：390px 测量 `clientWidth=390`、`scrollWidth=390`；顶部导航保留自身横向滚动 | [`cohorts-fixture-mobile.png`](l4-page/cohorts-fixture-mobile.png)、[`browser-summary.json`](l4-page/browser-summary.json) |
| U-06 | 安全边界 | PASS：只渲染预定义 section 类型；页面没有数据库、聚合、排序、截断或执行服务端配置 | `AnalysisPage.vue`、`AnalyticsChart.vue` |
| U-07 | 真实交接 | PASS：页面不区分 fixture/真实 payload，仅按统一结构渲染；真实 data_version、168 个群体键和 MySQL 一致性见 [#55 证据](../55/README.md) | #55 Resolution、`docs/07-terminal-product-contract.md` |

## 构建与回归

```text
cd frontend; npm ci; npm run build
PASS — Vite 8.2.1，621 modules transformed

python -m pytest backend/tests data/tests -q
60 passed, 3 skipped

git diff --check
PASS
```

fixture 只用于页面结构、四态和响应式复现，不替代真实全量结论。真实批次为 `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，由 #55 的数据/MySQL证据负责来源和跨层一致性。
