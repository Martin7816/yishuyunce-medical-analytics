# Issue #65 前端验收证据：病情严重程度与风险分析

验收日期：2026-08-19（Asia/Shanghai）。交付工作流：`frontend/multi-page-dashboard`；页面：`/risks`；接口：`GET /api/v1/risks/overview`。

## 交付范围

- 继续复用 `AnalysisPage`、`MetricCard`、`AnalyticsChart`、`PageState` 与统一请求客户端，没有新增页面专属状态框架。
- 年龄与疾病筛选只使用 API 枚举；前端只提交 `age_group`、`diagnosis_code`，不聚合、排序、截断或改写响应顺序和值。
- 黄色医疗边界提示在 loading/success/empty/error 四态均保留；fixture 版本另有明确联调警告，真实版本不显示 fixture 警告。
- 风险页桌面布局固定为严重程度/死亡风险并排、离院去向跨两列、高风险年龄/疾病并排；720px 以下变为单列。
- 横轴使用本地预定义的紧凑刻度文本，tooltip 仍显示完整值；没有执行服务端 ECharts/HTML/JavaScript 配置。

## 验收矩阵

| 编号 | 结果 | 证据 |
|---|---|---|
| U-01 布局层级 | PASS：标题、医疗边界、筛选、KPI、五分区和页脚顺序清楚 | [`risks-fixture-desktop.png`](l4-page/risks-fixture-desktop.png)、[`risks-real-desktop.png`](l4-page/risks-real-desktop.png) |
| U-02 正常数据 | PASS：真实 MySQL/API/UI 的指标、单位、section 顺序与版本一致 | [`api-summary.json`](l3-api/api-summary.json)、[`risks-real-filtered-desktop.png`](l4-page/risks-real-filtered-desktop.png) |
| U-03 四态与 retry | PASS：四态互斥；loading/empty/error 均无旧指标或图；错误显示稳定 code、trace_id 和 retry | [`browser-summary.json`](l4-page/browser-summary.json)、`risks-loading.png`、`risks-empty.png`、`risks-error.png` |
| U-04 筛选行为 | PASS：真实 5 个年龄枚举、477 个疾病枚举；快速切换后较晚返回的旧请求未覆盖最终结果 | [`browser-summary.json`](l4-page/browser-summary.json)、[`api-summary.json`](l3-api/api-summary.json) |
| U-05 响应式 | PASS：1280 与 390 视口正文均无横向溢出；仅顶部导航自身可横向滚动 | `risks-fixture-desktop.png`、[`risks-fixture-mobile.png`](l4-page/risks-fixture-mobile.png) |
| U-06 安全边界 | PASS：公共 renderer 只接受白名单 section；页面不访问数据库、不重算正式指标、不冒充 fixture | 源码 Review、fixture/真实截图对照 |
| U-07 真实联调 | PASS：真实 data_version 贯穿 API 与页面；真实无筛选及 `70 or Older + INF002` 均为 200 success | [`api-summary.json`](l3-api/api-summary.json)、[`risks-real-desktop.png`](l4-page/risks-real-desktop.png) |

## 构建与回归

见 [`build-and-tests.txt`](l2-build/build-and-tests.txt)：Vite build PASS，`63 passed, 6 skipped`，`git diff --check` PASS；浏览器控制台无 error/warning。

真实批次：`sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`。fixture 仅用于四态和响应式复现，未作为真实成功结论。
