# 公共可视化语法与契约

> #105 的设计语义已由 #106 落为正式快照契约。`bar`、`pie`、`table`、`status`、`grouped_bar`、`scatter`、`heatmap` 是唯一允许的 section 类型；关系图只接收本文件规定的白名单字段，不接收任意 ECharts option。

## 1. Common grammar

当前 payload 的稳定外形仍是：

```json
{
  "title": "页面标题",
  "description": "统计边界",
  "options": {},
  "filters": {},
  "metrics": [{"key": "record_count", "label": "住院出院记录", "value": 0, "unit": "条"}],
  "sections": [{"key": "ranking", "title": "排行", "type": "bar", "items": []}],
  "insights": []
}
```

所有类型共用以下规则：

- `title` 说清业务问题和统计对象；不使用“效果”“原因”“预测趋势”等超出聚合事实的词；
- `description` 或 `visual.boundary` 明确范围、筛选、分母、数据版本和 `fixture:` 状态；
- `unit` 必须是稳定中文单位：病例量/记录数用 `条`，住院时长用 `天`，账面收费用 `美元`，成本用 `美元`，比例用 `%`；
- `%` 在数据中继续以 0–1 存储，页面乘 100 展示；金额去千分位后按非负数处理；
- 数值必须是有限数；空结果用空数组和明确 empty state，不用 `0` 冒充暂无数据；
- 数值、标签、分组、版本和筛选都来自服务结果；浏览器不读取原始 CSV、不执行 SQL、不计算正式指标；
- 每张图必须有表格或文字替代；Tooltip 的信息也必须可以通过焦点、摘要或表格获取，不能依赖 hover；
- 颜色只作辅助。图例、直接标签、形状、线型、纹理或文本必须承担同样的区分作用。

## 2. Frozen section metadata

`grouped_bar`、`scatter`、`heatmap` 必须携带以下完整 `visual` 对象；`summary` 和 `insights` 都由服务端生成。版本和时间必须与快照外层的 `data_version`、`generated_at` 完全一致。

```json
{
  "key": "cost_los_relation",
  "title": "收费与住院时长的分组关系",
  "type": "scatter",
  "visual": {
    "question": "在当前筛选群体中，收费与住院时长如何分布？",
    "x_label": "平均住院时长（天）",
    "y_label": "平均收费（美元）",
    "unit": "美元",
    "legend": [{"key": "severity", "label": "严重程度", "style": "shape"}],
    "tooltip_fields": ["name", "x", "y", "size", "group"],
    "summary": {
      "text": "由后端生成的确定性摘要",
      "source_metric_keys": ["avg_los", "avg_charges", "record_count"],
      "source_section": "cost_los_relation",
      "data_version": "<same snapshot version>",
      "generated_at": "<same UTC timestamp>",
      "boundary": "当前筛选下的聚合记录",
      "related_not_causal": true
    },
    "fallback": {"type": "table", "columns": ["name", "x", "y", "size", "group"]},
    "empty": {"title": "当前条件暂无关系数据", "text": "请清空或调整已发布筛选。"}
  },
  "items": [],
  "insights": [{
    "key": "cost_los_relation",
    "title": "收费与住院时长关系摘要",
    "summary": "由后端生成的确定性摘要",
    "level": "info",
    "source_section": "cost_los_relation",
    "source_metric_keys": ["avg_los", "avg_charges", "record_count"],
    "data_version": "<same snapshot version>",
    "generated_at": "<same UTC timestamp>",
    "boundary": "当前筛选下的聚合记录",
    "related_not_causal": true
  }]
}
```

`visual` 只允许上述产品字段和有限枚举，不接受完整 ECharts option、JavaScript、HTML、SQL、颜色字符串、任意 formatter 或表达式。`related_not_causal` 在关系图和热力矩阵中固定为 `true`；前端只展示服务端摘要，不根据点位、颜色或排序推导洞察。

## 3. Type semantics

### 3.1 Existing `bar`

```json
{"key":"hospital_top10","title":"医院病例量 TOP10","type":"bar","items":[{"name":"机构 A","value":123}]}
```

- 用于离散类别比较、排行和分布；默认按数值降序，并列按稳定标签升序；
- ≤15 个类别使用横向 bar；超过 15 个类别转表格或服务端截断并说明；
- 标题、横轴/数值轴和 Tooltip 显示单位；移动端优先横向、减少刻度，不旋转长中文标签；
- 直接显示关键值，图表旁保留可读列表/表格。

### 3.2 Existing `pie`

- 只用于有明确总和的比例结构，最多 5 个类别；每段显示标签或可聚焦 Tooltip；
- 超过 5 个类别（例如支付方式九项）使用 bar/table，不通过压缩字号强行放入饼图；
- 图例靠近图表，图例文本包含类别和比例；颜色、纹理和文字共同表达。

### 3.3 Existing `table`

