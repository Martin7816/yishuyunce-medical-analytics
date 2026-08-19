# #53 API 与数据版本证据

## 真实全量快照适配器成功

来源：`D:/HuaDi/analytics-output/issue47-real-full.json`，通过现有 Flask `FixtureAnalyticsSnapshotRepository` 适配器读取；这不是客户端伪造数据，也不是在线 MySQL 的替代声明。

| 请求 | HTTP | code | data_version | generated_at | 关键内容 |
| --- | ---: | --- | --- | --- | --- |
| `GET /api/v1/diseases` | 200 | `OK` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` | `2026-08-18T12:00:00.000000Z` | 477 个诊断选项；`diagnosis_count`；`top10` |
| `GET /api/v1/diseases/BLD001` | 200 | `OK` | 同上 | 同上 | `record_count`、`avg_los`、`avg_charges`、`avg_costs`、`emergency_rate`、`surgical_rate`、`severe_rate`；`age`、`gender`、`severity`、`mortality`、`procedures`、`hospitals` |

前端实际请求保留了接口返回顺序和值；选择器只使用索引响应的 `diagnoses` 枚举。

## 夹具成功

夹具版本为 `fixture:sparcs_full_analytics:v1`，验证了 `GET /api/v1/diseases` 的 TOP10 首屏及 `GET /api/v1/diseases/NVS005` 的完整画像，页面提示“当前显示固定联调快照，只用于并行开发与四态验收，不代表真实全量分析结论”。

## 在线 MySQL 配置重验

当前 `backend/.env` 配置为 `192.168.219.128:3306`。重验结果：

```text
Test-NetConnection -ComputerName 192.168.219.128 -Port 3306 -InformationLevel Quiet
False

GET http://127.0.0.1:5000/api/v1/diseases
HTTP 503
{"code":"DATABASE_UNAVAILABLE","data":null,"message":"The data service is temporarily unavailable.","trace_id":"b7b06d6e-46fd-407a-8771-2724b028cca1"}
```

错误响应满足公共错误契约；前端会清除旧图表，保留模块标题/筛选骨架，展示稳定中文错误文案、错误码、trace_id 和重试按钮。
