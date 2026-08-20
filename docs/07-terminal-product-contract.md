# 医数云策公共产品契约

本文件定义所有分析模块共同遵守的数据结构、筛选键、接口语义和安全边界。模块实现和验收材料引用这些约定，不各自定义另一套格式。

## 1. 统一分析快照

MySQL 表 `analysis_snapshot_result` 使用 `(module_key, entity_key)` 定位一条汇总结果，并保存：

- `payload_json`：页面所需的标题、说明、指标、分区和选项；
- `data_version`：输入数据版本；
- `generated_at`：UTC 生成时间。

一次发布写入一个完整批次。同批记录使用同一个 `data_version` 和 `generated_at`；发布失败时事务回滚。

## 2. Payload

```json
{
  "title": "页面标题",
  "description": "统计边界",
  "options": {},
  "filters": {},
  "metrics": [
    {"key": "record_count", "label": "住院出院记录", "value": 1, "unit": "条"}
  ],
  "sections": [
    {
      "key": "ranking",
      "title": "排行",
      "type": "bar",
      "items": [{"name": "A", "value": 1}]
    }
  ]
}
```

约束如下：

- 顶层只允许 `title`、`description`、`options`、`filters`、`metrics`、`sections`；
- `title`、`description`、`metrics`、`sections` 必须存在；
- `metrics[]` 只允许 `key`、`label`、`value`、`unit`，数值必须有限；
- `%` 单位使用 0—1 的比例值，页面乘 100 展示；
- `sections[]` 只允许 `key`、`title`、`type`、`items`；
- `type` 只允许 `bar`、`pie`、`table`、`status`；
- `options` 保存筛选枚举或不可执行的模型元数据；
- `filters` 回显已接受的白名单筛选；
- 未知字段、未知图表类型、NaN 和无穷大均拒绝发布或读取。

联调快照使用 `fixture:` 版本前缀，并在页面明确标记。

## 3. 数据口径

- 原始 CSV 在一次任务中读取一次，清洗结果持久化后供各模块聚合；
- `Total Charges` 与 `Total Costs` 去除千分位后按非负金额解析；
- `Length of Stay` 的 `120 +` 映射为 120，并保留 `los_capped=true`；
- 编码字段按字符串保存，文本去除首尾空白；
- 原始记录不按患者去重；
- 金额 P25、P50、P75、P90 使用 `percentile_approx(..., accuracy=10000)`；
- `generated_at` 使用带 6 位微秒、以 `Z` 结尾的 UTC 字符串；
- 真实 HDFS、Hive 和 MySQL 状态来自执行证据；没有执行检查时使用 `CHECK_REQUIRED`；
- 联调环境的存储状态不得使用会被理解为真实验收结论的 `VERIFIED` 或 `PASS`。

## 4. 模块键与筛选键

| 模块 | module_key | entity_key |
|---|---|---|
| 运营驾驶舱 | `dashboard` | `overview` |
| 医院索引 | `hospitals` | `index` |
| 医院画像 | `hospitals` | `profile:{facility_id}` |
| 疾病索引 | `diseases` | `index` |
| 疾病画像 | `diseases` | `profile:{diagnosis_code}` |
| 住院记录群体 | `cohorts` | `age={age_group}|gender={gender}|admission={admission_type}` |
| 费用与成本 | `costs` | `diagnosis={diagnosis_code}|facility={facility_id}|severity={severity}` |
| 病情风险 | `risks` | `age={age_group}|diagnosis={diagnosis_code}` |
| 支付方式 | `payments` | `payment={payment_type}|age={age_group}` |
| 数据质量 | `data_quality` | `summary` |
| 高费用模型指标 | `high_cost_model` | `metrics` |

`*` 表示该维度未筛选。筛选值来自已发布 `options`，服务端按表中的固定顺序组成实体键。普通空格可以出现在枚举值中；模块键和实体键禁止首尾空白、换行、回车和制表符。

合法枚举组合没有数据时保留可读标题、说明、筛选、版本和时间，`metrics` 与 `sections` 为空。非法枚举或未知参数返回参数错误。

## 5. 模块约束

### 5.1 医院

医院以字符串 `facility_id` 聚合，医院名称只用于展示，避免同名机构合并。医院病例量指标键为 `case_count`。双院比较只组合完整医院画像，不改变指标顺序、单位或数值。

### 5.2 疾病

疾病索引提供诊断编码枚举和疾病病例量 TOP10；疾病画像以 `diagnosis_code` 定位。病例量表示有效住院出院记录数，不表示患者人数或患病率。

### 5.3 住院记录群体

