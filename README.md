# 医数云策

医数云策是一套面向医院运营管理人员和医疗数据分析人员的住院运营分析系统。系统读取 2021 年纽约州 SPARCS 住院出院数据，以可复查的统计口径生成医院、疾病、住院记录群体、费用成本、病情严重程度和支付方式等汇总结果，并通过网页、分类模型和受控 AI 问答提供分析入口。

数据中的一行表示一次住院出院记录，不表示唯一患者。系统不提供个人诊断、处方、治疗建议或跨次住院追踪。

## 系统能力

| 能力 | 入口 | 项目状态 |
|---|---|---|
| 运营驾驶舱 | `/overview` | 真实数据、MySQL、API 与页面证据齐备 |
| 医院运营分析 | `/hospitals` | 真实数据、MySQL、API 与页面证据齐备 |
| 疾病画像分析 | `/diseases` | 真实数据、MySQL、API 与页面证据齐备 |
| 住院记录群体分析 | `/cohorts` | 真实数据、MySQL、API 与页面证据齐备 |
| 费用与成本分析 | `/costs` | 真实数据、MySQL、API 与页面证据齐备 |
| 病情严重程度与风险分析 | `/risks` | 真实数据、MySQL、API 与页面证据齐备 |
| 支付方式分析 | `/payments` | 真实数据、MySQL、API 与页面证据齐备 |
| 数据质量 | `/data-quality` | 代码、接口和页面可运行，纳入整体验收 |
| 高费用记录分类 | `/model` | 训练、指标、预测接口和页面可运行，纳入真实模型验收 |
| AI 问答与洞察报告 | `/assistant` | 接口和页面可运行，真实调用依赖 DeepSeek 密钥与网络验收 |

联调快照用于验证接口、页面和错误状态，版本以 `fixture:` 开头；它不表示真实数据结论。各模块的执行记录位于 `evidence/`，最终状态以对应验收证据为准。

## 数据链路

```text
SPARCS CSV
  → PySpark 清洗与聚合
  → 统一分析快照与模型工件
  → MySQL 事务发布
  → Flask 白名单 API
  → Vue / ECharts 页面
  → DeepSeek 白名单分析工具

HDFS 原始副本与 Hive 外部表用于课程环境检查，不承担重复统计。
```

浏览器不连接数据库、不执行 SQL、不重新聚合正式结果。AI 只能调用登记过的分析工具，不能访问原始住院明细或自由执行 SQL。

## 本地启动

### 环境要求

- Python 3.11；
- Node.js 22 LTS 与 npm；
- 仅运行联调快照时不需要 MySQL、Hadoop、Hive、完整 CSV 或 DeepSeek 密钥。

以下命令均在仓库根目录执行。

### 1. 启动后端

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
.\.venv\Scripts\python.exe backend\run.py
```

看到 Flask 监听 `http://127.0.0.1:5000` 后，可在另一个终端检查：

```powershell
curl.exe http://127.0.0.1:5000/api/v1/health
curl.exe http://127.0.0.1:5000/api/v1/dashboard/overview
```

### 2. 启动前端

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173/overview`。Vite 把 `/api` 请求转发到 `http://127.0.0.1:5000`。停止服务时在各自终端按 `Ctrl+C`。

### 3. 验证工程

```powershell
.\.venv\Scripts\python.exe -m pip install -r data\requirements.txt
.\.venv\Scripts\python.exe -m pytest backend\tests data\tests -q
cd frontend
npm run build
```

## 真实数据运行

真实模式需要完整 SPARCS CSV、MySQL 8.0 和本机未提交的 `backend/.env`。完整 CSV、数据库口令、分析快照、模型工件和 API 密钥不得提交 Git。

```powershell
.\.venv\Scripts\python.exe data\src\run_full_analytics_pyspark.py `
  --input "<SPARCS CSV 路径>" `
  --output "<输出目录>\analytics-snapshot.json"

.\.venv\Scripts\python.exe data\src\train_high_cost_model_pyspark.py `
  --input "<SPARCS CSV 路径>" `
  --artifact "<输出目录>\high-cost-model.json" `
  --metrics "<输出目录>\high-cost-metrics.json" `
  --snapshot "<输出目录>\analytics-snapshot.json"

# 在 MySQL 中执行 data/sql/002-analysis-snapshot.sql 后发布同一批快照
.\.venv\Scripts\python.exe data\src\publish_analytics_snapshot_mysql.py `
  --input "<输出目录>\analytics-snapshot.json" --apply
```

在 `backend/.env` 中设置 `ANALYTICS_DATA_SOURCE=mysql`、MySQL 连接信息和 `HIGH_COST_MODEL_PATH`，再按本地启动流程运行后端与前端。AI 页面还需要 `DEEPSEEK_API_KEY`。详细检查步骤见 [开发与运行手册](docs/04-development-and-runbook.md)。

## 文档入口

- [项目概览](docs/00-project-overview.md)：产品目标、范围、模块和状态；
- [数据与可行性](docs/01-data-and-feasibility.md)：数据来源、字段和全量核验；
- [疾病病例量 TOP10 契约](docs/02-metrics-and-data-contract.md)：指标定义和服务结果；
- [系统架构与环境](docs/03-architecture-and-env.md)：组件职责和数据边界；
- [开发与运行手册](docs/04-development-and-runbook.md)：安装、启动、真实发布和排障；
- [API 契约](docs/05-api.md)：接口、参数、响应和错误语义；
- [测试与验收](docs/06-test-and-acceptance.md)：自动化、真实链路和证据要求；
- [公共产品契约](docs/07-terminal-product-contract.md)：统一快照、模块键和模型/AI 边界；
- [业务术语表](CONTEXT.md)：全项目统一词汇。

老师提供的医疗材料和第 1 组项目工件仅作为课程参考。第 2 组的产品事实以本仓库代码、公共文档和验收证据为准。