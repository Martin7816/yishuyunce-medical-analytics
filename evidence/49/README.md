# Issue #49 医院运营分析前端验收证据

## 交付范围

- `/hospitals` 继续复用公共 `AnalysisPage`、`MetricCard`、`AnalyticsChart` 和 `PageState`。
- 未选择医院时展示医院病例量排行；选择一家或两家时只展示接口返回的完整医院画像、KPI、主要疾病 TOP5 和内外科结构。
- 双院比较按 `metric` 高亮对应 KPI；医院编码始终作为字符串传递，页面不重算、排序、截断或换算正式结果。
- 图表尺寸更新改为下一帧合并执行，长 `data_version` 在手机页脚中可断行，避免响应式检查时出现横向溢出或 ResizeObserver 循环告警。

## 验收矩阵

| 编号 | 检查项 | 实际结果 | 证据 |
|---|---|---|---|
| U-01 | 布局层级 | PASS：标题、筛选、画像 KPI、图表和页脚顺序清楚；未筛选页显示排行 | [`browser-summary.json`](l4-page/browser-summary.json)、[`hospitals-comparison-desktop.png`](l4-page/hospitals-comparison-desktop.png) |
| U-02 | 正常数据 | PASS：真实版本下单院 1 张画像卡/2 张图，双院 2 张画像卡/4 张图，版本和接口值贯穿页面 | [`browser-summary.json`](l4-page/browser-summary.json)；上游真实 API 记录见 [`evidence/39`](../39/README.md) |
| U-03 | 四态与 retry | PASS：fixture success、合法 empty、error/retry 均复现；错误页无旧图表，empty 保留筛选并提供清空按钮 | [`browser-summary.json`](l4-page/browser-summary.json) |
| U-04 | 筛选行为 | PASS：fixture 请求使用 `facility_a=1&facility_b=2&metric=avg_charges`；真实请求使用字符串 ID；A/B 相同就地提示且不展示旧结果 | [`browser-summary.json`](l4-page/browser-summary.json) |
| U-05 | 响应式 | PASS：桌面 `scrollWidth=clientWidth=1265`；手机 `scrollWidth=clientWidth=375`，顶部导航仅自身横向滚动 | [`browser-summary.json`](l4-page/browser-summary.json)、[`hospitals-comparison-mobile.png`](l4-page/hospitals-comparison-mobile.png) |
| U-06 | 安全边界 | PASS：只渲染 `bar`/`pie`/`table`/`status` 白名单；页面没有数据库、聚合、排序或任意 ECharts 配置执行 | `frontend/src/views/AnalysisPage.vue`、`frontend/src/components/AnalyticsChart.vue` |
| U-07 | 控制台与图表稳定性 | PASS：真实、fixture、error 页面浏览器 error/warning 读取均为 0；图表尺寸更新复验未再出现 ResizeObserver 循环告警 | [`browser-summary.json`](l4-page/browser-summary.json) |

## 自动化验证

```text
cd frontend; npm run build
PASS — Vite 8.2.1，621 modules transformed

.venv\Scripts\python.exe -m pytest backend/tests data/tests -q
38 passed in 41.49s

git diff --check
PASS
```

## 真实数据边界

浏览器曾在本地 MySQL API 成功实例上观察到 `data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`、205 家机构及单院/双院画像；真实数据聚合与发布证据仍以 [Issue #47 证据包](../47/README.md) 和 [Issue #39 API 记录](../39/l3-api/real-mysql-summary.txt) 为准。后续本机 MySQL 服务短暂返回 503 时没有修改数据库或把失败状态伪装成成功。

fixture 截图仅证明页面布局和交互可复现，不代表真实全量结论。