年龄组、性别和入院方式使用有限枚举。组合筛选描述住院出院记录的群体结构，不表示可识别患者队列。

### 5.4 费用与成本

`diagnosis_code` 与 `facility_id` 互斥，`severity` 可以与其中一个组合。指标包含记录数、收费/成本均值与分位数、收费成本差和单日金额。单日金额只使用 `los > 0` 的记录。合法键包括未筛选、单疾病或单医院，并分别与严重程度组合；不生成疾病和医院同时指定的键。

### 5.5 病情风险

风险模块发布年龄、诊断及其组合。`high_risk_rate` 使用当前筛选记录作分母并保持 0—1 比例。风险页展示群体结构，不构成个人诊断、治疗建议或因果判断。

### 5.6 支付方式

支付模块发布未筛选键和支付方式×年龄组组合。`payment_type` 来自 `Payment Typology 1`，金额指标只使用可解析且非负的收费。支付方式、年龄和疾病排行排除空分组；疾病排行严格取十项。

### 5.7 高费用模型

高费用阈值取训练集 `Total Charges` 的 P75，随机种子为 `20260818`，算法为 PySpark ML Logistic Regression。允许特征为年龄组、性别、种族、族裔、医院区域、机构编号、入院方式和急诊标志。收费、成本、住院时长、出院去向和出院后字段在训练层与请求层均禁止。

## 6. API

| 方法 | 路径 | 白名单参数 |
|---|---|---|
| GET | `/api/v1/health` | 无 |
| GET | `/api/v1/dashboard/overview` | 无 |
| GET | `/api/v1/hospitals` | `facility_a`、`facility_b`、`metric` |
| GET | `/api/v1/hospitals/{facility_id}` | 无 |
| GET | `/api/v1/diseases` | 无 |
| GET | `/api/v1/diseases/{diagnosis_code}` | 无 |
| GET | `/api/v1/diseases/top10` | 无 |
| GET | `/api/v1/cohorts/summary` | `age_group`、`gender`、`admission_type` |
| GET | `/api/v1/costs/overview` | `diagnosis_code` 或 `facility_id`、`severity` |
| GET | `/api/v1/risks/overview` | `age_group`、`diagnosis_code` |
| GET | `/api/v1/payments/overview` | `payment_type`、`age_group` |
| GET | `/api/v1/data-quality/summary` | `data_version` |
| GET | `/api/v1/models/high-cost/metrics` | 无 |
| POST | `/api/v1/models/high-cost/predict` | 固定 JSON 字段 |
| POST | `/api/v1/ai/chat` | `message` |

响应统一使用：

```json
{
  "code": "OK",
  "message": "success",
  "data": {},
  "trace_id": "..."
}
```

追踪编号同时写入 `X-Trace-ID`。客户端根据 HTTP 状态与 `code` 判断结果，不依赖 `message` 文案。

## 7. 错误语义

| HTTP | code | 含义 |
|---:|---|---|
| 400 | `INVALID_QUERY_PARAMETER` | 查询参数不符合白名单 |
| 400 | `INVALID_REQUEST_FIELD` | JSON 字段不符合白名单 |
| 400 | `INVALID_REQUEST_FORMAT` | 请求格式不合法 |
| 400 | `LEAKAGE_FIELD_FORBIDDEN` | 预测请求包含禁止的泄漏字段 |
| 405 | `METHOD_NOT_ALLOWED` | HTTP 方法不受支持 |
| 503 | `RESULT_NOT_READY` | 模块结果尚未发布 |
| 503 | `DATABASE_UNAVAILABLE` | MySQL 连接或查询失败 |
| 503 | `UPSTREAM_SERVICE_ERROR` | DeepSeek 或工具调用失败 |
| 500 | `SERVER_MISCONFIGURED` | 服务缺少必要配置 |
| 500 | `SERVICE_RESULT_INVALID` | 快照或上游结果不符合契约 |

错误消息不得包含 SQL、数据库地址、口令、密钥、堆栈或住院明细。

## 8. 前端与 AI

前端固定提供 `/overview`、`/hospitals`、`/diseases`、`/cohorts`、`/costs`、`/risks`、`/payments`、`/data-quality`、`/model` 和 `/assistant`。八个分析页复用公共渲染器，模型和 AI 使用各自必要的交互。

AI 使用 DeepSeek 的 OpenAI 兼容 Chat Completions 接口，超时 20 秒，单次问题最多调用两次白名单工具，不保存历史。回答必须包含工具轨迹、来源指标、数据版本和统计边界；依赖失败时返回错误，不生成无来源内容。