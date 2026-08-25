# `enryteam/bigscreen` 仓库分析与医数云策借鉴建议

分析日期：2026-08-23
上游基线：`master`，提交 `432c9df`（2024-03-12）

## 结论先行

这个仓库有参考价值，但不适合作为我们项目的代码底座。它的本质是“大屏设计资源汇总”，不是围绕真实数据、接口契约、测试和部署组织的完整应用。仓库 README 明确把设计手册、效果图、HTML 模板、行业案例和外部项目链接放在一起；当前 master 约 8,668 个文件，主要是图片、第三方 JavaScript、CSS、HTML 和 JSON 资源。

对“医数云策”最有用的是三类内容：

1. 用“业务问题—指标—维度—图表—布局—测试”的顺序做大屏设计复核；
2. 借鉴医疗样例中的 KPI 组织、横向排行条、卡片标题和专题下钻的视觉表达；
3. 把 1920×1080 的真实演示窗口作为视觉验收基线。

不建议复制它的页面、依赖或数据逻辑。医疗样例的数据多数直接写在 HTML/JS 中，页面引入 jQuery、ECharts、百度地图和日期插件；这与我们已经建立的 PySpark → 分析快照 → MySQL → Flask → Vue/D3 链路不一致。上游样例还包含百度地图 AK、患者搜索/列表、趋势和地图等内容，不能直接当作第2组项目功能。

## 1. 上游仓库是什么

