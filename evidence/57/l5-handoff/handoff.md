# #57 下游交接

- 页面入口：`/cohorts`
- 共享交付分支：`frontend/multi-page-dashboard`
- 页面实现：`frontend/src/router.js`、`frontend/src/views/AnalysisPage.vue`、`frontend/src/style.css`
- 公共 renderer：`frontend/src/api/client.js`、`frontend/src/components/MetricCard.vue`、`frontend/src/components/AnalyticsChart.vue`、`frontend/src/components/PageState.vue`
- 接口：`GET /api/v1/cohorts/summary`
- 筛选白名单：`age_group`、`gender`、`admission_type`
- 真实交接版本：`sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，来源为 #55 的独立快照/MySQL 证据。

下游只需启动 Flask 和 Vite，打开 `/cohorts`；页面直接消费 `options`、`filters`、`metrics`、`sections`、`data_version` 和 `generated_at`，不需要自行拼接实体键或重算指标。合法但未发布的组合按 `200 + metrics=[] + sections=[]` 进入空态。