- 复杂关系图和任何需要精确读数的场景都必须有 table fallback；
- 表头包含字段名和单位，数值列使用 Tabular figures；可排序列用 `aria-sort`，排序规则由服务端或公共契约说明；
- 390px 使用独立横向滚动容器或卡片化行；不允许正文整体横向滚动；
- table 是事实视图，不隐藏在 hover、折叠或仅供开发调试的区域。

### 3.4 Existing `status`

```json
{"key":"storage","title":"存储与服务检查","type":"status","items":[{"name":"MySQL","value":"CHECK_REQUIRED"}]}
```

状态值必须原样显示并配解释：`CHECK_REQUIRED` 表示尚未完成真实检查，`FIXTURE_ONLY` 表示仅有联调工件；页面不能把它们改成绿色 PASS。颜色之外使用状态文本、图标、边框和 `aria-live`。

### 3.5 Frozen `grouped_bar`

**业务语义**：比较 2–3 个同单位系列在有限类别中的大小。医院 A/B 对照、严重程度分组和支付方式收费对照可以使用；不同单位不能塞进同一坐标轴。

```json
{
  "key": "facility_metric_comparison",
  "title": "两家医疗机构的病例量对照",
  "type": "grouped_bar",
  "visual": {
    "question": "两家医疗机构的病例量如何对照？",
    "x_label": "医疗机构",
    "y_label": "病例量（条）",
    "unit": "条",
    "legend": [
      {"key": "facility_a", "label": "医院 A", "style": "solid"},
      {"key": "facility_b", "label": "医院 B", "style": "pattern"}
    ],
    "tooltip_fields": ["category", "series_label", "value", "unit"],
    "summary": {"text": "仅并列展示已发布病例量。", "source_metric_keys": ["case_count"], "source_section": "facility_metric_comparison", "data_version": "<same snapshot version>", "generated_at": "<same UTC timestamp>", "boundary": "已发布机构汇总", "related_not_causal": true},
    "fallback": {"type": "table", "columns": ["category", "series_label", "value", "unit"]},
    "empty": {"title": "暂无机构对照数据", "text": "请调整已发布机构筛选。"}
  },
  "items": [
    {"category": "病例量", "series": [
      {"key": "facility_a", "label": "医院 A", "value": 0},
      {"key": "facility_b", "label": "医院 B", "value": 0}
    ]}
  ]
}
```

系列必须共享单位、颜色族和排序；不能用多 Y 轴掩盖单位差异。移动端默认先显示表格，再显示可横向阅读的两系列 bar。

### 3.6 Frozen `scatter`

**业务语义**：查看两个连续聚合指标的分布关系，不表示因果。点必须是后端按医院、疾病、严重程度或其他已冻结分组聚合的结果，不是单条住院出院记录。

```json
{
  "key": "cost_los_relation",
  "title": "收费与住院时长的分组关系",
  "type": "scatter",
  "visual": {
    "question": "固定住院时长分箱中，收费与成本如何呈现汇总关系？",
    "x_label": "平均住院时长（天）",
    "y_label": "平均收费（美元）",
    "unit": "美元",
    "legend": [{"key": "severity", "label": "严重程度", "style": "shape"}],
    "tooltip_fields": ["name", "x", "y", "cost", "size", "group", "high_cost_rate"],
    "summary": {"text": "由后端生成的确定性摘要。", "source_metric_keys": ["avg_los", "avg_charges", "record_count"], "source_section": "cost_los_relation", "data_version": "<same snapshot version>", "generated_at": "<same UTC timestamp>", "boundary": "当前筛选下的聚合记录", "related_not_causal": true},
    "fallback": {"type": "table", "columns": ["name", "x", "y", "cost", "size", "group", "high_cost_rate"]},
    "empty": {"title": "当前条件暂无关系数据", "text": "请清空或调整已发布筛选。"}
  },
  "items": [
    {"name": "4-6天 · Major", "x": 5.0, "y": 85000, "size": 100, "group": "Major", "cost": 27000, "high_cost_rate": 0.43}
  ]
}
```

约束：服务端先聚合；默认不超过 500 个点，更多点必须分箱/采样并说明；点大小只能表示明确的病例量等第三变量；不画未经服务端返回的拟合线、因果箭头或预测区间。表格至少包含分组、x、y、点大小、单位和记录数/分母。

### 3.7 Frozen `heatmap`

**业务语义**：显示两个有限分类维度交叉后的强度或比例。风险页固定优先使用年龄组 × APR 严重程度，值可为病例量或后端定义的比例。

