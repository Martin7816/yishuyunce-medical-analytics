# Issue #81 页面验收证据：AI 大模型问答与洞察报告

## 交付范围

- `frontend/src/views/AssistantPage.vue`：完成 `/assistant` 页面交互、响应信封校验、白名单图表输入、错误恢复和可打印报告。
- `frontend/src/style.css`：补充问答卡、报告卡、来源指标、工具轨迹、响应式和打印样式。

页面只把经过前端白名单校验的 `chart.type`、`chart.title` 和 `chart.items` 交给公共 `AnalyticsChart`，回答正文和来源字段均使用 Vue 文本插值，不执行模型返回的 HTML、JavaScript 或 ECharts 配置。

## 自动化检查

| 检查项 | 命令 | 结果 |
|---|---|---|
| 前端生产构建 | `npm run build`（`frontend/`） | PASS；Vite 构建成功 |
| 现有后端接口回归 | `python -m pytest -q backend/tests/test_analytics_api.py` | PASS；24 passed |
| 空白来源静态安全检查 | `rg -n "v-html|innerHTML|eval\\(|new Function" frontend/src/views/AssistantPage.vue frontend/src/components/AnalyticsChart.vue` | PASS；无匹配 |
| 差异格式检查 | `git diff --check -- frontend/src/views/AssistantPage.vue frontend/src/style.css` | PASS |

## 浏览器联调

通过本地 fixture API 和临时 FakeAIClient 完成以下检查；没有调用真实 DeepSeek，也没有使用或记录 API Key。

| 场景 | 检查结果 |
|---|---|
| 首屏与键盘表单 | 4 个预设问题、带标签 textarea、字符计数、Ctrl/⌘+Enter、提交按钮均可用 |
| loading | `aria-busy=true`、旧报告清除、按钮 disabled，并显示“正在调用白名单分析工具” |
| 成功态 | 双工具轨迹、两个来源指标卡、预定义 bar 图表、数据版本和统计边界均展示；回答按纯文本渲染 |
| 无 Key | 显示安全文案、`SERVER_MISCONFIGURED`、`trace_id` 和“重新提问”按钮 |
| 空来源 | 不展示无依据回答，显示 `SERVICE_RESULT_INVALID` 和“缺少可核验来源” |
| 空白问题 | 保留输入，显示行内错误，并设置 `aria-invalid=true` |
| 390px | 来源卡片变为单列，页面 `scrollWidth` 未超过视口，长版本字段使用 `overflow-wrap:anywhere` |
| 控制台 | 浏览器控制台无 error/warning |

## 已知边界

真实 DeepSeek Key、超时、断网和上游模型失败属于 #79/#80 的后端与真实链路验收；本页面通过同一 `/api/v1/ai/chat` 契约展示这些错误码，并不在前端提交或保存密钥。
