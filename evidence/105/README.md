# Issue #105 设计系统证据

## 结论范围

本证据包证明 #105 的设计资产、页面覆盖、图表语义、数据/API 交接和 UX 复核清单已经形成。它不证明 #106 的新聚合、#107 的正式大屏实现或 #108 的独立人工验收已经完成；新图表仍标记为 candidate，真实结论必须等待对应 Issue 的数据/API 证据。

工作基线：`origin/main` 的 `c168475`，本次本地分支为 `agent/issue105-design`。本次没有执行 GitHub 认领、评论、提交、推送或关闭操作。

## 交付物索引

| 交付物 | 作用 | 状态 |
|---|---|---|
| `design-system/yishuyunce/MASTER.md` | tokens、密度、壳层、公共组件、四态、无障碍和边界 | 已形成冻结稿 |
| `design-system/yishuyunce/PAGE-COVERAGE.md` | 十路由覆盖、响应式和状态规则 | 已形成 |
| `design-system/yishuyunce/VISUALIZATION-CONTRACT.md` | bar/pie/table/status 兼容语法和三类新图候选扩展 | 已形成；#106 待正式化 |
| `design-system/yishuyunce/DATA-API-HANDOFF.md` | 已确认字段、聚合、分母、API 载体和下游证据 | 已形成；数据/API 复核待 #106 |
| `design-system/yishuyunce/WIREFRAMES.md` | overview、医院关系、费用关系、风险热力线框和演示路径 | 已形成 |
| `design-system/yishuyunce/pages/*.md` | 四个重点页面的局部覆盖规则 | 已形成 |
| `design-system/yishuyunce/prototype/index.html` | 不接真实 API 的静态/fixture 原型 | 已形成 |

## DS-01：Skill 检索

检索工具：`C:\Users\15066\.codex\skills\ui-ux-pro-max\scripts\search.py`。

| 查询 | 结果 | 采用/舍弃 |
|---|---|---|
| `medical operations analytics dashboard professional accessible --design-system`，variance 5、motion 2、density 8 | `Data-Dense Dashboard`、蓝色/琥珀、Fira Code/Fira Sans、低动效无障碍清单 | 采用高密度、低动效、蓝/琥珀候选；舍弃 Enterprise Gateway、Hero、营销 CTA、轮播 |
| `medical operations relationship heatmap scatter categorical dashboard --domain chart` | scatter、heatmap 的条件、聚合阈值、表格替代和非纯颜色要求 | 采用聚合点、矩阵表、数值图例和键盘替代 |
| `categorical comparison grouped bar accessible --domain chart` | 分类比较使用 bar/grouped bar，直接标签和稳定排序 | 采用同单位、2–3 系列、表格 fallback |
| `dashboard keyboard focus responsive reduced motion --domain ux` | reduced-motion、focus、键盘顺序、焦点不遮挡、390/768 等规则 | 写入 Master 和验收矩阵 |
| `vue component responsive --stack vue`（第一次更宽查询无结果） | 7 条 active 结果：SFC、lazy route、PascalCase、组件行为测试等 | 采用当前 Vue SFC/lazy route 基线；无结果的第一次查询不作为依据 |

## DS-02：Tokens 和组件

复核证据：

- 色板、字体、字号、4/8 spacing、圆角、阴影、focus 和 motion 在 `MASTER.md`；
- `#1E3A8A/#FFFFFF = 10.36:1`；`#475569/#F8FAFC = 7.24:1`；白字/`#1E40AF = 8.72:1`；黑字/`#D97706 = 6.59:1`；
- 顶栏、侧栏、KPI、筛选、洞察卡、图表卡、表格、四态、版本/边界提示均有单独行为规则；
- 原型使用 CSS token 和语义文字，不引入 UI 组件库、D3、Three.js、GSAP 或第二套路由框架。

状态：设计稿自检 `READY`；真实页面实现后的字体、图标和状态组合仍需 #108 复测。

## DS-03：图表语法

