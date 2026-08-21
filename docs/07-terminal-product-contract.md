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
  ],
  "insights": []
}
```

约束如下：

- 顶层只允许 `title`、`description`、`options`、`filters`、`metrics`、`sections`、`insights`；
- `title`、`description`、`metrics`、`sections` 必须存在；
- `metrics[]` 只允许 `key`、`label`、`value`、`unit`，数值必须有限；
- `%` 单位使用 0—1 的比例值，页面乘 100 展示；
- 普通 `sections[]` 只允许 `key`、`title`、`type`、`items`；`type` 只允许 `bar`、`pie`、`table`、`status`；
- 关系 `sections[]` 只允许 `grouped_bar`、`scatter`、`heatmap`，并必须携带白名单 `visual`：问题、坐标轴、单位、图例、Tooltip 字段、服务端摘要、table fallback 和 empty state；不接受任意 ECharts option、JavaScript、HTML、SQL 或 formatter；
- `grouped_bar` 每项是类别和 1—3 个同单位系列；`scatter` 每点是后端聚合的 `name/x/y/size/group`，费用关系可附 `cost/high_cost_rate`；`heatmap` 每格是 `x_label/y_label/value/unit`，比例需附分子、分母和正式比例字段；
- `insights[]` 由服务端确定性生成，必须指向当前 section，并返回 `source_metric_keys`、`data_version`、`generated_at`、`boundary` 和 `related_not_causal`；嵌套版本与时间必须和快照外层一致；
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

### 3.1 业务总体与比例分母

- **基础记录总体**是当前数据版本和筛选条件下纳入分析的全部住院出院记录。字段缺失不会触发全局删行，也不得把该总体表述为患者数。
- **适用记录总体**是按业务定义应填写某字段的基础记录集合，用于区分缺失与不适用；当前产品不因 `Birth Weight`、`Payment Typology 2/3` 等未使用字段改变业务总体。
- **指标有效总体**是具有该指标所需有效字段的适用记录集合。字段比例必须使用各自的指标有效总体，不能机械复用页面的基础记录总体。
- `Major/Extreme` 重症率以严重程度属于 `Minor`、`Moderate`、`Major`、`Extreme` 的记录为分母；空值和其他不可判定值既不作分子，也不视为非重症。
- 业务页面保留一个主业务总体，并在描述或图表标题中简要说明受影响指标的范围；完整的字段有效数与缺失数集中发布在 `data_quality/summary`，不在每个页面堆叠质量告警。
- 同一 `data_version` 和筛选条件下，比例分子、指标有效总体及对应分布 section 必须可对账；不同页面的基础总体可以因业务筛选不同而不同，但必须由实体键、筛选条件和上述口径唯一解释。
- `data_quality/summary` 在既有 `payload.options.audit` 中发布 `formula_version`、基础总体及其筛选条件、各业务字段的适用/有效/缺失数和急诊率、外科率、重症率的分子/分母；`data_version` 与 `generated_at` 仍使用快照文档和 API 既有元数据，不新增响应顶层字段。

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

医院以字符串 `facility_id` 聚合，医院名称只用于展示，避免同名机构合并。医院病例量指标键为 `case_count`。`facility_relation` 使用 `avg_los`、`avg_charges`、`case_count` 和 `severe_rate` 生成最多 50 个后端散点；双院比较只组合完整医院画像，不改变指标顺序、单位或数值，并以 `facility_metric_comparison` 返回同单位 `grouped_bar`。医院画像的 `severe_rate` 以该机构严重程度可判定记录为分母，并发布 `severity` 分区作为可对账的业务结构。

### 5.2 疾病

疾病索引提供诊断编码枚举和疾病病例量 TOP10；疾病画像以 `diagnosis_code` 定位。病例量表示基础住院出院记录数，不表示患者人数或患病率；画像中的 `severe_rate` 只使用严重程度可判定记录作分母。

### 5.3 住院记录群体

年龄组、性别和入院方式使用有限枚举。组合筛选描述住院出院记录的群体结构，不表示可识别患者队列；记录数保留当前筛选的基础记录总体，`severe_rate` 只使用其中严重程度可判定记录作分母。

### 5.4 费用与成本

`diagnosis_code` 与 `facility_id` 互斥，`severity` 可以与其中一个组合。指标包含记录数、收费/成本均值与分位数、收费成本差和单日金额。`cost_los_relation` 固定使用八个住院时长分箱和 `severity` 分组，缺失严重程度为 `未分类`，并以当前批次收费 P75 计算 `high_cost_rate`。单日金额只使用 `los > 0` 的记录。合法键包括未筛选、单疾病或单医院，并分别与严重程度组合；不生成疾病和医院同时指定的键。

### 5.5 病情风险

风险模块发布年龄、诊断及其组合。`severity_valid_count` 是当前筛选下严重程度可判定的记录数，`high_risk_count` 是其中 `Major`/`Extreme` 的记录数，`high_risk_rate` 以前者为分母并保持 0—1 比例。`age_severity_matrix` 固定返回年龄枚举×`Minor/Moderate/Major/Extreme` 的完整矩阵；合法空组合返回四个数值字段均为 0。高风险平均住院时长、收费和成本只使用 `Major`/`Extreme` 记录中各自可用的非负字段。风险页展示群体结构，不构成个人诊断、治疗建议或因果判断。

### 5.6 支付方式

支付模块发布未筛选键和支付方式×年龄组组合。`payment_type` 来自 `Payment Typology 1`，金额指标只使用可解析且非负的收费。支付方式、年龄和疾病排行排除空分组；疾病排行严格取十项。

### 5.7 数据质量

数据质量页集中发布基础记录总体、严重程度有效/缺失数，以及现有业务使用字段的有效记录数和非零缺失数。`Birth Weight`、`Payment Typology 2/3` 等未进入当前业务的字段不改变基础记录总体，也不进入业务页面。

### 5.8 高费用模型

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
