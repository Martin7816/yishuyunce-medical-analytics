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

## 2. 数据口径

- CSV 只读取一次，清洗结果持久化后供全部聚合复用；
- `Total Charges`、`Total Costs` 去千分位后转 `decimal(20,2)`，解析失败或负值不进入正式费用聚合；
- `Length of Stay` 的 `120 +` 映射为 120，同时保留 `los_capped=true`；
- 编码字段按字符串保留，文本去除首尾空白；
- 原始记录不按患者去重；
- 全部快照共享输入 SHA-256 生成的 `data_version` 与同一 `generated_at`；
- 金额中位数和 P25/P75/P90 使用 `percentile_approx(..., accuracy=10000)` 并在页面说明；
- 真实 HDFS、Hive、MySQL 状态必须来自执行证据，未检查时写 `CHECK_REQUIRED`，不得伪造 `VERIFIED`。

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

## 4. 模型与 AI

高费用标签是训练集 `Total Charges` 的 P75。训练随机种子固定为 `20260818`，算法为 PySpark ML Logistic Regression。允许特征只有年龄组、性别、种族、族裔、医院区域、机构编号、入院方式和急诊标志。收费、成本、住院时长、出院去向、手术和出院后字段在请求层与训练层均禁止。

AI 使用 `DEEPSEEK_API_KEY` 注入密钥、OpenAI 兼容 Chat Completions、20 秒超时、最多两次工具调用，不保存历史。工具只读取运营、医院、疾病、群体、费用、风险、支付和模型指标快照。返回内容必须附带工具轨迹、来源指标、数据版本与统计边界；上游失败直接返回错误。

## 5. 前端与关闭边界

固定路由为 `/overview`、`/hospitals`、`/diseases`、`/cohorts`、`/costs`、`/risks`、`/payments`、`/data-quality`、`/model`、`/assistant`。八个分析页复用统一页面渲染器、指标卡、图表和 loading/success/empty/error/retry；模型和 AI 保留必要专用交互。

当前代码和 fixture 测试通过只证明并行开发基线可用。任何父 Issue 只有在真实数据、MySQL、API、页面三层字段/单位/排序/版本一致且具备独立证据后才能关闭；AI 还必须通过真实 Key、超时、错误与断网验证。最终集成 #83 只有十个父 Issue、文档、演示材料和干净 `main` 复现全部完成后才能关闭。
