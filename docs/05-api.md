# 医数云策 API 契约

Flask API 为网页和 AI 工具提供统一的住院运营汇总结果。除高费用记录预测和 AI 问答外，分析接口均为只读 GET 请求。接口不读取原始 CSV，不在路由中重新聚合或修补快照。

基础地址：`http://127.0.0.1:5000/api/v1`

## 1. 接口索引

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 应用存活检查 |
| GET | `/dashboard/overview` | 运营驾驶舱 |
| GET | `/hospitals` | 医院排行或双院比较 |
| GET | `/hospitals/{facility_id}` | 单院画像 |
| GET | `/diseases` | 疾病排行与疾病枚举 |
| GET | `/diseases/{diagnosis_code}` | 单病种画像 |
| GET | `/diseases/top10` | 疾病病例量 TOP10 |
| GET | `/cohorts/summary` | 住院记录群体分析 |
| GET | `/costs/overview` | 费用与成本分析 |
| GET | `/risks/overview` | 病情严重程度与风险分析 |
| GET | `/payments/overview` | 支付方式分析 |
| GET | `/data-quality/summary` | 数据质量和任务状态 |
| GET | `/models/high-cost/metrics` | 高费用模型指标 |
| POST | `/models/high-cost/predict` | 单条住院记录的高费用分类 |
| POST | `/ai/chat` | 受控 AI 问答 |

## 2. 响应结构

### 2.1 成功

```json
{
  "code": "OK",
  "message": "success",
  "data": {},
  "trace_id": "4f0d..."
}
```

HTTP 响应头 `X-Trace-ID` 与正文 `trace_id` 相同。分析接口的 `data` 通常包含：

```json
{
  "title": "页面标题",
  "description": "统计边界",
  "options": {},
  "filters": {},
  "metrics": [],
  "sections": [],
  "insights": [],
  "data_version": "...",
  "generated_at": "..."
}
```

合法筛选没有记录时仍返回 `200`，保留标题、说明、筛选、版本和时间，`metrics`、`sections` 与 `insights` 为空。

关系 section 只允许 `grouped_bar`、`scatter`、`heatmap`。它们必须使用后端返回的有限 `visual` 元数据和 table fallback；浏览器不得读取原始 CSV、执行 SQL、按分箱重算或透传任意 ECharts option。`insights[]` 是服务端确定性摘要，必须指向当前 section，并带来源指标、版本、生成时间、统计边界和 `related_not_causal`。

### 2.2 错误

```json
{
  "code": "INVALID_QUERY_PARAMETER",
  "message": "The query parameter is not supported.",
  "data": null,
  "trace_id": "4f0d..."
}
```

| HTTP | code | 含义 |
|---:|---|---|
| 400 | `INVALID_QUERY_PARAMETER` | 查询参数、重复参数或枚举值不合法 |
| 400 | `INVALID_REQUEST_FIELD` | JSON 字段不合法 |
| 400 | `INVALID_REQUEST_FORMAT` | 请求体格式不合法 |
| 400 | `LEAKAGE_FIELD_FORBIDDEN` | 预测请求包含禁止的泄漏字段 |
| 404 | `NOT_FOUND` | 路径不存在 |
| 405 | `METHOD_NOT_ALLOWED` | HTTP 方法不受支持 |
| 503 | `RESULT_NOT_READY` | 模块快照尚未发布 |
| 503 | `DATABASE_UNAVAILABLE` | MySQL 不可用 |
| 503 | `UPSTREAM_SERVICE_ERROR` | DeepSeek 或工具调用失败 |
| 500 | `SERVER_MISCONFIGURED` | 服务缺少数据源、模型或密钥配置 |
| 500 | `SERVICE_RESULT_INVALID` | 已读取结果不符合公共契约 |

错误消息不返回 SQL、数据库地址、凭证、密钥、堆栈或住院明细。

## 3. 只读分析接口

只读接口拒绝请求体、未知参数、重复参数和非 GET 方法。筛选枚举来自对应索引或基础快照的 `options`。

### 3.1 医院

```http
GET /api/v1/hospitals
GET /api/v1/hospitals?facility_a=1&facility_b=2&metric=avg_charges
GET /api/v1/hospitals/1
```

`facility_a` 与 `facility_b` 必须不同。`metric` 允许：

- `case_count`
- `avg_los`
- `avg_charges`
- `avg_costs`
- `emergency_rate`
- `severe_rate`

比较响应在 `data.comparison` 中按请求顺序返回完整医院画像，并在 `data.sections` 中返回同单位的 `facility_metric_comparison` grouped bar；未指定比较筛选时，医院索引仍提供 `facility_relation` scatter 和默认机构病例量对照。医院编码始终按字符串处理；医院画像的 `severe_rate` 以严重程度可判定记录为分母，`severity` 分区用于对账。

### 3.2 疾病

```http
GET /api/v1/diseases
GET /api/v1/diseases/NVS005
GET /api/v1/diseases/top10
```

