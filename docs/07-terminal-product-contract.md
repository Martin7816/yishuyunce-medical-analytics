# 医数云策终局产品冻结契约

> 冻结日期：2026-08-18  
> 终局 Map：#37  
> 范围：10 个产品模块的公共实现边界

## 1. 公共快照

所有分析结果写入 `analysis_snapshot_result(module_key, entity_key, payload_json, data_version, generated_at)`。一次发布先删除旧快照，再写入完整新快照并核对行数；任一步失败必须回滚。`payload_json` 固定包含：

```json
{
  "title": "页面标题",
  "description": "统计边界",
  "options": {},
  "filters": {},
  "metrics": [{"key": "record_count", "label": "记录数", "value": 1, "unit": "条"}],
  "sections": [{"key": "ranking", "title": "排行", "type": "bar", "items": [{"name": "A", "value": 1}]}]
}
```

`options`、`filters` 可按页面省略。`section.type` 只允许前端预定义的 `bar`、`pie`、`table`、`status`；前端不执行快照或模型返回的 JavaScript/ECharts 配置。

联调快照必须使用 `fixture:` 版本前缀并在页面明确提示，不能作为真实分析、模型效果或最终验收证据。

### 1.1 Payload 结构约束

- payload 顶层只能出现 `title`、`description`、`options`、`filters`、`metrics`、`sections`；其中 `title`、`description`、`metrics`、`sections` 必须存在，其他字段不得通过数据库、API 或 fixture 扩展。
- `metrics[]` 只能包含 `key`、`label`、`value`、`unit`；`value` 必须是有限数字。`unit=条` 表示有效住院出院记录数，`unit=美元`/`美元/天` 表示金额，`unit=%` 的 `value` 使用 0—1 比例，页面统一乘 100 展示百分数。
- `sections[]` 只能包含 `key`、`title`、`type`、`items`。`bar`、`pie`、`table` 的 item value 为有限数字；`status` 的 item value 为状态字符串。未知类型、未知字段、NaN 和无穷大都拒绝发布。
- `options` 只承载有限枚举或非可执行模型元数据；模型版本、阈值和特征名放在 `options` 内，不能新增 `model_version`、`threshold_amount` 等 payload 顶层字段。`filters` 只记录已选择的白名单字符串。
- 数据发布器和 Flask 读取模块都使用同一份结构校验；校验失败分别阻止发布或返回 `SERVICE_RESULT_INVALID`，不把坏快照降级成假答案。

## 2. 数据口径

- CSV 只读取一次，清洗结果持久化后供全部聚合复用；
- `Total Charges`、`Total Costs` 去千分位后转 `decimal(20,2)`，解析失败或负值不进入正式费用聚合；
- `Length of Stay` 的 `120 +` 映射为 120，同时保留 `los_capped=true`；
- 编码字段按字符串保留，文本去除首尾空白；
- 原始记录不按患者去重；
- 全部快照共享输入 SHA-256 生成的 `data_version` 与同一 `generated_at`；
- 金额中位数和 P25/P75/P90 使用 `percentile_approx(..., accuracy=10000)` 并在页面说明；
- 真实 HDFS、Hive、MySQL 状态必须来自执行证据，未检查时写 `CHECK_REQUIRED`，不得伪造 `VERIFIED`。
- `generated_at` 固定为带 6 位微秒、以 `Z` 结尾的 UTC 字符串，例如 `2026-08-18T08:00:00.000000Z`；MySQL 的 `DATETIME(6)` 按 UTC 存储。
- fixture 的存储状态使用 `CHECK_REQUIRED`，本机任务状态使用 `FIXTURE_ONLY`；fixture 不得出现 `VERIFIED`、`PASS` 等会被误读为真实验收的状态。

### 2.1 枚举来源与 entity_key 顺序

筛选值只能来自下表对应的已发布 `options`，服务端按固定顺序拼接实体键；`*` 表示该维度未筛选。调用方不得自行改变顺序、编码或拼接符号。