`VISUALIZATION-CONTRACT.md` 明确了：

- 现有 `bar/pie/table/status` 的兼容条件、单位、排序、空态和可访问替代；
- `grouped_bar`、`scatter`、`heatmap` 的候选字段、title、axis/unit、legend、tooltip、summary、empty 和 fallback；
- 新类型的 metadata 只能使用白名单字段，不能透传 ECharts option、JS、HTML、SQL 或任意表达式；
- `%` 的 0–1 存储规则、费用/成本/住院时长单位和关系图“相关不等于因果”边界；
- 390/768/1024/1440px 的图表降级策略。

状态：设计契约 `READY_FOR_API_REVIEW`；#106 需要把候选字段写进共享校验、快照、fixture、API 和测试后才能标记正式通过。

## DS-04：重点线框和原型

复核对象：`WIREFRAMES.md` 与 `prototype/index.html`。

已覆盖：

1. `/overview` 标准/大屏同源布局，明确不增加模块；
2. `/hospitals` 医院散点关系、双院 grouped bar、比较表；
3. `/costs` 收费 × 住院时长关系、分位数 bar、点位表；
4. `/risks` 年龄 × 严重程度 heatmap、数值图例、矩阵表；
5. 390/768/1024/1440px 的布局、菜单、表格滚动和摘要优先规则；
6. loading/success/empty/error、重试、版本和边界提示的展示路径。

状态：静态原型 `READY_FOR_REVIEW`；它不代替真实 API/页面验收，也没有把示意数字写成项目事实。

## DS-05：数据可行性

字段来源已对照 `data/src/run_full_analytics_pyspark.py`、`docs/01-data-and-feasibility.md` 和 `docs/07-terminal-product-contract.md`：

- 医院关系使用 `facility_id` 聚合、`facility` 展示；
- 费用关系使用清洗后的 `los`、`charges`、`costs`，遵守 `120 +` capped 和 `los>0` 单日金额规则；
- 风险热力使用 `Age Group` × `APR Severity of Illness Description`，默认展示病例量结构；比例必须由后端给出分子/分母；
- 每条有效记录计一次，不按患者去重；版本和生成时间贯穿 snapshot/API/page；
- 原始明细不出浏览器，关系点/热力格均为服务端聚合。

状态：字段追溯 `READY`；独立数据成员对分箱、点数上限、分母、缺失组合和真实结果的确认仍为 `PENDING-HUMAN-REVIEW`，不能在本证据中代签。

## DS-06：业务边界

已对照 `CONTEXT.md` 和公共产品契约：

- 使用“住院出院记录/病例量”，不写“患者数/患病人数”；
- 收费与成本不互称；
- 风险页固定“不构成个人诊断、治疗建议或因果判断”；
- 关系摘要固定“相关不等于因果”，不画无依据趋势、地图或因果箭头；
- fixture/静态原型明确为联调或示意，不当作真实数据验收；
- `CHECK_REQUIRED`、`FIXTURE_ONLY` 原样表达，不伪装成真实 PASS。

状态：范围自检 `READY`；独立 UX 验收和组长最终确认仍需真实 Issue 评论。

## Independent UX acceptance matrix

此表是交给胡钰炜复验的逐项矩阵。`READY-FOR-REVIEW` 表示本地证据已备齐，不表示已经获得该成员的独立 PASS。

