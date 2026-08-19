# Issue #41 页面基础验收证据

> 责任范围：李佳明负责的 Vue 多页面壳、公共分析页 renderer、图表白名单、四态、响应式和页面联调交接。
>
> 本证据使用 `fixture:sparcs_full_analytics:v1`，只能证明页面公共实现和联调状态可复现，不代表真实 CSV、MySQL、模型效果或最终全链路已经验收通过。

## 执行环境

- 仓库分支：`integration/final-product`
- 前端：Node.js `v22.13.1`、npm `10.9.2`、Vite `8.2.1`
- 后端：Flask fixture 模式，监听 `127.0.0.1:5000`
- 启动：`$env:ANALYTICS_DATA_SOURCE='fixture'; python backend/run.py`；`cd frontend; .\node_modules\.bin\vite.cmd --host 0.0.0.0`

## 自动化结果

| 检查项 | 命令/动作 | 实际结果 |
|---|---|---|
| 前端生产构建 | `cd frontend; npm run build` | `PASS`，621 modules transformed |
| 后端和数据回归 | `.codex_tmp/issue10-venv/Scripts/python.exe -m pytest backend/tests data/tests -q` | `36 passed in 0.73s` |
| 差异格式检查 | `git diff --check` | `PASS` |
| 公共 API fixture | 访问 9 个分析/模型 GET 路径 | 全部 HTTP 200、`code=OK`；合法空筛选也返回 200 |

## 浏览器结果

使用本地 Vite 页面和浏览器 DOM 读取复验，页面控制台 error/warning 为空。

### 十路由

| 路由 | 页面标题 | 图表/专页结果 | 横向溢出 |
|---|---|---:|---|
| `/overview` | 医疗运营驾驶舱 | 5 个图表 | 无 |
| `/hospitals` | 医院运营分析 | 1 个图表 | 无 |
| `/diseases` | 疾病画像分析 | 1 个图表 | 无 |
| `/cohorts` | 住院记录群体分析 | 2 个图表 | 无 |
| `/costs` | 医疗费用与成本分析 | 2 个图表 | 无 |
| `/risks` | 病情严重程度与风险分析 | 3 个图表 | 无 |
| `/payments` | 支付方式分析 | 2 个图表 | 无 |
| `/data-quality` | 数据质量与任务管理 | 1 个图表 | 无 |
| `/model` | 高费用病例分类模型 | 专用模型页可达 | 无 |
| `/assistant` | AI 大模型问答与洞察报告 | 专用 AI 页可达 | 无 |

八个分析页均显示 `fixture:` 黄色提示和统一版本信息；导航链接数量为 10。

### 四态

| 状态 | 触发方式 | 页面证据 |
|---|---|---|
| loading | 临时 Vite 实例设置 `VITE_API_BASE_URL=http://10.255.255.1:59999`，在请求尚未结束时读取 `/overview` | `.state-panel.loading`，文案“正在加载分析快照”，无旧指标和图表 |
| success | fixture 后端访问 `/overview` | 8 张指标卡、5 个图表、版本 `fixture:sparcs_full_analytics:v1` |
| empty | `/cohorts` 选择合法筛选 `age_group=50 to 69` | `.state-panel.empty`，文案“当前条件暂无数据”，仍保留 fixture 警告和版本胶囊 |
| error | 以 `ANALYTICS_DATA_SOURCE=invalid` 启动 Flask 后访问 `/overview` | `.state-panel.error`，显示稳定“服务配置不完整”文案、`SERVER_MISCONFIGURED`、`追踪编号`和“重新加载”按钮，不显示旧指标；停止 Flask 时也能落入安全的 `HTTP_ERROR` 错误态 |
| retry | 恢复 fixture Flask 后点击“重新加载” | 恢复 success，标题“医疗运营驾驶舱”、8 张指标卡和 fixture 提示重新出现 |

### 390px 响应式

浏览器 viewport 设置为 `390×844` 后访问 `/overview`：`scrollWidth=375`、`clientWidth=375`，无横向溢出；`.app-shell` 为单列、顶部导航为横向、指标网格为两列、图表网格为一列，5 个图表均存在。复验结束已恢复默认 viewport。

## 交接与边界

- 下游页面可以直接复用 `frontend/src/router.js` 的路由配置、`frontend/src/api/client.js` 的统一请求信封、`AnalysisPage.vue`、`MetricCard.vue`、`AnalyticsChart.vue` 和 `PageState.vue`。
- `section.type` 只按 `bar`、`pie`、`table`、`status` 渲染；其他类型不会执行配置，而显示安全的“不支持”状态。
- `%` 指标按契约把 0—1 比例乘 100 展示；金额、天数、记录数保留服务返回单位；页面不重新聚合、排序、截断或连接数据库。
- 当前证据没有声称真实全量 CSV、真实 `analysis_snapshot_result` MySQL 批次、组长电脑或 AI Key 已通过；这些仍由 #39、#40、各模块父 Issue 和 #83 按终局契约复验。