画像路径中的 `diagnosis_code` 必须来自 `/diseases` 的 `options.diagnoses`。疾病病例量表示基础住院出院记录数，不表示患者人数或患病率；画像中的 `severe_rate` 只使用严重程度可判定记录作分母。

### 3.3 住院记录群体

```http
GET /api/v1/cohorts/summary?age_group=50%20to%2069&gender=F&admission_type=Emergency
```

三个参数都可省略，取值来自基础响应的 `options.age_group`、`options.gender` 与 `options.admission_type`。记录数表示当前筛选的基础记录总体，`severe_rate` 只使用该总体中严重程度可判定记录作分母。

### 3.4 费用与成本

```http
GET /api/v1/costs/overview?diagnosis_code=BLD001&severity=Major
GET /api/v1/costs/overview?facility_id=1&severity=Major
```

`diagnosis_code` 与 `facility_id` 不能同时出现。`severity` 允许 `Minor`、`Moderate`、`Major`、`Extreme`。

响应中的 `cost_los_relation` 按固定住院时长分箱（`0-1天`、`2-3天`、`4-6天`、`7-13天`、`14-29天`、`30-59天`、`60-119天`、`120天及以上`）和严重程度生成聚合散点；缺失严重程度为 `未分类`，`high_cost_rate` 的阈值为当前批次收费 P75。前端不重算这些关系。

### 3.5 病情风险

```http
GET /api/v1/risks/overview?age_group=70%20or%20Older&diagnosis_code=BLD001
```

参数可单独或组合使用。指标按 `severity_valid_count`、`high_risk_count`、`high_risk_rate`、`avg_los`、`avg_charges`、`avg_costs` 发布，其中 `high_risk_rate` 以前者为分母。结果为群体统计，不构成个人诊断、治疗建议或因果判断。

`age_severity_matrix` 固定返回已发布年龄枚举×`Minor/Moderate/Major/Extreme` 的完整 heatmap；每格返回记录数、分子、分母和 `high_risk_rate`，合法空组合均返回 0，不由前端决定分母。

### 3.6 支付方式

```http
GET /api/v1/payments/overview?payment_type=Medicare&age_group=70%20or%20Older
```

取值来自基础响应的 `options.payment_type` 与 `options.age_group`。

### 3.7 数据质量

```http
GET /api/v1/data-quality/summary
GET /api/v1/data-quality/summary?data_version=<当前响应中的版本>
```

`data_version` 只接受当前发布版本。该页面集中展示基础记录总体、严重程度有效/缺失数，以及当前业务使用字段的有效记录数和非零缺失数；`data.options.audit` 还提供适用数、有效数、缺失数、比例分子/分母、筛选条件和 `formula_version`，`data_version` 与 `generated_at` 继续使用既有响应元数据。其他业务页面只保留简要口径说明。

#### Issue #72 后端交接

路由只读取统一快照服务的 `data_quality/summary`（`module_key=data_quality`、`entity_key=summary`），不读取 CSV、HDFS 或 MySQL，不重新聚合、排序、截断或触发任务。fixture 和 MySQL 适配器都通过 `AnalyticsSnapshotService.get(module_key, entity_key)` 读取同一 interface。

`data_version` 是唯一可选参数，只接受当前已发布版本；未知/重复参数、非法版本和 GET 请求体分别返回 `400 INVALID_QUERY_PARAMETER` 或 `400 INVALID_REQUEST_FORMAT`，`HEAD`、`OPTIONS`、`POST` 等返回 `405 METHOD_NOT_ALLOWED`。未发布快照和数据库故障分别返回 `503 RESULT_NOT_READY`、`503 DATABASE_UNAVAILABLE`；配置缺失和 payload 契约损坏分别返回 `500 SERVER_MISCONFIGURED`、`500 SERVICE_RESULT_INVALID`。所有响应使用统一 `code/message/data/trace_id` 信封，`X-Trace-ID` 与正文一致，错误 details 只包含安全字段名。

合法空 payload 保留 `data_version`、`generated_at`，并返回空的 `metrics`、`sections`，不把未知版本伪装成空结果。专项测试和真实批次交接证据见 [`evidence/72`](../evidence/72/README.md)；fixture 版本只证明接口契约，真实 MySQL/API 证据沿用 [`evidence/39/l3-api/real-mysql-summary.txt`](../evidence/39/l3-api/real-mysql-summary.txt)。

## 4. 高费用记录分类

### 4.1 模型指标

```http
GET /api/v1/models/high-cost/metrics
```

响应包含模型版本、阈值、特征名、评估指标、混淆矩阵、数据版本和统计边界。

### 4.2 预测

```powershell
curl.exe -X POST http://127.0.0.1:5000/api/v1/models/high-cost/predict `
  -H 'Content-Type: application/json' `
  -d '{"age_group":"50 to 69","gender":"F","race":"White","ethnicity":"Not Span/Hispanic","hospital_service_area":"New York City","facility_id":"1","admission_type":"Emergency","emergency_indicator":"Y"}'
```

只允许以下字段：