```json
{
  "key": "age_severity_matrix",
  "title": "年龄组与病情严重程度结构",
  "type": "heatmap",
  "visual": {
    "question": "不同年龄组的病情严重程度结构如何分布？",
    "x_label": "年龄组",
    "y_label": "病情严重程度",
    "unit": "条",
    "legend": [{"key": "record_count", "label": "住院出院记录", "style": "numeric-gradient"}],
    "tooltip_fields": ["x_label", "y_label", "value", "unit", "numerator", "denominator", "high_risk_rate"],
    "summary": {"text": "由后端生成的确定性摘要。", "source_metric_keys": ["record_count", "high_risk_count", "high_risk_rate"], "source_section": "age_severity_matrix", "data_version": "<same snapshot version>", "generated_at": "<same UTC timestamp>", "boundary": "当前筛选群体", "related_not_causal": true},
    "fallback": {"type": "table", "columns": ["x_label", "y_label", "value", "unit", "numerator", "denominator", "high_risk_rate"]},
    "empty": {"title": "当前条件暂无矩阵数据", "text": "请清空或调整已发布筛选。"}
  },
  "items": [
    {"x_label": "50 to 69", "y_label": "Major", "value": 100, "unit": "条", "numerator": 43, "denominator": 100, "high_risk_rate": 0.43}
  ]
}
```

约束：必须有数值图例、格内数值/符号、键盘焦点和完整矩阵表；颜色不单独表达高低；分类维度通常不超过 10×10，过大时由服务端合并/分页。百分比值必须给分子、分母或来源 metric key，前端不自行决定分母。

## 3.8 #106 implementation freeze

- `hospitals/index.facility_relation`：按 `facility_id` 汇总有效 `los`、收费和成本记录；`x=avg_los`、`y=avg_charges`、`size=case_count`、`group=severe_rate`；按病例量降序、机构编号升序取前 50 点。
- `hospitals` 的 `facility_metric_comparison`：默认比较已发布机构枚举前两项；带 `facility_a`、`facility_b`、`metric` 时由 API 仅组合已发布画像，`metric` 仍受既有白名单约束。
- `costs/*` 的 `cost_los_relation`：固定分箱为 `0-1天`、`2-3天`、`4-6天`、`7-13天`、`14-29天`、`30-59天`、`60-119天`、`120天及以上`；每格按 `severity` 分组，空严重程度为 `未分类`；高费用率阈值为当前批次收费 P75。
- `risks/*` 的 `age_severity_matrix`：年龄轴来自已发布年龄枚举，严重程度轴固定为 `Minor`、`Moderate`、`Major`、`Extreme`；缺失组合仍返回 `value=0`、`numerator=0`、`denominator=0`、`high_risk_rate=0`。
- 每个关系 section 可附一个同 key 的 `insights[]` 项；洞察只能使用 `title`、`summary`、`level`、`source_section`、`source_metric_keys`、版本、时间和边界，且 `related_not_causal=true`。服务端生成，前端不得推断。

## 4. Tooltip, summary and empty behavior

| 元素 | 必须包含 | 不允许 |
|---|---|---|
| 标题 | 业务问题、统计对象 | 因果/治疗/趋势暗示 |
| 图例 | 系列标签、区分方式、单位 | 只有色块没有文字 |
| Tooltip | 分类/分组、精确值、单位、必要分子分母 | 仅 hover、无键盘等价路径 |
| 摘要 | 后端文本、来源 key、数据版本、边界 | 前端根据图形猜结论 |
| 空态 | 无数据说明、当前筛选、清空/调整动作 | 空坐标轴、伪造 0 |
| 错误态 | code、trace_id、重试、影响范围 | SQL、堆栈、地址、口令、住院明细 |

## 5. Responsive rendering map

| 类型 | 1440px | 1024/768px | 390px |
|---|---|---|---|
| bar | 横向排行 + 直接值 | 减少刻度，保持标签 | 横向排行或表格优先 |
| pie | ≤5 项，近图例 | 图例换行 | 表格/列表优先，避免小扇区 |
| table | 完整表格 | 独立滚动 | 独立滚动/卡片行 |
| status | 状态网格 | 两列或列表 | 单列状态列表 |
| grouped_bar | 2–3 系列同轴 | 缩短标签/表格并置 | 表格后置，避免精细点击 |
| scatter | 聚合点 + 摘要 + 表格 | 限点/分组切换，禁止精确刷选依赖 | 摘要 + 表格优先，图仅作辅助 |
| heatmap | 数值图例 + 矩阵表 | 格内文字与表格并置 | 可滚动矩阵/逐行卡片 + 摘要 |

## 6. Handoff checklist to #106

- [ ] 冻结三类新 section 的 schema、有限字段和最大数量；
- [ ] 在 `shared/analytics_snapshot_contract.py`、PySpark 发布、Flask API 和 fixture 中使用同一校验；
- [ ] 明确每个点/格的分组字段、分母、缺失处理、排序和空结果；
- [ ] 为正常、合法空、非法字段、未发布、坏快照和数据库失败各保留证据；
- [ ] 由后端生成摘要，返回来源 metric/section key、版本和统计边界；
- [ ] 通过后再让 #107 接入 renderer；在此之前页面只能继续显示现有四种正式类型。
