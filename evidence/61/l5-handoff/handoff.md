# #61 下游交接

## 页面入口

- 路由：`/costs`
- API：`GET /api/v1/costs/overview`
- 疾病白名单：`GET /api/v1/diseases` 的 `options.diagnoses`
- 医院白名单：`GET /api/v1/hospitals` 的 `options.facilities`
- 严重程度白名单：wildcard cost payload 的 `options.severity`

## 固定边界

前端按 API 返回的 metrics/sections 顺序和值直接渲染。`diagnosis_code` 与 `facility_id` 互斥，`severity` 可叠加；不在浏览器访问数据库、拼接快照键、重算费用/成本、排序或截断比较项。金额单位由服务结果携带并原样展示，页面保留 `data_version`、`generated_at` 和 fixture-only 警告。

真实 wildcard 已验收 14 个指标和 9 个 sections；诊断筛选 `BLD001` 返回 14 个指标和 7 个 sections；合法空组合继续展示标题、筛选和版本并隐藏空图表。#83 最终联调只需复用该路由并核对同一真实批次版本。
