# #108 十页面视觉、响应式、可访问性与答辩展示验收

## 范围

- 前端验收入口：本分支启动的 Vite 页面，代理到本分支后端的固定联调快照。
- 数据版本：`fixture:sparcs_full_analytics:v1`。
- 模型工件：`fixture:high_cost_logistic_regression:v1`。
- 本证据只记录实际执行结果；固定联调快照不代表真实全量分析结论。

## 自动化结果

- `frontend`: `npm.cmd run build` 通过；623 个模块构建完成。Vite 仅提示既有的 ECharts chunk size warning。
- `backend/tests data/tests`: `213 passed, 2 warnings`。两个 warning 均来自 PySpark 依赖的弃用提示。
- `git diff --check`: 通过。

## 浏览器验收矩阵

| 视口 | 结果 |
| --- | --- |
| 390×844 | 移动头部显示、侧栏默认隐藏、数据渲染后无横向溢出；菜单打开后焦点进入关闭按钮，关闭后焦点回到菜单按钮 |
| 768×1024 | 10 页面成功态可加载，无横向溢出 |
| 1024×768 | 10 页面成功态可加载，无横向溢出 |
| 1440×900 | 10 页面成功态可加载，无横向溢出 |
| 1920×1080 大屏 | `/overview?mode=screen` 隐藏侧栏，四指标栅格、双列内容栅格和退出/浏览器全屏按钮可用，无横向溢出 |

十条路由均进入成功态：`/overview`、`/hospitals`、`/diseases`、`/cohorts`、`/costs`、`/risks`、`/payments`、`/data-quality`、`/model`、`/assistant`。分析路由均显示数据版本与生成时间；医院、费用、风险等关系/对照 section 均显示后端问题摘要和可读数据表替代视图，数据表单位不再以空白短横线代替。

## 状态与键盘路径

- 不支持查询参数：展示 validation 态，点击“清除无效参数”后回到成功态。
- 互斥医院筛选：展示 validation 态，清除后回到成功态。
- 合法但无已发布结果的群体筛选：展示 empty 态，不保留旧指标或旧图表。
- 不支持的筛选值：展示 error 态、错误类型和“重新加载”入口，不保留旧数据。
- 路由切换后页面标题自动聚焦；全局 skip link 指向 `#main-content`；导航使用原生 link/button/select；图表画布隐藏于辅助技术树，问题摘要和数据表承担可读替代。
- CSS 已覆盖 `prefers-reduced-motion: reduce` 和 print/PDF；图表动画也根据媒体查询关闭。

## 模型与 AI

- 模型指标与固定工件预测均成功；本次浏览器预测返回“高费用记录”、概率、阈值、模型版本、数据版本和统计边界。
- 本机当前未配置 DeepSeek 密钥，因此 AI 页面实际验证的是空问题校验（错误提示可聚焦）和服务配置错误态（错误码、追踪编号、重新提问），没有伪造正向 AI 回答。真实 DeepSeek 白名单与问答正向验证沿用 [evidence/79](../79/execution-record.md) 的已存证据。

## 截图

- `overview-1440.png`：桌面分析页。
- `overview-390.png`：移动分析页。
- `overview-stage-1920.png`：1920×1080 答辩大屏。
