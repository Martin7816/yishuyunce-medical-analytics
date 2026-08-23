# AI 分析质量契约

本文件描述 AI 问答在后端的分析质量边界。它不改变 `/api/v1/ai/chat` 的外层字段，也不改变现有八个白名单工具。

## 处理链路

一次问答分为两个模型阶段：

1. Routing Prompt 接收用户原问题，只选择一个最直接相关的白名单工具；只有明确包含两个不同主题时才选择两个工具。工具参数固定为空对象 `{}`。
2. 后端执行工具并通过 `ai_evidence.py` 建立安全证据。证据只保留快照标题、指标、允许的 sections/insights、数据版本、统计边界和确定性 derived facts。
3. 后端计算 `answerability`：`answerable`、`partially_answerable`、`unsupported` 或 `unsafe`。
4. Analysis Prompt 接收原问题、工具结果、安全证据、derived facts、answerability 和限制，回答原问题，而不是复述整个快照。

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

当前数据不能可靠支持：某医院或患者费用高的因果原因、患者诊断或治疗建议、张三等个体的高费用预测、同比/环比趋势、患者级排名、从两个孤立指标断言相关关系，以及没有相应分组明细的“重点疾病”结论。此类问题必须明确说明 unsupported 或 partially_answerable，而不是补造结论。
