# #53 疾病画像分析前端验收证据

验收日期：2026-08-19

本次交付在共享分支 `frontend/multi-page-dashboard` 上完成，页面入口为 `/diseases`。前端复用 `AnalysisPage.vue`、`PageState.vue`、`AnalyticsChart.vue` 与统一 `apiRequest`，没有在客户端做分组、排序、截断、单位换算或数据库计算。

## 验收结论

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| U-01 首屏与疾病画像 | PASS | 夹具与真实全量快照均验证了 TOP10、单疾病选择器、7 个 KPI、年龄/性别/严重程度/死亡风险/常见操作/主要医院 6 个图表分区。 |
| U-02 API 与版本信息 | PASS | [`l3-api/api-summary.md`](l3-api/api-summary.md)；请求只使用 `GET /api/v1/diseases` 与 `GET /api/v1/diseases/{diagnosis_code}`，响应中的 `data_version`、`generated_at` 原样展示。 |
| U-03 四状态 | PASS | [`disease-loading.png`](l4-page/disease-loading.png)、[`disease-empty.png`](l4-page/disease-empty.png)、[`disease-error.png`](l4-page/disease-error.png) 及状态记录；错误状态包含稳定中文提示、错误码、trace_id、重试按钮，空状态保留筛选并提供清空操作。 |
| U-04 响应式 | PASS | [`l4-page`](l4-page) 中的 1280px 与 390px 视口截图；页面 `scrollWidth <= clientWidth`，仅顶部导航保留自身横向滚动。 |
| U-05 可访问性与稳定性 | PASS | 浏览器可通过 `combobox`、`button`、`alert`、`status` 语义定位；加载态有 `aria-busy`，图表有可访问名称；桌面/移动端控制台均无 error/warning。 |
| U-06 构建与 API 回归 | PASS | [`l2-build/build-and-tests.txt`](l2-build/build-and-tests.txt)：`npm run build` 通过，疾病 API 23 项、统一分析 API 21 项测试通过。 |
| U-07 交付与下游 | PASS | [`l5-handoff/handoff.md`](l5-handoff/handoff.md)；已记录共享分支、公共契约、真实快照版本与父 issue #50 的交接边界。 |

## 夹具与真实快照分离

- 夹具成功态使用 `fixture:sparcs_full_analytics:v1`，提供 2 个疾病选项，独立验证开发夹具页面与四状态。
- 真实快照成功态使用 `D:/HuaDi/analytics-output/issue47-real-full.json`，`data_version` 为 `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，提供 477 个诊断选项；索引和 `BLD001` 画像均返回 HTTP 200，并完整提供 6 个画像分区。
- 另行重放了当前 `.env` 的 MySQL 配置：`192.168.219.128:3306` TCP 探测为 `False`，API 返回 `503 DATABASE_UNAVAILABLE`。该结果已如实记录在 API 证据中，未将本地真实快照适配器成功冒充为在线 MySQL 成功；它属于父 issue #50/#52 的环境链路重验，不改变本前端对真实快照响应的验收结论。

## 页面截图

- 夹具：[`disease-fixture-desktop-profile-viewport.png`](l4-page/disease-fixture-desktop-profile-viewport.png)、[`disease-fixture-mobile-profile-viewport.png`](l4-page/disease-fixture-mobile-profile-viewport.png)
- 真实快照：[`disease-real-desktop-profile-viewport.png`](l4-page/disease-real-desktop-profile-viewport.png)、[`disease-real-mobile-profile-viewport.png`](l4-page/disease-real-mobile-profile-viewport.png)
- 状态：[`disease-loading.png`](l4-page/disease-loading.png)、[`disease-empty.png`](l4-page/disease-empty.png)、[`disease-error.png`](l4-page/disease-error.png)