| 模块 | entity_key 形式 | 筛选枚举来源 |
|---|---|---|
| 总览 | `overview` | 无 |
| 医院 | `index`；`profile:{facility_id}` | `hospitals/index.options.facilities` |
| 疾病 | `index`；`profile:{diagnosis_code}` | `diseases/index.options.diagnoses` |
| 群体 | `age={age_group}\|gender={gender}\|admission={admission_type}` | `cohorts` 的 `age_group`、`gender`、`admission_type` |
| 费用 | `diagnosis={diagnosis_code}\|facility={facility_id}\|severity={severity}` | 疾病/医院索引及 `costs` 的 `severity` |
| 风险 | `age={age_group}\|diagnosis={diagnosis_code}` | `risks` 的 `age_group`、疾病索引的 `diagnosis_code` |
| 支付 | `payment={payment_type}\|age={age_group}` | `payments` 的 `payment_type`、`age_group` |
| 数据质量 | `summary` | `data_version` 只能选择当前快照版本 |
| 高费用模型 | `metrics` | 无 |

合法但尚未发布的筛选仍返回 `200`，保留标题、描述、版本和时间，将 `metrics`、`sections` 置为空；非法参数、未知字段和非白名单值返回 `400`。

支付快照补充约定：`payments` 的 wildcard 记录键为
`payment=*|age=*`，其 `options.payment_type` 只来自清洗帧中的非空
`Payment Typology 1`，`options.age_group` 只来自清洗帧中的非空年龄组。
支付记录按当前键对应的有效住院出院记录计算 `record_count`，金额指标只使用
可解析且非负的 `Total Charges`；`avg_charges` 为算术平均，
`median_charges` 使用 `percentile_approx(charges, 0.5, 10000)`，单位均为美元。
`sections` 固定按 `payment`、`charges`、`age`、`diseases` 输出；其中支付方式、年龄和疾病
排行排除空分组并按 value 降序、name 升序，疾病严格 TOP10，支付方式费用只展示有有效收费的方式。
wildcard 和每个有限 `payment_type × age_group` 组合都必须有记录；无数据组合保留合法空
`metrics`/`sections`，不能省略。缺失支付字段仍计入 wildcard 的记录分母，但不进入支付方式排行。

`entity_key` 中的枚举值按发布的字符串原样保存，因此允许年龄等枚举值内部的普通空格（例如 `age=50 to 69|gender=*|admission=*`）；模块键和实体键仍禁止首尾空白、换行、回车和制表控制字符。请求 URL 中的空格按 HTTP 客户端规则编码，服务端解码后使用同一实体键顺序。

医院模块补充约束：`hospitals/index.options.facilities[].value` 和
`hospitals/profile:{facility_id}` 的 `facility_id` 均按字符串处理；医院画像的病例量
指标键固定为 `case_count`，平均金额的单位为 `美元`，比例指标的单位为 `%` 且值域为
`0—1`。医院排行和画像都以 `facility_id` 聚合，医院名称只作为展示标签，避免同名机构被合并。

## 3. API

| 模块 | 方法与路径 | 白名单参数 |
|---|---|---|
| 总览 | `GET /api/v1/dashboard/overview` | 无 |
| 医院 | `GET /api/v1/hospitals` | `facility_a`、`facility_b`、`metric` |
| 医院画像 | `GET /api/v1/hospitals/{facility_id}` | 无 |
| 疾病 | `GET /api/v1/diseases` | 无 |
| 疾病画像 | `GET /api/v1/diseases/{diagnosis_code}` | 无 |
| 群体 | `GET /api/v1/cohorts/summary` | `age_group`、`gender`、`admission_type` |
| 费用成本 | `GET /api/v1/costs/overview` | `diagnosis_code` 或 `facility_id` 二选一、`severity` |
| 病情风险 | `GET /api/v1/risks/overview` | `age_group`、`diagnosis_code` |
| 支付 | `GET /api/v1/payments/overview` | `payment_type`、`age_group` |
| 数据质量 | `GET /api/v1/data-quality/summary` | `data_version` |
| 模型指标 | `GET /api/v1/models/high-cost/metrics` | 无 |
| 单条预测 | `POST /api/v1/models/high-cost/predict` | 固定 JSON 字段 |
| AI 问答 | `POST /api/v1/ai/chat` | `message` |

响应统一为 `code/message/data/trace_id`，追踪编号同时写入 `X-Trace-ID`。未知参数、未知字段和非白名单值返回 400；合法但未产出聚合的筛选返回 200 空结果；整个模块未发布返回 503 `RESULT_NOT_READY`；数据库不可用返回 503；服务器缺少密钥或工件返回 500 配置错误。

### 3.1 错误码表

