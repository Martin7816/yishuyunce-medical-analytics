# 医数云策前端

前端为住院运营分析提供八个页面入口。`/overview` 固定进入深色运营全景大屏，页面顶部提供医院、疾病、群体、费用、严重程度和支付方式专题入口；工作台页面暂不在前端展示。六个专题页继续复用 `AnalysisPage`、`MetricCard`、`AnalyticsChart` 和 `PageState`，AI 问答保留独立的表单和结果区。

前端只请求 Flask API，不连接数据库，不在浏览器中聚合、排序或截断正式结果，也不执行接口返回的 HTML、JavaScript 或任意图表配置。图表由 D3 根据受控数据契约生成响应式 SVG。

前端不选择数据源；请先按仓库根目录 `README.md` 将后端配置为 `mysql` 真实模式。后端返回的 `data_version` 以 `fixture:` 开头时，页面会明确标记为演示数据。

## 页面

| 路由 | 页面 |
|---|---|
| `/overview` | 深色笔记本自适应运营全景展示（执行摘要、结构扫描与专题入口） |
| `/hospitals` | 医院运营分析 |
| `/diseases` | 疾病画像分析 |
| `/cohorts` | 住院记录群体分析 |
| `/costs` | 费用与成本分析 |
| `/risks` | 病情严重程度与风险分析 |
| `/payments` | 支付方式分析 |
| `/assistant` | AI 问答与洞察报告 |

## 启动流程

### 1. 启动 Flask

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
.\.venv\Scripts\python.exe backend\run.py
```

根目录 README 的默认流程使用 MySQL 真实分析快照。Flask 监听 `http://127.0.0.1:5000`；只有为联调显式设置 `TOP10_DATA_SOURCE=fixture` 和 `ANALYTICS_DATA_SOURCE=fixture` 时，才会读取仓库内置快照。

### 2. 启动 Vite

另开 PowerShell：

```powershell
cd frontend
# 首次安装或更新依赖时执行；如果 Vite 已在运行，先在其终端按 Ctrl+C
npm ci --cache D:\HuaDi\.npm-cache-medical-analytics
npm run dev
```

如果本机没有 `D:\HuaDi` 工作区，请将 `--cache` 后的路径换成一个当前用户可写的目录；不要继续使用报 `EPERM` 的 npm 缓存目录。
不要在 `npm run dev` 正在运行时再次执行 `npm ci`，否则 Windows 可能无法删除正在使用的 Rollup 原生模块。

访问 `http://localhost:5173/overview`。Vite 将 `/api` 转发到 `http://127.0.0.1:5000`。跨主机或同源部署时，在未提交的 `frontend/.env` 中设置：

```dotenv
VITE_API_BASE_URL=<Flask 对外地址>
```

## 页面状态

公共分析页使用五个可验证行为：

- `loading`：请求进行中，旧指标与旧图表被清除；
- `success`：展示接口返回的标题、说明、指标、分区、单位和版本；
- `empty`：合法筛选没有记录，保留筛选与版本信息；
- `error`：显示稳定错误提示、错误类型、追踪编号和重试按钮；
- `retry`：依赖恢复后重新请求。

`fixture:` 数据只用于开发联调和页面状态验证，页面会显示固定提示。真实展示需要 MySQL 分析快照、真实数据版本和对应验收证据。

## 渲染约束

- 图表只接受公共快照契约允许的 `bar`、`pie`、`grouped_bar`、`scatter`、`heatmap`、`correlation`、`table` 和 `status`；
- `%` 指标把接口的 0—1 比例乘 100 显示；
- 金额与记录数使用接口提供的单位；
- 筛选枚举来自 API `options`；
- 快速切换筛选时，较早请求的响应不能覆盖最后一次选择；
- 页面正文在桌面和移动端不产生横向溢出，顶部导航可在自身区域横向滚动。
- 运营大屏采用普通网页流式布局，不锁定 1920×1080；笔记本窗口按宽度自适应，内容不足以一屏容纳时自然纵向滚动。总览顶部专题入口使用键盘可访问的页面链接，其他专题分析页保持原有布局。
- 运营总览中的 D3 SVG 图表提供工具提示、直接数值和键盘专题跳转；专题分析页以筛选条件为统一入口，图表同时提供直接数值和可展开的数据表替代视图。

## 构建

```powershell
npm ci --cache D:\HuaDi\.npm-cache-medical-analytics
npm test
npm run build
```

构建产物位于 `frontend/dist`。该目录由构建生成，不作为项目事实来源。
