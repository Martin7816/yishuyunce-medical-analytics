# 数据与 API 交接清单

> #106 已把 #105 的视觉需求冻结为统一快照和 API 的正式输入。`fixture:` 只表示联调工件；真实全量结果必须同时提供 PySpark、独立核对、MySQL 和 API 读回证据。

## 1. 已确认的输入边界

来源代码 `data/src/run_full_analytics_pyspark.py` 已把以下原始列映射到统一清洗帧；设计只引用这些已出现的字段：

| 清洗字段 | 原始列 | 类型/处理 | 可用于 |
|---|---|---|---|
| `facility_id` | `Permanent Facility Id`（兼容 `Facility ID`） | 字符串；按 ID 聚合 | 医院关系、医院筛选 |
| `facility` | `Facility Name` | 字符串；仅展示，不作唯一键 | 医院名称 |
| `age` | `Age Group` | 有限字符串 | 群体筛选、风险热力横轴 |
| `diagnosis_code` / `diagnosis` | `CCSR Diagnosis Code` / `CCSR Diagnosis Description` | 字符串；诊断描述首尾清洗，空值不参与疾病排行 | 疾病筛选和分组 |
| `severity` | `APR Severity of Illness Description` | 有限字符串 | 医院指标、费用/风险分组 |
| `mortality` | `APR Risk of Mortality` | 字符串 | 现有风险分布；不解释为个人风险 |
| `los` | `Length of Stay` | 数值；`120 +` 映射 120，并保留 `los_capped=true` | 费用关系 x 轴、住院时长指标 |
| `charges` | `Total Charges` | 去千分位，非负金额 | 收费指标/关系 y 轴 |
| `costs` | `Total Costs` | 去千分位，非负金额 | 成本指标/对照 |
| `emergency` | `Emergency Department Indicator` | `Y/N` | 急诊率 |
| `payment` | `Payment Typology 1` | 有限字符串 | 支付方式页面 |
| `record_count` | 一行有效住院出院记录 | 每条记录计数一次，不按患者去重 | 所有关系图点/格的分母 |

业务术语必须继续使用“住院出院记录”和“病例量”，不使用“患者数”“患病人数”或“患者风险”。

## 2. 三个冻结聚合交接

### 2.1 医院运营关系

**设计目的**：在同一统计边界内观察医疗机构汇总指标的分布，并支持两家医院精确对照。

- 主图：`scatter`，每个点是一个 `facility_id` 聚合结果；`x=avg_los`（天）、`y=avg_charges`（美元）、`size=case_count`（条）、`group=severe_rate`（0—1），不发送原始记录；
- 关系图按病例量降序、机构编号升序最多返回 50 个点；点数不足不伪造趋势，仍返回服务端摘要和 table fallback；
- 对照图：沿用现有 `facility_a`、`facility_b`、`metric` 白名单，以相同单位的 `grouped_bar` 展示两家机构；两家机构相同时维持现有参数错误；未指定筛选时默认展示已发布机构枚举前两项的病例量对照；
- 聚合键必须是 `facility_id`，`facility` 只用于显示。排序以 `case_count` 降序、`facility_id` 稳定兜底；
- 文案只能说“汇总指标呈现关系/差异”，不能说某医院导致收费或住院时长变化。

### 2.2 费用 × 住院时长关系

**设计目的**：在费用页面展示收费和住院时长的分组关系，同时保留收费/成本的现有分位数指标。

- 主图：`scatter`，`x=平均住院时长`（天）、`y=平均收费`（美元）、`size=record_count`（条），并附 `cost` 和 `high_cost_rate`；每个点必须由后端按固定分组生成；
- 分组固定为 `los` 分箱 × `severity`：`0-1天`、`2-3天`、`4-6天`、`7-13天`、`14-29天`、`30-59天`、`60-119天`、`120天及以上`，缺失严重程度归入 `未分类`；收费 P75 是当前批次高费用率阈值，不能在前端重算；
- 服务端最多返回 500 个点；当前实现按合法筛选生成完整固定分组，空分组不造点，空筛选结果保留 section 的 `empty` 元数据；
- 同页保留现有 `quantiles` bar 和收费/成本 KPI；收费与成本若放在 `grouped_bar` 中必须共享美元单位，不能与住院时长共用数值轴；
- `los=0` 不参与单日金额；`120 +` 只按既有 120/capped 规则处理。收费是账面收费，成本是估算成本。

