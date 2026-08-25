# AI 分析质量契约

本文件描述 AI 问答在后端的分析质量边界。它不改变 `/api/v1/ai/chat` 的外层字段，也不改变现有八个白名单工具。

## 处理链路

问答目前有两条受控路径：旧版快照工具路径，以及面向结构化问题的新版语义分析路径。两条路径都不允许模型直接访问数据库或生成 SQL。

新版语义分析路径为：

1. Deterministic intent layer 识别通用的维度、指标、筛选、排序、分布和比较意图，而不是匹配完整句子；例如“50岁男性最容易得什么病”会映射为 `age_group=50 to 69`、`gender=M`、按 `diagnosis` 的 `case_count` 降序排名。单个年龄会明确提示已按发布年龄组粗化。
2. DeepSeek Planner 只返回 `query_analytics-v1` 结构化计划；后端再次执行 QueryPlanValidator 和 SafeQueryCompiler。
3. 只读 aggregate query repository 使用服务端白名单维度、指标和绑定参数查询当前 ACTIVE 聚合批次。
4. Query Evidence Adapter 将结果转成 Safe Evidence，Evidence Answer Generator 只依据证据生成结构化回答，并由服务端校验引用、数字和统计边界。

当外部模型暂时不可用时，新版路径还有两个受限恢复点：

- 对“医院/疾病排名、年龄/性别筛选、病例量、平均费用”等高置信问题，后端可以从确定性意图生成小范围语义计划；该计划仍必须通过相同的 QueryPlanValidator 和 SafeQueryCompiler，不能生成 SQL，也不能扩大数据能力。
- 如果模型总结超时、返回非法结构或未通过证据校验，后端可以直接从 Safe Evidence 的分组和值生成保守摘要，并保留原有证据 ID、数据版本和限制说明。该摘要不计算新比例、差值或总量。

结果展示类型也由已识别意图决定：排名使用 bar，分布使用 pie，对比使用 grouped_bar，多指标关系使用 scatter。这个选择只改变证据投影和图表形状，不改变查询权限。

旧版快照工具路径仍然保留，用于整体运营概况等未进入语义查询能力的自然语言问题：

1. Routing Prompt 接收用户原问题，只选择一个最直接相关的白名单工具；只有明确包含两个不同主题时才选择两个工具。工具参数固定为空对象 `{}`。
2. 后端执行工具并通过 `ai_evidence.py` 建立安全证据。证据只保留快照标题、指标、允许的 sections/insights、数据版本、统计边界和确定性 derived facts。
3. 后端计算 `answerability`：`answerable`、`partially_answerable`、`unsupported` 或 `unsafe`。
4. Analysis Prompt 接收原问题、工具结果、安全证据、derived facts、answerability 和限制，回答原问题，而不是复述整个快照。

新版路径的 DeepSeek 规划和证据回答请求默认启用 thinking mode，并将 reasoning effort 设为 high；推理内容不会写入前端或证据源。带旧版工具的多轮请求保持兼容格式，不伪造或丢失 DeepSeek 要求的 reasoning_content。

对于问题本身已经判定为 `unsupported` 或 `unsafe` 的请求，后端直接返回受控回答，`tool_trace`、`sources` 和 `data_versions` 为空，不为了制造 source 调用无关工具。对于属于白名单数据能力范围的 `answerable` 或 `partially_answerable` 问题，如果 Routing 阶段没有返回工具调用，则失败关闭，不由后端猜测工具。超过两个工具、未知工具、非空参数或非法 JSON 仍然失败关闭。

## source 扩展字段

原有字段仍然存在：`tool`、`title`、`metrics`、`data_version`。后端可以附加：

- `description`、`generated_at`、`boundary`、`source_boundaries`
- `sections`、`insights`
- `derived_facts`
- `limitations`、`answerability`

`sections` 只允许快照契约中的 `bar`、`pie`、`table`、`status`、`grouped_bar`、`scatter`、`heatmap` 形状。证据层不会把未知字段、SQL、HTML/JavaScript 或患者级明细传给模型。

derived facts 只做可复核的加减、除法、排名、最大/最小、差距、总量和份额；除数为零时不生成比例。不计算显著性、相关系数、预测概率，也不作因果推断。

## 回答规范

Analysis Prompt 要求回答按以下顺序组织：

1. 直接结论：先回答用户真正的问题。
2. 数据证据：引用当前 source 的指标、分组、版本和可复核计算。
3. 分析发现：指出最大/最小、排名、差距、比例、集中或结构特征。
4. 业务解释：只能使用“数据显示”“值得进一步关注”“可以进一步分析”等谨慎表达。
5. 统计边界：说明这是版本化的住院出院记录群体汇总，不支持个体判断、诊疗建议或因果结论。

最终回答还会经过轻量 grounded validation：拒绝空回答、明显的 SQL/脚本内容；对于拒答类问题要求出现限制表达；对于可回答问题要求出现 source 锚点或证据中的数值。验证不是自然语言事实审计，不能替代证据契约。

## 当前支持与不支持

当前汇总工具可以支持：整体运营概况、医院病例量排名、疾病结构、收费与成本汇总、群体结构、风险结构、支付方式结构和高费用模型评估指标。费用与风险的联合问题通常只能分别描述两侧信号，除非同一 source 提供相同粒度的联合 section。

新版聚合查询还支持已发布年龄组/性别筛选后的疾病病例量排名。这里的病例量是住院出院记录数，不是一般人群患病率、发病率或个体患病风险；`50岁`会映射到数据实际提供的 `50 to 69` 年龄组。

当前数据不能可靠支持：某医院或患者费用高的因果原因、患者诊断或治疗建议、张三等个体的高费用预测、同比/环比趋势、患者级排名、从两个孤立指标断言相关关系，以及没有相应分组明细的“重点疾病”结论。此类问题必须明确说明 unsupported 或 partially_answerable，而不是补造结论。
