# 医数云策智慧医疗运营大数据与AI决策分析平台

医数云策是本项目简称，正式名称为“医数云策智慧医疗运营大数据与AI决策分析平台”。平台面向医院运营管理人员和医疗数据分析人员，读取 2021 年纽约州 SPARCS 住院出院数据，以可复查的统计口径生成医院、疾病、住院记录群体、费用成本、病情严重程度和支付方式等汇总结果，并通过网页、分类模型和受控 AI 问答提供分析入口。

数据中的一行表示一次住院出院记录，不表示唯一患者。系统不提供个人诊断、处方、治疗建议或跨次住院追踪。

## 系统能力

| 能力 | 入口 | 项目状态 |
|---|---|---|
| 运营总览与专题分析 | `/overview` | 默认进入运营总览大屏；总览顶部提供医院、疾病、群体、费用、严重程度和支付方式专题入口 |
| 医院运营分析 | `/hospitals` | 真实数据、MySQL、API 与页面证据齐备 |
| 疾病画像分析 | `/diseases` | 真实数据、MySQL、API 与页面证据齐备 |
| 住院记录群体分析 | `/cohorts` | 真实数据、MySQL、API 与页面证据齐备 |
| 费用与成本分析 | `/costs` | 真实数据、MySQL、API 与页面证据齐备 |
| 病情严重程度与风险分析 | `/risks` | 真实数据、MySQL、API 与页面证据齐备 |
| 支付方式分析 | `/payments` | 真实数据、MySQL、API 与页面证据齐备 |
| 数据质量校验 | 后端接口 `/api/v1/data-quality/summary` | 保留批次、缺失和口径校验能力；无独立前端页面 |
| 高费用记录分类 | 后端接口 `/api/v1/models/high-cost/*` | 保留训练、指标和预测能力；无独立前端页面 |
| AI 问答与洞察报告 | `/assistant` | 接口和页面可运行，真实调用依赖 DeepSeek 密钥与网络验收 |

联调快照用于验证接口、页面和错误状态，版本以 `fixture:` 开头；它不表示真实数据结论。各模块的执行记录位于 `evidence/`，最终状态以对应验收证据为准。

本 README 的本地启动流程默认按真实模式配置：页面从已发布的 MySQL 分析快照读取真实的 2021 年 SPARCS 全量批次。它不是实时生产数据，接口返回的 `data_version` 应为真实批次版本，不能以 `fixture:` 开头。

## 数据链路

```text
HDFS 原始 CSV / Hive 外部表
  → PySpark（本地模式）读取、清洗与聚合
  → 统一分析快照与模型工件
  → MySQL 事务发布
  → Flask 白名单 API
  → Vue / D3 SVG 页面
  → DeepSeek 白名单分析工具

HDFS 保存原始数据，Hive 外部表提供结构化访问；PySpark 的清洗与分析逻辑不变，MySQL 继续承担面向页面的结果服务。
```

浏览器不连接数据库、不执行 SQL、不重新聚合正式结果。AI 只能调用登记过的分析工具，不能访问原始住院明细或自由执行 SQL。

## 本地启动

### 环境要求

- Python 3.11；
- Node.js 22 LTS 与 npm；
- 真实启动需要 MySQL 8.0、已发布的分析快照和真实高费用模型工件；重新生成批次时还需要能访问 Hadoop/Hive 集群的 Java/PySpark 环境。完整 CSV 只作为 HDFS 原始副本保存，AI 页面另需 DeepSeek 密钥。

以下命令均在仓库根目录执行。

### 1. 配置真实数据源并启动后端

启动 Flask：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```



### 2. 启动前端

```powershell
cd D:\HuaDi\project\yishuyunce-medical-analytics\frontend
npm ci --cache D:\HuaDi\.npm-cache-medical-analytics
npm run dev
```

访问 `http://localhost:5173/overview`。Vite 把 `/api` 请求转发到 `http://127.0.0.1:5000`。停止服务时在各自终端按 `Ctrl+C`。不要在 `npm run dev` 正在运行时再次执行 `npm ci`，否则 Windows 可能无法删除正在使用的 Rollup 原生模块。

### 3. 验证工程

```powershell
.\.venv\Scripts\python.exe -m pip install -r data\requirements.txt
.\.venv\Scripts\python.exe -m pytest backend\tests data\tests -q
cd frontend
npm test
npm run build
```

## 重新生成或发布真实数据（需要时）

真实模式不在浏览器请求时重新读取 CSV，而是读取由真实 CSV 生成并发布到 MySQL 的统一快照。完整 CSV、数据库口令、分析快照、模型工件和 API 密钥不得提交 Git。当前工作区的真实批次工件位于 `D:\HuaDi\analytics-output`，已存在时不必重复计算。

```powershell
.\.venv\Scripts\python.exe data\src\run_full_analytics_pyspark.py `
  --input "hdfs://hadoop001:9000/project/yishuyunce/raw/sparcs/2021/Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv" `
  --input-sha256 "185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219" `
  --data-version "sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219" `
  --hdfs-status VERIFIED `
  --hive-status VERIFIED `
  --output "<输出目录>\analytics-snapshot.json"

.\.venv\Scripts\python.exe data\src\train_high_cost_model_pyspark.py `
  --input "hdfs://hadoop001:9000/project/yishuyunce/raw/sparcs/2021/Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv" `
  --input-sha256 "185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219" `
  --data-version "sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219" `
  --artifact "<输出目录>\high-cost-model.json" `
  --metrics "<输出目录>\high-cost-metrics.json" `
  --snapshot "<输出目录>\analytics-snapshot.json"

# 在 MySQL 中执行 data/sql/002-analysis-snapshot.sql 后发布同一批快照
.\.venv\Scripts\python.exe data\src\publish_analytics_snapshot_mysql.py `
  --input "<输出目录>\analytics-snapshot.json" --apply
```

发布器读取当前 PowerShell 会话中的 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD` 和 `MYSQL_DATABASE`；仅写入 `backend/.env` 不会自动让数据发布脚本读取这些变量。发布成功后，再在 `backend/.env` 中设置 `ANALYTICS_DATA_SOURCE=mysql`、`TOP10_DATA_SOURCE=mysql` 和 `HIGH_COST_MODEL_PATH`，重启 Flask。AI 页面还需要 `DEEPSEEK_API_KEY`。详细检查步骤见 [开发与运行手册](docs/04-development-and-runbook.md)。

## 联调快照（可选）

只有在开发接口或验证页面状态时，才将两个数据源显式改为：

```dotenv
TOP10_DATA_SOURCE=fixture
ANALYTICS_DATA_SOURCE=fixture
TOP10_FIXTURE_STATE=success
```

此时页面显示的是演示数据，不得将其数值写成真实运营结论。

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