### 2.3 年龄 × 严重程度/风险热力矩阵

**设计目的**：显示有限年龄组与 APR 严重程度的群体结构，为风险 KPI 提供矩阵事实视图。

- heatmap 值固定为 `record_count`（条），横轴 `Age Group`，纵轴固定为 `Minor`、`Moderate`、`Major`、`Extreme`；这样不会把“严重程度”直接偷换成临床风险；
- 每格同时返回 `numerator`、`denominator`、`high_risk_rate`；分母是格内严重程度可判定记录，前端不得用整表或热力格自行推算；
- 每格返回 `x_label`、`y_label`、`value`、`unit`，需要比例时附 `numerator`/`denominator`；固定显示数值图例、格内数字/符号和完整矩阵表；
- 缺失组合保留合法行列并返回 `value=0`、`numerator=0`、`denominator=0`、`high_risk_rate=0`；不能用色块缺失让用户误以为没有该年龄组；
- 页面固定显示“群体统计，不构成个人诊断、治疗建议或因果判断”。

## 3. API 载体建议

为遵循奥卡姆剃刀原则，优先在现有只读接口的统一快照 payload 中增加已校验 section，不新增路由：

| 页面 | 复用接口 | 正式 section | 不新增的东西 |
|---|---|---|---|
| 医院关系 | `/api/v1/hospitals` | `facility_relation`、`facility_metric_comparison` | 不新增网络图服务、地图或自由 `group_by` |
| 费用关系 | `/api/v1/costs/overview` | `cost_los_relation` | 不传原始记录、不在浏览器按 bins 重算 |
| 风险热力 | `/api/v1/risks/overview` | `age_severity_matrix` | 不新增患者级接口、不把诊疗风险作为 API 字段 |

图表元数据、来源 key、摘要和 fallback 已纳入 #106 的白名单 section schema（见 `VISUALIZATION-CONTRACT.md`），不透传任意 ECharts option。响应仍保留 `code/data/trace_id`、`data_version`、`generated_at`，错误语义沿用 `docs/07-terminal-product-contract.md`。

## 4. 确定性洞察交接

每个关系 section 如需洞察，服务端返回：

```json
{
  "key": "cost_los_relation",
  "title": "收费与住院时长关系摘要",
  "summary": "当前筛选下的固定摘要，不包含因果推断。",
  "level": "info",
  "source_section": "cost_los_relation",
  "source_metric_keys": ["avg_los", "avg_charges", "record_count"],
  "data_version": "<同批版本>",
  "generated_at": "<同批 UTC 时间>",
  "boundary": "当前筛选下的聚合住院出院记录",
  "related_not_causal": true
}
```

摘要不由前端点位排序、颜色或回归线推导；没有可靠规则就返回空摘要并显示“暂无确定性洞察”。AI 页面引用这些摘要时必须继续展示工具轨迹、来源指标、版本和统计边界。

## 5. #106 必须补齐的验证证据

| 检查项 | 预期证据 |
|---|---|
| 字段与清洗 | PySpark stdout/快照显示字段、缺失、`120 +`、金额解析和版本 |
| 分组与分母 | 独立核对脚本或 pytest 输出；说明每点/格的记录数、分母和空组合 |
| 版本贯穿 | 同一 `data_version`/`generated_at` 出现在快照、MySQL、API 和 fixture |
| schema 安全 | shared contract 拒绝未知图表类型、未知视觉字段、NaN/无穷大和任意 option |
| API 状态 | 正常、合法空、非法参数、未发布、坏快照、数据库失败均有响应证据 |
| 下游可用 | fixture 能复现 success/empty/error，#107 不需要猜字段或单位 |

本文件的关系 section 是 #106 的正式交接；`fixture:` 仍只能证明契约和联调，Issue Resolution 只有在真实全量、MySQL/API 读回和独立核对证据齐全后，才能写成真实关系分析已完成。
