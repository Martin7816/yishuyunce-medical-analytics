# 医数云策前端

前端是终局产品的十路由壳：八个分析页共用 `AnalysisPage`，模型和 AI 保留各自的必要交互。页面只请求 Flask 的统一 API，不在浏览器连接数据库、聚合、排序或执行后端返回的 ECharts/HTML/JavaScript。

## 路由

| 路由 | 页面 |
|---|---|
| `/overview` | 运营驾驶舱 |
| `/hospitals` | 医院运营分析 |
| `/diseases` | 疾病画像分析 |
| `/cohorts` | 住院群体分析 |
| `/costs` | 费用成本分析 |
| `/risks` | 病情风险分析 |
| `/payments` | 支付方式分析 |
| `/data-quality` | 数据质量管理 |
| `/model` | 高费用分类模型 |
| `/assistant` | AI 问答与洞察报告 |

## 启动

在项目根目录启动联调快照后，再启动前端：

```powershell
$env:ANALYTICS_DATA_SOURCE='fixture'
python backend/run.py

cd frontend
npm ci
npm run dev
```

Vite 默认把 `/api` 代理到 `http://127.0.0.1:5000`。跨主机或同源部署时，可在未提交的 `frontend/.env` 设置 `VITE_API_BASE_URL`。

## 页面状态与事实边界

公共分析页只维护 `loading`、`success`、`empty`、`error` 四种互斥状态。加载新筛选或切换路由时会清除旧数据；错误态显示稳定提示、错误类型和服务返回的追踪编号，并可点击重试。

使用 `data_version` 以 `fixture:` 开头的结果时，页面会显示固定联调快照警告。fixture 只能用于并行开发、图表和四态验收，不能作为真实全量分析、模型效果或最终验收结论。

页面图表只接受冻结契约中的 `bar`、`pie`、`table`、`status` 四种 section 类型；`%` 指标按统一约定把 0—1 比例乘 100 展示，金额和记录数保留服务返回单位。

## 四态复现

- `loading`：打开任一分析路由，在 API 响应完成前观察加载面板；切换筛选时也会重新进入该状态。
- `success`：使用 fixture 后端打开 `/overview` 或其他已有快照的路由。
- `empty`：进入 `/cohorts`，选择合法但尚未发布聚合的筛选组合（例如年龄组 `50 to 69`），页面保留版本信息并显示空结果面板。
- `error`：让 Flask 暂停或以缺少分析数据源的配置启动，页面显示错误面板、错误类型和重试按钮；恢复 fixture 后点击重试即可重新加载。

正式验收必须替换为真实快照、MySQL 和 API 证据；本 README 不把 fixture 或本地页面运行误写成真实链路已通过。

## 构建

```powershell
npm run build
```