| 观察 | 证据 | 对我们的含义 |
|---|---|---|
| 仓库定位是资源集合 | [README](https://github.com/enryteam/bigscreen/blob/master/README.md) 将内容概括为设计手册、效果图、原型、行业大屏和开源项目索引 | 适合“找灵感和查样式”，不适合整体引入 |
| 内容规模大且重复 | 根目录包含多个行业目录、模板目录和大量图片/依赖；`智慧医疗/大数据医疗` 与 `智慧医疗/医院大数据大屏` 绝大多数同名文件内容相同 | 按需看单个文件，避免把仓库当依赖复制进项目 |
| 技术基线偏旧 | 医疗样例使用静态 HTML、jQuery、ECharts、BMap 和 Laydate；仓库 master 基线提交于 2024-03-12 | 只能借鉴交互和视觉，不应切换现有前端架构 |
| 授权边界不能一概而论 | 根目录有 [MIT LICENSE](https://github.com/enryteam/bigscreen/blob/master/LICENSE)，但 README 同时汇总了大量外部项目、图片和第三方模板 | 外部图片、字体、代码逐项确认来源和授权，不直接打包 |

## 2. 对我们最有用的内容

### 2.1 大屏设计手册：可吸收为评审流程

仓库中的[大屏数据可视化设计指南](https://github.com/enryteam/bigscreen/blob/master/1.%20%E5%A4%A7%E5%B1%8F%E8%AE%BE%E8%AE%A1%E5%8F%82%E8%80%83%E6%89%8B%E5%86%8C/%E5%A4%A7%E5%B1%8F%E6%95%B0%E6%8D%AE%E5%8F%AF%E8%A7%86%E5%8C%96%E8%AE%BE%E8%AE%A1%E6%8C%87%E5%8D%97%20.md)强调先明确业务目标和关键指标，再确定分析维度、图表类型、物理屏幕、页面布局和测试；其中“设计服务需求、先总览后细节”与我们目前的运营驾驶舱方向一致。

它可以转化为当前项目的一个轻量评审顺序：

```text
业务问题 → 已发布指标/分母 → 图表类型 → 1440/1920 布局 → 文字与表格替代 → 真实数据验收
```

这不是新增流程，而是对现有 [公共可视化契约](./07-terminal-product-contract.md)、[可视化语法](../design-system/yishuyunce/VISUALIZATION-CONTRACT.md) 和 [测试与验收](./06-test-and-acceptance.md) 的设计侧补充。

### 2.2 医疗样例：可借鉴信息组织，不复制代码

`智慧医疗/大数据医疗` 样例的首页包含顶部导航、多个 KPI、左右图表区和中间主视觉区；[首页 HTML](https://github.com/enryteam/bigscreen/blob/master/%E6%99%BA%E6%85%A7%E5%8C%BB%E7%96%97/%E5%A4%A7%E6%95%B0%E6%8D%AE%E5%8C%BB%E7%96%97/views/index.html) 还展示了点击机构后打开详情弹层的组织方式。这个“总览—重点比较—专题详情”的层级，对我们的 `/overview` → `/hospitals`、`/diseases`、`/risks` 下钻关系有启发。

样例 [quota.js](https://github.com/enryteam/bigscreen/blob/master/%E6%99%BA%E6%85%A7%E5%8C%BB%E7%96%97/%E5%A4%A7%E6%95%B0%E6%8D%AE%E5%8C%BB%E7%96%97/scripts/quota.js) 中的横向排行条还提供了一个可复用的视觉语法：排名序号、类别名称、横向条、直接数值和统一背景轨道。若现有 D3 renderer 尚未在所有排行图中保持这一层次，可以只补这几个视觉细节，并继续保留我们的单位、数据版本、边界说明和表格替代视图。

样例的深色背景、蓝青色主色、卡片标题装饰和较大的 KPI 数字，也可作为 `/overview?mode=screen` 的灵感来源。不过我们已经在 [MASTER.md](../design-system/yishuyunce/MASTER.md) 和 [dashboard.css](../frontend/src/styles/dashboard.css) 中形成了自己的 token，应该用 CSS token 重现语义，不直接拷贝图片标题、字体文件或整套样式。

### 2.3 视觉验收：借鉴“物理屏幕”意识

设计指南强调设计稿和实际投屏效果需要经过整体细节调优与测试；当前项目已经有 1920×1080、1440 和移动端证据。可以把上游经验落实为展示前的最小检查：

- 1920×1080 下 KPI、图表标题、图例和底部边界说明不被裁切；
- 1440/1024 下保持两列或可滚动布局，不让长中文标签重叠；
- 390 下优先保留摘要、单位和表格，不依赖悬停才能读数；
- 真实模式与 `fixture:` 模式的颜色和文案都能区分，不能把静态样例数字当真实结论。

这些要求与现有页面的 loading/success/empty/error 状态和 table fallback 相容，不需要引入新的大屏框架。

## 3. 不建议引入的内容

| 内容 | 上游证据 | 不引入的原因 |
|---|---|---|
| 百度地图/BMap 地图 | [首页 HTML](https://github.com/enryteam/bigscreen/blob/master/%E6%99%BA%E6%85%A7%E5%8C%BB%E7%96%97/%E5%A4%A7%E6%95%B0%E6%8D%AE%E5%8C%BB%E7%96%97/views/index.html) 引入 BMap 和外部地图脚本；[index.js](https://github.com/enryteam/bigscreen/blob/master/%E6%99%BA%E6%85%A7%E5%8C%BB%E7%96%97/%E5%A4%A7%E6%95%B0%E6%8D%AE%E5%8C%BB%E7%96%97/scripts/index.js) 使用固定经纬度 | 当前项目核心问题是住院运营统计，不需要新增地理模块；还会增加密钥、外网、地图性能和隐私边界 |
| 趋势线、实时钟表、跑马灯 | [trend.html](https://github.com/enryteam/bigscreen/blob/master/%E6%99%BA%E6%85%A7%E5%8C%BB%E7%96%97/%E5%A4%A7%E6%95%B0%E6%8D%AE%E5%8C%BB%E7%96%97/views/trend.html) 和通用模板包含趋势、时间和滚动列表 | 没有经过项目契约确认的时间维度时，趋势会制造错误的实时感；现有设计规范也明确不增加装饰性趋势和自动轮播 |
| 患者姓名/身份证搜索和慢病列表 | [chronic.html](https://github.com/enryteam/bigscreen/blob/master/%E6%99%BA%E6%85%A7%E5%8C%BB%E7%96%97/%E5%A4%A7%E6%95%B0%E6%8D%AE%E5%8C%BB%E7%96%97/views/chronic.html) | 我们的数据一行是住院出院记录，没有患者唯一 ID；该功能越过项目的数据和医疗边界 |
| 3D、地图飞线、炫光动画 | 仓库的 [ECharts 示例](https://github.com/enryteam/bigscreen/tree/master/Echarts%E7%A4%BA%E4%BE%8B) 和多个行业目录包含大量 3D/GIS 素材 | 增加渲染与展示风险，不能改善当前核心验收；可视化规范优先保证可读、可核对和可访问 |
| 直接复制 ECharts/jQuery 模板 | 医疗样例直接加载 `echarts.min.js`、jQuery、BMap 和 Laydate，指标和图表数据写在 HTML/JS 中 | 会与现有 Vue + D3、统一快照、Flask API 和测试体系形成第二套实现，且难以接入数据版本、错误态和白名单契约 |
| 整仓复制或批量下载图片 | README 把大量外部项目和图片汇总到同一仓库 | 体积、重复、授权和维护成本都不符合当前项目的最小化原则 |

另外，医疗样例源码中出现了硬编码的地图访问参数；本报告不重复展示具体值。即使参数属于前端公开配置，也不应把这种写法带入我们的仓库。

## 4. 对当前项目的最终取舍

### 可以直接采用的“思想”

- 大屏先回答核心运营问题，再安排次级图表；
- 排行图使用稳定排序、排名、直接值和单位；
- 视觉稿必须在真实目标分辨率下检查；
- 复杂图表旁边保留文字摘要或表格事实视图。

### 只做小范围借鉴的“表现”

- `/overview?mode=screen` 的标题装饰、卡片边界、KPI 数字层级；
- 医院/疾病 TOP10 的横向排行条；
- 从总览卡片到专题页的显式下钻按钮。

实施时只改现有 Vue/D3 renderer 和 token；不新增路由、API、数据表、ECharts、BMap 或第三方组件库。

### 明确不采用的“工程方案”

- 静态 HTML + jQuery + 写死数据；
- BMap、3D/GIS、自动滚动和实时装饰；
- 患者级搜索、身份字段和个人病程；
- 一次性引入整套模板或重新搭建可视化引擎。

## 5. 建议的下一步

1. 先用本报告的四项检查复核现有 `/overview?mode=screen`，确认已有能力是否已经覆盖，不为“看起来更酷”新增功能。
2. 如果排行条在医院、疾病和支付等页面的表达不一致，只在现有 renderer 中统一排名、单位、直接值和 table fallback。
3. 将 1920×1080 的大屏截图与真实数据版本、运行命令和验收结论放在同一份 evidence 中；不保存上游模板截图作为项目实现证据。
4. 若以后确实需要地图或实时运营场景，先单独确认数据字段、接口来源、密钥管理、性能和验收范围，再立项，不从本仓库直接复制。

## 依据

- 上游仓库：[enryteam/bigscreen](https://github.com/enryteam/bigscreen)
- 上游资源索引：[大屏可视化开源项目.md](https://github.com/enryteam/bigscreen/blob/master/%E5%A4%A7%E5%B1%8F%E5%8F%AF%E8%A7%86%E5%8C%96%E5%BC%80%E6%BA%90%E9%A1%B9%E7%9B%AE.md)
- 本项目：[README.md](../README.md)、[CONTEXT.md](../CONTEXT.md)、[系统架构与环境](03-architecture-and-env.md)、[MASTER.md](../design-system/yishuyunce/MASTER.md)、[VISUALIZATION-CONTRACT.md](../design-system/yishuyunce/VISUALIZATION-CONTRACT.md)
- 上游基线提交：[432c9df](https://github.com/enryteam/bigscreen/commit/432c9dfe674ea860a15b9a358f533f2f56e5e4b8)
