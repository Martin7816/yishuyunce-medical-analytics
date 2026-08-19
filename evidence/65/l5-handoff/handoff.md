# #65 下游交接

- 页面：`/risks`
- 工作流分支：`frontend/multi-page-dashboard`
- 接口：`GET /api/v1/risks/overview`
- 白名单筛选：`age_group`、`diagnosis_code`
- 公共实现：`frontend/src/views/AnalysisPage.vue`、`frontend/src/components/MetricCard.vue`、`frontend/src/components/AnalyticsChart.vue`、`frontend/src/components/PageState.vue`
- 页面配置：`frontend/src/router.js` 的 `risks`
- 父 Issue：[#62](https://github.com/Martin7816/yishuyunce-medical-analytics/issues/62)

真实 MySQL、API 与页面已用同一 data_version 验收；fixture 四态和 1280/390 响应式另行验收。父 Issue #62 可使用本目录与 #63/#64 的独立 Resolution 做最终跨层一致性结论。
