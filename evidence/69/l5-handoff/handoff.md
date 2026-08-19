# #69 下游交接

- 页面入口：`/payments`。
- 接口：`GET /api/v1/payments/overview`。
- 筛选白名单：`payment_type`、`age_group`；选项直接取响应 `options`，页面不拼接实体键。
- 公共 renderer：`frontend/src/views/AnalysisPage.vue`、`frontend/src/components/MetricCard.vue`、`frontend/src/components/AnalyticsChart.vue`、`frontend/src/components/PageState.vue`。
- 真实交接版本：`sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，来源为 #67 的快照/MySQL 核对。

支付页按接口返回顺序直接展示 `payment`、`charges`、`age`、`diseases` 四个 section；不在浏览器 groupBy、排序、截断或换算正式指标。fixture 只用于并行联调和四态验收，会显示黄色提示；真实版本不会显示该提示。合法但未发布的筛选按 `200 + metrics=[] + sections=[]` 进入空态，失败按稳定错误码进入 error 并可 retry。
