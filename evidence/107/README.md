# Issue #107 前端验收证据

本证据包对应 `model/high-cost-classifier` 分支上的运营大屏、复杂图表、表格替代、筛选深链接和确定性洞察实现。截图使用仓库固定快照 `fixture:sparcs_full_analytics:v1`，不把 fixture 当成真实全量结论。

## 可复查命令

```powershell
cd frontend
npm.cmd install --no-audit --no-fund
npm.cmd run build
git diff --check
```

结果：Vite `623 modules transformed`、构建成功；`git diff --check` 无空白错误。

页面检查使用 Vite dev server、固定快照 API 适配器和 Chrome headless，覆盖：

- `/overview?mode=screen`：1440×900、390×844；
- `/costs`：散点关系、后端摘要和明细表；
- `/risks`：热力图、分子/分母/比例和明细矩阵表；
- 页面 HTML 中确认了 `data_version=fixture:sparcs_full_analytics:v1`、筛选值恢复、下钻 URL 和无应用级 JavaScript 错误。

截图：

- `107-overview-stage-1440.png`
- `107-overview-stage-390.png`
- `107-costs-scatter-1440.png`
- `107-risks-heatmap-1440.png`

## 验收矩阵

| 编号 | 结果 | 证据 |
|---|---|---|
| UI-X-01 旧图兼容 | PASS | build；标准 bar/table/status 仍由 `AnalyticsChart` 白名单渲染 |
| UI-X-02 复杂 renderer | PASS（fixture） | grouped bar/scatter/heatmap DOM、ECharts canvas 和可读表格 |
| UI-X-03 大屏布局 | PASS（fixture） | 1440 与 390 截图；`mode=screen` 同一 `/overview` 路由，可进入/退出浏览器全屏 |
| UI-X-04 深链接与筛选恢复 | PASS（静态/fixture） | 筛选只写入白名单 query；页面 DOM 展示 `/hospitals`、`/diseases`、`/cohorts`、`/risks`、`/costs` 下钻链接；直接打开 query 可恢复筛选 |
| UI-X-05 键盘替代 | PASS（静态/fixture） | 图表有焦点入口，复杂图和普通图均有可读 HTML table，表格不依赖 hover |
| UI-X-06 真实一致 | FIXTURE PASS；真实 API 待环境复验 | #106 的真实批次证据为 `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`；本次浏览器证据使用 fixture |
| UI-X-07 四态与 retry | CODE PASS；运行时错误注入待环境复验 | 复用现有 `PageState`/`ApiError`/retry 链路，未改变正式错误码 |
| UI-X-08 性能与动效 | BUILD PASS | ECharts 使用 core + 白名单图表/组件；无自动轮播；构建有 chunk size warning，需真实演示环境继续记录性能 |
| UI-X-09 业务叙事 | PASS（fixture） | `InsightPanel` 只展示 API 返回摘要、来源指标、版本、边界和“相关不等于因果” |

当前工作区没有可执行 Python，因此未重复运行后端 pytest；后端/真实 MySQL 证据沿用 `evidence/106`，不能替代真实浏览器联调。