| 编号 | 场景/检查项 | 前置条件 | 执行动作 | 预期结果 | 证据 | 验收人 | 状态 |
|---|---|---|---|---|---|---|---|
| UX-01 | tokens/对比度 | Master 与静态原型可读 | 对照语义色、正文、状态、focus | 正文 ≥4.5:1，图形/边界 ≥3:1，状态不靠颜色单独表达 | `MASTER.md` §1、原型 CSS | 胡钰炜 | READY-FOR-REVIEW |
| UX-02 | 十路由任务路径 | 当前 router 的十入口存在 | 按导航顺序 Tab、进入 overview/hospitals/costs/risks、返回 | 顺序稳定、h1 可定位、回退不丢筛选语义 | `PAGE-COVERAGE.md` §2–§4 | 胡钰炜 | READY-FOR-REVIEW |
| UX-03 | 键盘与焦点 | 交互控件使用原生链接/控件 | 不使用鼠标操作筛选、菜单、图例、表格和重试 | 每个动作可到达，焦点可见且不被固定 UI 遮挡 | `MASTER.md` §4、`VISUALIZATION-CONTRACT.md` §4 | 胡钰炜 | READY-FOR-REVIEW |
| UX-04 | 390/768/1024/1440 响应式 | 静态原型和线框可打开 | 分别检查四个视口 | 无页面级横向滚动；图表降级为摘要/表格；标题、单位、版本不丢 | `WIREFRAMES.md` §6、`prototype/styles.css` media queries | 胡钰炜 | READY-FOR-REVIEW |
| UX-05 | loading/success/empty/error | fixture/API 状态定义已读 | 逐态触发或对照 PageState 契约 | 状态互斥，错误有 code/trace/retry，empty 不伪造 0 | `MASTER.md` §3 Four states、`PAGE-COVERAGE.md` §4 | 胡钰炜 | READY-FOR-REVIEW |
| UX-06 | 复杂图替代 | 新图候选 schema 已读 | 检查 scatter/heatmap/grouped_bar 的摘要、Tooltip、表格和图例 | 不依赖 hover/颜色；点/格可读，单位和分母明确 | `VISUALIZATION-CONTRACT.md` §3–§5 | 胡钰炜 | READY-FOR-REVIEW |
| UX-07 | 业务边界文案 | `CONTEXT.md` 与公共契约已读 | 逐页查找患者、诊疗、因果、收费/成本混用 | 使用住院出院记录/病例量；风险页保留非诊断和非因果提示 | `MASTER.md` §0/§3、`DATA-API-HANDOFF.md` §1 | 胡钰炜 | READY-FOR-REVIEW |

## Named responsibility handoff

| 责任人 | 本地交付/待确认范围 | 证据 | 状态 |
|---|---|---|---|
| 李佳明 | 设计系统、四个重点线框、静态原型和页面覆盖 | `MASTER.md`、`WIREFRAMES.md`、`prototype/` | 交付已形成，作者确认待补 |
| 王敬博 | 不新增模块、不改业务口径、与公共契约冲突裁决 | `MASTER.md` §0/§2/§6、`DATA-API-HANDOFF.md` | 本地范围复核已形成 |
| 魏世轩 | 字段、聚合、分母、分箱和真实数据可行性独立复核 | `DATA-API-HANDOFF.md` §1–§2 | 待独立评论 |
| 叶艺鑫 | payload 白名单、错误语义和 fixture/API 交接复核 | `VISUALIZATION-CONTRACT.md` §2/§4、`DATA-API-HANDOFF.md` §3 | 待独立评论 |
| 胡钰炜 | 390/768/1024/1440、键盘、焦点、四态和业务边界验收 | 本矩阵、`WIREFRAMES.md` §6 | 待独立 PASS/FAIL/BLOCKED 评论 |

## Closure gate

本地设计资产已经完成，但按仓库的 Issue 关闭规则，以下外部确认不能由本地文件代替：

- 五人责任范围的真实 Issue 评论；
- #106 对候选 schema、分母、分箱和真实字段的接收；
- #107/#108 对实现输入和 UX 矩阵的引用/复验；
- 李佳明发布 Resolution、王敬博回写 #104 和最终 GitHub 关闭动作。

## Reproduction commands

在仓库根目录执行：

```powershell
git diff --check
rg --files design-system/yishuyunce evidence/105
cd design-system/yishuyunce/prototype
python -m http.server 4175
```

静态原型仅用于视觉检查；正式代码基线仍按仓库 README/`docs/06-test-and-acceptance.md` 执行 `pytest` 与 `frontend\npm run build`。
