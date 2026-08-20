# 医数云策设计系统 Master

> 状态：Issue #105 设计冻结稿（供 #106/#107/#108 实现和复核）。
>
> 本文件冻结视觉、信息架构、组件行为和可视化语法；不改变当前数据契约，不代表新图表已经由数据任务、API 或正式页面实现。

## 0. 产品边界与设计结论

医数云策是面向医院运营管理人员和医疗数据分析人员的住院运营分析系统。页面回答“这批住院出院记录呈现什么运营特征”，不回答个人诊断、治疗或因果问题。所有界面文案使用 `住院出院记录`、`病例量`、`收费`、`成本`、`住院记录群体` 等 `CONTEXT.md` 中的术语。

已冻结的方向是“高密度专业数据看板、均衡现代、低动效”：

- 内容区以浅色表面和清晰边界承载数据，深色侧栏只承担品牌和导航，不用大面积渐变、玻璃拟态或霓虹效果；
- 蓝色表示主数据和导航，琥珀色只表示关注、当前选择或需要用户留意的状态；
- 优先显示数字、单位、统计边界和数据版本；没有真实时间维度时不画趋势线，不用装饰性动画制造“实时感”；
- `/overview` 是唯一的运营驾驶舱和大屏入口。大屏是同一页面的展示密度，不新增业务模块、路由、API 或指标；
- 复杂图表必须同时提供文字摘要和表格/矩阵替代视图，颜色不能成为唯一信息通道。

### 来源与取舍

`ui-ux-pro-max` 的 `medical operations analytics dashboard professional accessible` 设计系统检索命中 `Data-Dense Dashboard`、蓝色/琥珀色板和技术型字体配对；自动命中的 `Enterprise Gateway`、Hero/营销 CTA 和轮播内容与本产品不符，全部舍弃。图表与 UX 检索结果仅作为建议，仓库契约、业务边界和当前 Vue + ECharts 架构优先。

## 1. Product tokens

### 1.1 Color

组件只能引用语义 token，不在页面样式中直接散落 Hex 值。

| Token | 值 | 用途 |
|---|---|---|
| `--color-primary` | `#1E40AF` | 主按钮、链接、焦点环、主导航选中态 |
| `--color-primary-strong` | `#1E3A8A` | 页面标题、重要数据、深色文字 |
| `--color-secondary` | `#3B82F6` | 次级数据系列、辅助操作 |
| `--color-accent` | `#D97706` | 当前选择、提示、需要关注的数值；不得单独表示成功/失败 |
| `--color-on-primary` | `#FFFFFF` | 主色背景上的文字 |
| `--color-on-accent` | `#000000` | 琥珀背景上的文字 |
| `--surface-page` | `#F8FAFC` | 页面底色 |
| `--surface-card` | `#FFFFFF` | 卡片、表格、表单表面 |
| `--surface-subtle` | `#E9EEF6` | 禁用、辅助说明、图表浅底 |
| `--surface-stage` | `#0F2940` | 大屏外框和演示模式背景，不承载正文 |
| `--text-strong` | `#0F172A` | 正文标题、表头、主要数字 |
| `--text-body` | `#1E3A8A` | 正文和卡片标题 |
| `--text-muted` | `#475569` | 辅助说明、单位、元数据 |
| `--border-default` | `#DBEAFE` | 卡片、输入框和图表分隔线 |
| `--border-strong` | `#B9CBEA` | 选中、悬停、焦点邻近边界 |
| `--state-success` | `#15803D` | 文本/图标/边框同时表达的成功状态 |
| `--state-info` | `#0369A1` | 信息状态和可追溯提示 |
| `--state-warning` | `#B45309` | 警告状态，必须同时有文字 |
| `--state-danger` | `#B91C1C` | 错误状态，必须同时有文字和重试动作 |
| `--focus-ring` | `#1E40AF` | `:focus-visible` 的 2px 焦点环 |
| `--nav-surface` | `#0F2940` | 侧栏背景 |
| `--nav-active` | `#1E40AF` | 侧栏当前路由背景 |

已核对的浅色对比度：`#1E3A8A/#FFFFFF = 10.36:1`、`#475569/#F8FAFC = 7.24:1`、白字在 `#1E40AF` 上为 `8.72:1`、黑字在 `#D97706` 上为 `6.59:1`。`#D97706` 不作为白底小号正文色使用。实现 #108 时仍需用实际字体、边框和状态组合复测 4.5:1/3:1 基线。

### 1.2 Typography

中文可读性优先，不强制依赖外部字体网络：

```css
--font-body: "Noto Sans SC", "Fira Sans", system-ui, sans-serif;
--font-number: "Fira Code", "SFMono-Regular", Consolas, monospace;
--font-display: "Noto Sans SC", "Fira Sans", system-ui, sans-serif;
```

`Fira Code` 只用于数字、版本号、追踪编号和代码样式字段；中文标题和正文使用 `Noto Sans SC`，避免把缺少完整 CJK 字形的技术字体当作中文正文。数字使用等宽/Tabular figures，避免筛选或刷新时发生宽度跳动。

