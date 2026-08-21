# 医数云策前端

前端为住院运营分析提供十个页面入口。八个分析页复用 `AnalysisPage`、`MetricCard`、`AnalyticsChart` 和 `PageState`；高费用记录分类与 AI 问答保留各自需要的表单和结果区。

前端只请求 Flask API，不连接数据库，不在浏览器中聚合、排序或截断正式结果，也不执行接口返回的 HTML、JavaScript 或任意 ECharts 配置。

## 页面

| 路由 | 页面 |
|---|---|
| `/overview` | 运营驾驶舱 |
| `/hospitals` | 医院运营分析 |
| `/diseases` | 疾病画像分析 |
| `/cohorts` | 住院记录群体分析 |
| `/costs` | 费用与成本分析 |
| `/risks` | 病情严重程度与风险分析 |
| `/payments` | 支付方式分析 |
| `/data-quality` | 数据质量 |
| `/model` | 高费用记录分类 |
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

默认配置使用版本以 `fixture:` 开头的联调快照。Flask 监听 `http://127.0.0.1:5000`。

### 2. 启动 Vite

另开 PowerShell：

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173/overview`。Vite 将 `/api` 转发到 `http://127.0.0.1:5000`。跨主机或同源部署时，在未提交的 `frontend/.env` 中设置：

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

- 图表只接受 `bar`、`pie`、`table` 和 `status`；
- `%` 指标把接口的 0—1 比例乘 100 显示；
- 金额与记录数使用接口提供的单位；
- 筛选枚举来自 API `options`；
- 快速切换筛选时，较早请求的响应不能覆盖最后一次选择；
- 页面正文在桌面和移动端不产生横向溢出，顶部导航可在自身区域横向滚动。

## 构建

```powershell
npm ci
npm run build
```

构建产物位于 `frontend/dist`。该目录由构建生成，不作为项目事实来源。