- `age_group`
- `gender`
- `race`
- `ethnicity`
- `hospital_service_area`
- `facility_id`
- `admission_type`
- `emergency_indicator`

收费、成本、住院时长、出院去向和出院后字段会触发 `LEAKAGE_FIELD_FORBIDDEN`。分类结果用于运营分析，不构成医疗判断。

## 5. AI 问答

### 5.1 请求

```powershell
curl.exe -X POST http://127.0.0.1:5000/api/v1/ai/chat `
  -H 'Content-Type: application/json' `
  -d '{"message":"请概括当前运营情况，并说明引用的数据版本。"}'
```

请求体必须是 JSON 对象且只能包含 `message`。服务端会先 trim，再要求 `message` 为 1—1000 个字符；非 JSON、JSON 非对象、缺少字段、额外字段、空白消息和超长消息分别返回 400。接口只接受 POST，GET、HEAD、OPTIONS 等方法返回 405。

### 5.2 成功响应

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "answer": "当前运营指标已汇总。",
    "tool_trace": [
      {
        "tool": "get_dashboard_overview",
        "status": "success",
        "data_version": "fixture:sparcs_full_analytics:v1"
      }
    ],
    "sources": [
      {
        "tool": "get_dashboard_overview",
        "title": "运营驾驶舱",
        "metrics": [
          {"key": "record_count", "label": "住院出院记录", "value": 100, "unit": "条"}
        ],
        "data_version": "fixture:sparcs_full_analytics:v1"
      }
    ],
    "data_versions": ["fixture:sparcs_full_analytics:v1"],
    "chart": {
      "type": "bar",
      "title": "运营驾驶舱",
      "items": [{"name": "住院出院记录", "value": 100}]
    },
    "report": {"title": "医数云策洞察简报", "printable": true},
    "boundary": "Aggregated inpatient discharge records; no patient-level diagnosis or causal claim."
  },
  "trace_id": "4f0d0000-0000-4000-8000-000000000000"
}
```

`data` 必须包含 `answer`、`tool_trace`、`sources`、`data_versions`、`chart`、`report` 和 `boundary`。`sources[]` 只输出 `tool`、`title`、`metrics`、`data_version`；成功至少有一个 source 和一个 data version。`chart.type` 只允许公共契约中的 `bar`、`pie`、`table`、`status`，图表项只能从来源指标生成。

单次问题第一轮最多调用两个固定白名单工具，工具参数必须为 `{}`；不执行自由 SQL、不读取住院明细、不保存多轮历史。多个 source 的版本不一致时，服务端保留每个 source 的 `data_version`，并在 `data_versions` 中列出全部版本，不合并或伪装成单一版本，交由验收阻断。

### 5.3 错误与安全边界

| 场景 | HTTP | code |
|---|---:|---|
| 非 JSON 或 JSON 非对象 | 400 | `INVALID_REQUEST_FORMAT` |
| 缺少/额外字段、空消息、消息超过 1000 字符 | 400 | `INVALID_REQUEST_FIELD` |
| 非 POST 方法 | 405 | `METHOD_NOT_ALLOWED` |
| `DEEPSEEK_API_KEY` 缺失 | 500 | `SERVER_MISCONFIGURED` |
| DeepSeek 超时、HTTP/断网、坏响应、空回答或白名单工具失败 | 503 | `UPSTREAM_SERVICE_ERROR` |

每个成功或错误响应都带 `trace_id`，并通过 `X-Trace-ID` 响应头返回同一值。错误响应的 `data` 为 `null`，不返回 API Key、Authorization、用户 prompt、SQL、堆栈、数据库地址、口令或住院明细；真实链路证据只记录脱敏状态码、耗时和工具名。

### 5.4 #81 前端交接

前端按统一信封读取 `data.answer`、`data.tool_trace`、`data.sources`、`data.data_versions`、`data.chart`、`data.report` 和 `data.boundary`；错误页按 HTTP 状态和 `code` 处理 `INVALID_REQUEST_FORMAT`、`INVALID_REQUEST_FIELD`、`METHOD_NOT_ALLOWED`、`SERVER_MISCONFIGURED` 与 `UPSTREAM_SERVICE_ERROR`，并展示 `trace_id` 和重试入口。前端不得渲染未经过白名单校验的图表配置，也不得把错误详情或 Key 写入页面日志。

## 6. 数据源配置

联调模式：

```dotenv
TOP10_DATA_SOURCE=fixture
ANALYTICS_DATA_SOURCE=fixture
```

真实模式：

```dotenv
TOP10_DATA_SOURCE=mysql
ANALYTICS_DATA_SOURCE=mysql
MYSQL_HOST=<地址>
MYSQL_PORT=3306
MYSQL_USER=<只读账号>
MYSQL_PASSWORD=<密码>
MYSQL_DATABASE=medical_analytics
HIGH_COST_MODEL_PATH=<模型工件路径>
```

完整环境配置与启动命令见 [开发与运行手册](04-development-and-runbook.md)。公共 Payload、实体键和错误语义见 [公共产品契约](07-terminal-product-contract.md)。