| Token | 规格 | 使用 |
|---|---:|---|
| `--text-xs` | 12px / 1.5 | 标签、版本、图例辅助信息；不承载长正文 |
| `--text-sm` | 14px / 1.5 | 表头、筛选标签、辅助说明 |
| `--text-md` | 16px / 1.6 | 正文、按钮、表格单元格 |
| `--text-lg` | 18px / 1.45 | 卡片标题、洞察标题 |
| `--text-xl` | 24px / 1.3 | 页面标题 |
| `--text-2xl` | 32px / 1.2 | 标准模式 KPI 数字 |
| `--text-stage` | 40px / 1.1 | 大屏 KPI 数字；不超过 48px |

正文最小 16px；移动端不通过禁止缩放来“解决”排版。中文长标题自然换行，诊断名称、机构名称和版本号使用 `overflow-wrap: anywhere`，不使用 `break-all` 破坏正常阅读。

### 1.3 Spacing, shape and elevation

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;

--radius-control: 8px;
--radius-card: 12px;
--radius-shell: 16px;
--radius-pill: 999px;
--shadow-card: 0 1px 2px rgba(15, 23, 42, .06);
--shadow-floating: 0 8px 24px rgba(15, 23, 42, .10);
--focus-width: 2px;
--focus-offset: 2px;
```

卡片默认不抬升；悬停只改变边框/阴影，不改变布局尺寸。表面边框优先于阴影传达分组关系。

### 1.4 Layout and density

| 视口 | 模式 | 结构 | 关键尺寸 |
|---:|---|---|---|
| 390px | mobile | 侧栏收为菜单按钮，内容单列，图表后置文字/表格摘要 | 页面内边距 16px；控制项至少 44×44px |
| 768px | tablet | 侧栏可折叠，KPI 两列，图表两列或单列 | 页面内边距 24px；表格允许独立滚动容器 |
| 1024px | compact desktop | 侧栏 224px，内容 8 列网格 | 卡片间距 16px；图表最小高度 280px |
| 1440px | standard / stage | 侧栏 240px，内容 12 列网格 | 标准内边距 32px；大屏内边距 24px、图表高度 320–360px |

标准和大屏共用同一信息架构：

- 标准模式：页面标题/边界 → 筛选 → KPI → 主图表 → 洞察/表格 → 版本和来源；
- 大屏模式：隐藏非必要侧栏细节，扩大 KPI 和图表，但不增加 section、不改变排序、不重算数值；
- 大屏推荐展示 `overview` 的已发布内容，显示 `?display=stage` 仅作为待 #107 落地的 UI 展示状态建议，不是新 API 参数或新业务模块；
- 任何模式下都保留 `loading/success/empty/error` 的可辨识状态和数据边界。

交互目标区域统一为 44×44px，目标之间至少 8px 间距。页面使用一个主滚动区；表格在窄屏可横向滚动，但正文、筛选和卡片不能产生页面级横向滚动。

### 1.5 Motion

```css
--motion-fast: 120ms;
--motion-state: 200ms;
--motion-page: 300ms;
--motion-ease: cubic-bezier(.2, .8, .2, 1);
```

只使用与状态变化相关的 `opacity`/`transform`，每个视图最多 1–2 个关键动效；不引入 GSAP、滚动劫持、自动轮播、3D 或呼吸灯。图表首次显示可以使用 150ms 淡入，正式数值必须在动画之前可读。

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

## 2. Information architecture and shell

保留当前十个固定路由和深链接，不增加第十一个业务模块。导航分成两个有标题的组，但 URL 与顺序保持不变：

1. **分析模块**：`/overview` 运营驾驶舱、`/hospitals` 医院运营分析、`/diseases` 疾病画像分析、`/cohorts` 住院记录群体分析、`/costs` 费用与成本分析、`/risks` 病情严重程度与风险分析、`/payments` 支付方式分析、`/data-quality` 数据质量管理；
2. **辅助能力**：`/model` 高费用记录分类、`/assistant` AI 问答与洞察报告。

公共壳层从上到下固定为：跳过导航链接 → 侧栏/移动菜单 → 页面顶栏 → 页面标题和边界 → 筛选 → 内容。每次路由切换后把焦点移到页面 `h1` 或可聚焦的主内容标题；返回页面应保留已接受的筛选和滚动位置。

不使用 emoji 或单个汉字充当最终图标。实现可复用现有 `frontend/public/icons.svg` 中的 SVG 资源或同一套内联 SVG；装饰图标 `aria-hidden="true"`，图标按钮必须有可见/无障碍名称。

## 3. Shared component rules

### App shell / top bar / sidebar

- 侧栏宽 240px，深色背景只用于导航；每个链接有文本标签、稳定顺序、44px 最小高度和 `aria-current="page"`；
- 顶栏显示当前模块名称、可选筛选摘要、`data_version`、`generated_at` 和 fixture/真实状态；批次标识超长时可以折行或展开，不能只靠省略号隐藏；
- 顶栏的“标准/大屏”是展示密度切换，不是业务筛选；AI 和模型页保留各自必要的操作，不把它们塞进驾驶舱；
- 移动端侧栏改为显式菜单按钮和可关闭菜单，不能依赖 hover；固定元素要预留 `scroll-padding-top`，不遮挡焦点。

### KPI card

卡片只展示 API `metrics[]` 中已有的 `label/value/unit`。数值使用等宽数字，单位始终可见；百分比值遵守统一契约，以 0–1 存储、页面乘 100 显示。没有时间维度时不添加“同比/增长”箭头，不用图标推断趋势。

### Filter bar

筛选控件的选项只能来自 payload `options`，不允许自由 SQL、自由 ECharts option 或前端自造枚举。每个控件有显式 label、键盘顺序和清空动作；互斥字段（如 `diagnosis_code` 与 `facility_id`）在选择前后都有文字提示。已接受筛选应可通过深链接复现，非法参数进入 error state 而不是静默修正。

### Insight card

洞察卡只承载后端返回的确定性摘要、来源 metric/section key、数据版本和统计边界。前端不从点位、颜色或排序自行推断结论；涉及两个变量时固定显示“相关不等于因果”。没有可信摘要时显示“暂无确定性洞察”，不生成营销式文案。

### Chart card

每张图卡固定包含：业务问题标题、统计对象/筛选边界、单位、图例（需要时）、图表、可键盘访问的 Tooltip/数据摘要、文字替代或表格。图卡标题不写“效果”“原因”等无法由聚合结果支持的词。移动端优先保留标题、单位、结论摘要和表格，减少刻度而不是缩小到不可读。

### Table

表格是复杂图的可访问事实视图，不是仅供调试的隐藏 DOM。表头有单位和稳定排序规则；可排序列使用 `aria-sort`。390px 下使用独立 `overflow-x: auto` 容器或卡片化行，不能让页面整体横向溢出。

### Four states

| 状态 | 视觉/语义 | 允许的动作 |
|---|---|---|
| `loading` | 骨架或明确的加载提示，旧图不与新筛选混显 | 等待；不显示伪造的 0 |
| `success` | 指标、图表、边界、版本完整 | 筛选、下钻、回退；操作结果保留在 URL/状态 |
| `empty` | 明确“当前条件暂无数据”，保留有效筛选/版本 | 清空筛选、改变已发布枚举 |
| `error` | 稳定文案、`code`、`trace_id`、影响范围 | `重新加载`；不展示堆栈、SQL、凭证或住院明细 |

状态使用文字、图标、边框和 `aria-live` 共同表达，不能只换颜色。切换到 loading 时清理上一轮图表，避免把旧结果误认为新结果。

### Version and boundary notice

统一使用两类提示：

- **版本提示**：`数据版本：<data_version> · 生成时间：<generated_at>`；`fixture:` 前缀必须明确标记“仅联调，不代表真实数据结论”；
- **边界提示**：分析页至少说明“统计对象为住院出院记录，不按患者去重”；风险页再说明“不构成个人诊断、治疗建议或因果判断”。

## 4. Accessibility baseline

- 正文对比度至少 4.5:1，图形/边界至少 3:1；成功、警告、错误和严重程度必须同时有文字、图标/形状或纹理；
- Tab 顺序与视觉顺序一致；所有按钮、选择框、链接、图例切换和图表点位都有可见焦点；焦点不能被固定侧栏/顶栏遮挡；
- 路由使用一个 `h1`，图卡按 `h2` 层级；图表提供 `aria-label`/摘要和可见表格，不依赖 hover；
- 图表点、分段和图例的操作目标至少 44×44px；不要求精确点击细线或小点；拖拽/刷选若未来出现，必须同时有按钮/键盘替代；
- 390/768/1024/1440px 都要检查；移动端不能禁用缩放；
- `prefers-reduced-motion: reduce` 下不播放进入动画、不滚动劫持、不自动轮播；
- 错误与重试状态可被读屏器感知；live region 只播报必要的完整上下文，不抢焦点。

## 5. Downstream usage

实现新页面前先读本文件，再读 `pages/<page>.md`（若存在）。#106 只将 `VISUALIZATION-CONTRACT.md` 中标为“候选扩展”的字段正式化；#107 使用 `WIREFRAMES.md` 的同一路由/同一 section 顺序实现大屏；#108 按 `evidence/105/README.md` 的矩阵复核视觉、键盘、窄屏和边界文案。

## 6. Explicit non-goals

- 不新增 UI 组件库、D3、Three.js、GSAP、第二套路由框架或第二套状态管理；
- 不新增时间趋势、地图、网络图、3D、患者身份、个人诊疗或因果解释；
- 不把老师样例项目、fixture 数值或设计示意值写成第 2 组已完成的真实结果；
- 不在本 Issue 修改正式 snapshot validator、API 路由、MySQL 表、PySpark 任务或十页面实现代码。