| HTTP | code | 语义 | data |
|---:|---|---|---|
| 400 | `INVALID_QUERY_PARAMETER` / `INVALID_REQUEST_FIELD` / `INVALID_REQUEST_FORMAT` | 参数、字段或请求格式不符合白名单 | `null` |
| 400 | `LEAKAGE_FIELD_FORBIDDEN` | 预测请求包含收费、成本、住院时长或出院后字段 | `null` |
| 405 | `METHOD_NOT_ALLOWED` | 使用未冻结的 HTTP 方法 | `null` |
| 503 | `RESULT_NOT_READY` | 合法模块尚未发布快照 | `null` |
| 503 | `DATABASE_UNAVAILABLE` | MySQL 连接或查询失败 | `null` |
| 503 | `UPSTREAM_SERVICE_ERROR` | DeepSeek 或工具调用失败 | `null` |
| 500 | `SERVER_MISCONFIGURED` | 缺少密钥、模型工件或数据源配置 | `null` |
| 500 | `SERVICE_RESULT_INVALID` | 快照未通过公共结构校验 | `null` |

错误消息不返回 SQL、数据库地址、密钥、堆栈或患者级内容；客户端按 HTTP 状态和 `code` 判断，不依赖 `message` 文案。

### 3.2 最小调用示例

```powershell
curl.exe 'http://127.0.0.1:5000/api/v1/dashboard/overview'
curl.exe 'http://127.0.0.1:5000/api/v1/cohorts/summary?age_group=50%20to%2069'
curl.exe -X POST 'http://127.0.0.1:5000/api/v1/models/high-cost/predict' `
  -H 'Content-Type: application/json' `
  -d '{"age_group":"50 to 69","gender":"F","race":"White","ethnicity":"Not Span/Hispanic","hospital_service_area":"New York City","facility_id":"1","admission_type":"Emergency","emergency_indicator":"Y"}'
```

调用者只需要学习上述路径、白名单参数、统一信封和版本/时间字段；不得在前端或 AI 工具中拼接 SQL、执行聚合或重排结果。

## 4. 模型与 AI

高费用标签是训练集 `Total Charges` 的 P75。训练随机种子固定为 `20260818`，算法为 PySpark ML Logistic Regression。允许特征只有年龄组、性别、种族、族裔、医院区域、机构编号、入院方式和急诊标志。收费、成本、住院时长、出院去向、手术和出院后字段在请求层与训练层均禁止。

AI 使用 `DEEPSEEK_API_KEY` 注入密钥、OpenAI 兼容 Chat Completions、20 秒超时、最多两次工具调用，不保存历史。工具只读取运营、医院、疾病、群体、费用、风险、支付和模型指标快照。返回内容必须附带工具轨迹、来源指标、数据版本与统计边界；上游失败直接返回错误。

## 5. 前端与关闭边界

固定路由为 `/overview`、`/hospitals`、`/diseases`、`/cohorts`、`/costs`、`/risks`、`/payments`、`/data-quality`、`/model`、`/assistant`。八个分析页复用统一页面渲染器、指标卡、图表和 loading/success/empty/error/retry；模型和 AI 保留必要专用交互。

当前代码和 fixture 测试通过只证明并行开发基线可用。任何父 Issue 只有在真实数据、MySQL、API、页面三层字段/单位/排序/版本一致且具备独立证据后才能关闭；AI 还必须通过真实 Key、超时、错误与断网验证。最终集成 #83 只有十个父 Issue、文档、演示材料和干净 `main` 复现全部完成后才能关闭。

## 6. 下游交接与受影响 Issue

| Issue | 直接使用的冻结内容 | 交接边界 |
|---|---|---|
| #39 | 快照 payload、版本/时间、entity_key 和事务发布规则 | 负责真实 CSV 清洗、全量聚合和 MySQL 发布证据 |
| #40 | 读取 adapter、参数白名单、响应信封和错误码 | 负责真实 API 查询与依赖失败复验，不在 API 重算 |
| #41 | 路由、section 类型、指标单位、四态和 fixture 提示 | 负责页面 renderer、响应式和浏览器证据，不把 fixture 当真实结论 |
| #42、#46、#50、#54、#58、#62、#66、#70 | 各分析模块的枚举、实体键和空结果语义 | 负责对应模块真实数据/API/UI 三层一致性 |
| #74、#78 | 模型与 AI 工具的输入、版本和事实边界 | 负责真实模型工件、Key、超时、断网和来源追踪验收 |
| #83 | 全部公共约束及其证据入口 | 负责最终联调、展示材料和干净 `main` 复现 |

下游遇到公共字段、单位、错误语义或 entity_key 冲突时，先回到 #38 说明影响；不得在子 Issue 中另起一套快照表、响应信封或筛选规则。
