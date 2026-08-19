# Issue #61 前端验收证据：医疗费用与成本分析

验收日期：2026-08-19（Asia/Shanghai）。交付分支：`frontend/multi-page-dashboard`；页面路由：`/costs`。

## 交付范围

- 费用页继续复用 `AnalysisPage`、`MetricCard`、`AnalyticsChart` 和 `PageState`，只消费 `GET /api/v1/costs/overview` 及疾病/医院索引的白名单 options。
- `diagnosis_code` 与 `facility_id` 互斥：选择一项后禁用另一项；`severity` 可叠加；请求仍由统一 `withQuery` 生成，页面不拼接 entity key、不聚合、不排序、不截断。
- 页面按接口返回顺序展示指标和 sections；金额/记录数使用千分位且最多两位小数，图表坐标轴、tooltip 和 table section 使用同一格式化边界；重点指标用视觉边框强调，不改变接口顺序或数值。
- 重新加载时清除旧指标和图表；合法空结果保留标题、描述、筛选和版本；错误态显示稳定错误类型并提供 retry；费用页始终提供“清空筛选”。
- 移动端筛选栏改为可收缩两列网格，正文不产生横向溢出；顶部导航自身横向滚动属于约定允许范围。

## 验收矩阵

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| U-01 | 首屏布局 | PASS：标题、统计说明、三项筛选、清空按钮、KPI 和首组图表层级清楚 | [`costs-real-desktop.png`](l4-page/costs-real-desktop.png) |
| U-02 | 正常数据 | PASS：真实 wildcard 返回 14 个指标、9 个 section；页面原样显示真实版本、时间、单位和接口顺序 | [`api-summary.json`](l3-api/api-summary.json)、[`costs-real-desktop.png`](l4-page/costs-real-desktop.png) |
| U-03 | 四态与 retry | PASS：fixture success、fixture 合法空组合、后端停止后的 error/retry 均复现；空/错态没有旧 KPI 或图表 | [`browser-summary.json`](l4-page/browser-summary.json)、[`costs-fixture-desktop.png`](l4-page/costs-fixture-desktop.png) |
| U-04 | 筛选行为 | PASS：疾病选项来自 `/diseases`，医院选项来自 `/hospitals`；真实选择 `BLD001` 后医院 select 为 disabled，响应保留 14 个指标和 7 个 section | [`api-summary.json`](l3-api/api-summary.json)、`AnalysisPage.vue` |
| U-05 | 响应式 | PASS：1280 CSS 宽度 `clientWidth=1265`、`scrollWidth=1265`；390 CSS 宽度 `clientWidth=375`、`scrollWidth=375`；顶部导航内部溢出允许 | [`browser-summary.json`](l4-page/browser-summary.json)、[`costs-real-mobile.png`](l4-page/costs-real-mobile.png) |
| U-06 | 安全边界 | PASS：只支持契约登记的 `bar/pie/table/status`，不执行 API 返回的代码，不访问数据库，不在客户端重算、排序、截断或换单位 | `AnalysisPage.vue`、`AnalyticsChart.vue` |
| U-07 | 真实联调 | PASS：页面真实成功批次为 `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，生成时间为 `2026-08-19T00:00:00.000000Z` | [`api-summary.json`](l3-api/api-summary.json)、[`costs-real-desktop.png`](l4-page/costs-real-desktop.png) |

## 构建与回归

详见 [`build-and-tests.txt`](l2-build/build-and-tests.txt)。截图中的 fixture 只用于四态和视觉联调；真实金额、版本与成本矩阵来源于运行中的 MySQL/API 快照，不把 fixture 当作真实结论。

## 下游交接

`#83` 及最终演示可直接使用 `/costs`。后端需继续保持 #59/#60 冻结的参数白名单、14 个指标、section 顺序、真实 `data_version/generated_at` 和合法空组合 `metrics=[]/sections=[]` 语义；前端不需要数据库连接或额外的成本计算模块。
