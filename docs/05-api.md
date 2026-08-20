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
  "data_version": "...",
  "generated_at": "..."
}
```

合法筛选没有记录时仍返回 `200`，保留标题、说明、筛选、版本和时间，`metrics` 与 `sections` 为空。

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

比较响应在 `data.comparison` 中按请求顺序返回完整医院画像。医院编码始终按字符串处理。

### 3.2 疾病

```http
GET /api/v1/diseases
GET /api/v1/diseases/NVS005
GET /api/v1/diseases/top10
```

画像路径中的 `diagnosis_code` 必须来自 `/diseases` 的 `options.diagnoses`。疾病病例量表示有效住院出院记录数，不表示患者人数或患病率。

### 3.3 住院记录群体

```http
GET /api/v1/cohorts/summary?age_group=50%20to%2069&gender=F&admission_type=Emergency
```

三个参数都可省略，取值来自基础响应的 `options.age_group`、`options.gender` 与 `options.admission_type`。

### 3.4 费用与成本

```http
GET /api/v1/costs/overview?diagnosis_code=BLD001&severity=Major
GET /api/v1/costs/overview?facility_id=1&severity=Major
```

`diagnosis_code` 与 `facility_id` 不能同时出现。`severity` 允许 `Minor`、`Moderate`、`Major`、`Extreme`。

### 3.5 病情风险

```http
GET /api/v1/risks/overview?age_group=70%20or%20Older&diagnosis_code=BLD001
```

参数可单独或组合使用。结果为群体统计，不构成个人诊断、治疗建议或因果判断。

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

`data_version` 只接受当前发布版本。

## 4. 高费用记录分类

### 4.1 模型指标

```http
GET /api/v1/models/high-cost/metrics
```

接口只读取已发布的 `high_cost_model/metrics` 快照，不在请求中重新训练或计算指标。成功响应的 `data` 包含模型版本、收费阈值、八个特征名、训练/测试规模、Accuracy、Precision、Recall、F1、AUC、混淆矩阵、`data_version` 和 `generated_at`。`model_version`、`threshold_amount`、`feature_names` 从快照的 `options` 中以只读方式展开。

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

请求必须是只包含上述八个字段的 JSON 对象；字段值必须是非空字符串，并按已发布工件的类别映射处理。工件提供 `OTHER` 桶时，未见过的类别归入 `OTHER`；没有 `OTHER` 桶的非法类别返回 `400 INVALID_REQUEST_FIELD`。

收费、成本、住院时长、出院去向、手术、目标标签和其他出院后字段会触发 `400 LEAKAGE_FIELD_FORBIDDEN`；普通未知字段返回 `400 INVALID_REQUEST_FIELD`。非 JSON 或非对象请求返回 `400 INVALID_REQUEST_FORMAT`。模型路径未发布返回 `503 RESULT_NOT_READY`，工件损坏、字段缺失或数值无效返回 `500 SERVER_MISCONFIGURED`。

服务首次成功预测时读取 `HIGH_COST_MODEL_PATH` 指向的 JSON 工件并缓存。工件必须提供 `intercept`、八个特征的 `feature_weights`、`model_version` 和 `data_version`；预测使用截距与类别权重计算 sigmoid，并返回 `prediction`、`probability`、`classification_threshold`、`threshold_amount`、归一化后的 `features`、版本信息、`fixture_only` 和运营分析边界。`fixture_only=true` 或 `fixture:` 版本只表示联调工件，不代表真实模型效果。

分类结果用于运营分析，不构成医疗判断。

## 5. AI 问答

```powershell
curl.exe -X POST http://127.0.0.1:5000/api/v1/ai/chat `
  -H 'Content-Type: application/json' `
  -d '{"message":"请概括当前运营情况，并说明引用的数据版本。"}'
```

请求体只允许非空 `message`。成功结果包含：

- `answer`：回答正文；
- `tool_trace`：工具名、执行状态和数据版本；
- `sources`：回答引用的汇总指标；
- `data_versions`：涉及的数据版本；
- `boundary`：统计与医疗安全边界；
- `chart`：可选的预定义图表数据。

AI 最多调用两次白名单工具，不执行自由 SQL，不读取原始住院明细，不保存多轮历史。缺少密钥、超时或上游失败时返回错误。

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
