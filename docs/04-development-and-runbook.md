# 医数云策开发与运行手册

本手册从仓库根目录开始，说明联调启动、真实数据发布、自动化验证和常见故障。所有路径示例均为相对路径；尖括号内容由执行者填写。

## 1. 环境准备

### 1.1 软件

- Git；
- Python 3.11；
- Node.js 22 LTS 与 npm 10；
- 真实数据流程需要 Java 8 或 17、MySQL 8.0，以及可访问 Hadoop/Hive 的虚拟机环境；
- 完整 SPARCS CSV 上传到 HDFS 后作为原始副本保存，Hive 外部表提供结构化访问。

检查版本：

```powershell
python --version
node --version
npm --version
java -version
```

### 1.2 获取代码

```powershell
git clone git@github.com:Martin7816/yishuyunce-medical-analytics.git
cd yishuyunce-medical-analytics
git status
```

已有仓库直接进入根目录。不要在课件目录或 `project` 外层目录执行项目命令。

## 2. 联调快照启动

联调快照适合首次运行、接口开发和页面状态验证。其 `data_version` 以 `fixture:` 开头，不表示真实全量数据结论。

### 2.1 后端

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
.\.venv\Scripts\python.exe backend\run.py
```

`backend/.env.example` 已显式设置：

```dotenv
TOP10_DATA_SOURCE=fixture
ANALYTICS_DATA_SOURCE=fixture
```

服务监听 `http://127.0.0.1:5000`。在另一个终端检查：

```powershell
curl.exe http://127.0.0.1:5000/api/v1/health
curl.exe http://127.0.0.1:5000/api/v1/dashboard/overview
curl.exe http://127.0.0.1:5000/api/v1/diseases/top10
```

### 2.2 前端

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173/overview`。默认路由见 [前端说明](../frontend/README.md)。后端和前端分别在各自终端按 `Ctrl+C` 停止。

## 3. 真实数据流程

### 3.1 创建数据环境

```powershell
.\.venv\Scripts\python.exe -m pip install -r data\requirements.txt
```

确保 `JAVA_HOME` 指向 Java 8，并在运行 PySpark 的终端加载 Hadoop/Hive 配置。当前课程集群的原始数据位置和 Hive 表为：

```text
HDFS:  /project/yishuyunce/raw/sparcs/2021/Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv
Hive:  analytics_check.sparcs_2021_raw_issue39
NameNode 示例: hdfs://hadoop001:9000
```

完整 CSV、快照和模型工件不放入仓库；快照和模型工件仍写到运行终端可访问的本地输出目录。

### 3.2 生成统一分析快照

推荐直接从 HDFS 原始副本读取，PySpark 仍使用原有本地模式和原有清洗、聚合逻辑：

```powershell
.\.venv\Scripts\python.exe data\src\run_full_analytics_pyspark.py `
  --input "hdfs://hadoop001:9000/project/yishuyunce/raw/sparcs/2021/Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv" `
  --input-sha256 "185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219" `
  --data-version "sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219" `
  --hdfs-status VERIFIED `
  --hive-status VERIFIED `
  --output "<工件目录>\analytics-snapshot.json"
```

如果需要让 PySpark 通过 Hive 外部表读取同一份 HDFS 数据，将 `--input` 替换为：

```powershell
--hive-table "analytics_check.sparcs_2021_raw_issue39"
```

此时仍保留 `--input-sha256` 和 `--data-version`，确保 Hive 表输入生成的快照与 HDFS 路径输入、模型工件使用同一个批次版本。任务读取一次原始数据，生成运营驾驶舱、医院、疾病、住院记录群体、费用成本、病情风险、支付方式和数据质量等模块记录。输出必须通过公共快照结构校验，并在同一文件中使用一致的 `data_version` 与 `generated_at`。

比例口径按业务字段分别确定：页面记录数保留当前筛选后的基础记录总体；急诊率、外科率和 `Major/Extreme` 重症率分别使用对应字段的指标有效总体作分母，严重程度可判定值为 `Minor`、`Moderate`、`Major`、`Extreme`，未知值不作分子也不作非重症。驾驶舱、医院画像、疾病画像和住院记录群体通过严重程度分布对账；风险快照额外发布 `severity_valid_count`。完整字段有效数、适用数、缺失数和比例分子/分母集中在 `data_quality/summary.options.audit`，其公式版本为 `analytics-denominator-v1`；不在各业务页面重复展示质量告警。

固定边界样例可使用 `verify_dashboard_snapshot.py`、`verify_hospital_snapshot.py`、`verify_disease_snapshot.py`、`verify_cohort_snapshot.py` 和 `verify_risk_snapshot.py` 独立核对分子、分母与分布。

### 3.3 训练高费用记录分类模型

```powershell
.\.venv\Scripts\python.exe data\src\train_high_cost_model_pyspark.py `
  --input "hdfs://hadoop001:9000/project/yishuyunce/raw/sparcs/2021/Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv" `
  --input-sha256 "185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219" `
  --data-version "sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219" `
  --artifact "<工件目录>\high-cost-model.json" `
  --metrics "<工件目录>\high-cost-metrics.json" `
  --snapshot "<工件目录>\analytics-snapshot.json" `
  --repetitions 2 `
  --reproducibility "<工件目录>\reproducibility.json"
```

`--snapshot` 把模型指标写入待发布的同批分析快照；正式验收追加两次固定切分复现，比较阈值、规模、五项指标、混淆矩阵、类别结构和系数宽度。模型工件供预测接口读取，指标快照供模型页面展示。模型训练依赖以 `data/requirements.txt` 为准；脚本复用本任务的清洗口径，并将真实 SPARCS 的 `Hospital Service Area` 兼容映射为 `hospital_service_area`。

### #75 高费用病例分类模型交接

2026-08-20 使用同一真实 CSV 和 `data_version` 完成两次连续训练：训练集 1,681,301 条、测试集 420,287 条，训练集收费 P75 为 77,202.39 美元，模型版本为 `high_cost_lr_seed_20260818_185808e20900`。训练工件只暴露八个入院时类别特征，真实 `Hospital Service Area` 已映射到 `hospital_service_area`；两次训练的阈值、规模、Accuracy、Precision、Recall、F1、AUC、混淆矩阵、类别结构和系数宽度均通过复现检查。最终快照发布器 dry-run 为 7,198 条记录，模型与快照使用同一 `data_version`。详细摘要与命令见 [`evidence/75/README.md`](../evidence/75/README.md)。

### 3.4 准备 MySQL

在目标数据库执行：

```sql
SOURCE data/sql/002-analysis-snapshot.sql;
```

发布账号需要目标表的 `SELECT`、`INSERT` 和 `DELETE` 权限；API 账号只需要 `SELECT`。数据库账号、密码和主机地址写入本机 `backend/.env`，不得写入 README、代码、截图或 Git 历史。

### 3.5 发布快照

先执行校验预览：

```powershell
.\.venv\Scripts\python.exe data\src\publish_analytics_snapshot_mysql.py `
  --input "<工件目录>\analytics-snapshot.json"
```

确认记录数、模块、版本和时间后执行事务发布：

```powershell
.\.venv\Scripts\python.exe data\src\publish_analytics_snapshot_mysql.py `
  --input "<工件目录>\analytics-snapshot.json" --apply
```

发布器在同一事务中清理目标批次、写入完整快照并核对结果。任一步失败都会回滚。

### 3.6 配置后端

在未提交的 `backend/.env` 中填写：

```dotenv
TOP10_DATA_SOURCE=mysql
ANALYTICS_DATA_SOURCE=mysql
HIGH_COST_MODEL_PATH=<高费用模型工件绝对路径>

MYSQL_HOST=<MySQL 地址>
MYSQL_PORT=3306
MYSQL_USER=<只读账号>
MYSQL_PASSWORD=<密码>
MYSQL_DATABASE=medical_analytics
MYSQL_CONNECT_TIMEOUT=3
```

AI 页面需要以下配置：

```dotenv
DEEPSEEK_API_KEY=<本机密钥>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=20
```

重新启动 Flask 和前端，逐页检查 `data_version` 与 `generated_at` 是否一致。

## 4. 自动化验证

### 4.1 后端与数据

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests data\tests -q
```

### 4.2 前端

```powershell
cd frontend
npm ci
npm run build
```

### 4.3 基础接口

```powershell
curl.exe http://127.0.0.1:5000/api/v1/health
curl.exe http://127.0.0.1:5000/api/v1/dashboard/overview
curl.exe http://127.0.0.1:5000/api/v1/hospitals
curl.exe http://127.0.0.1:5000/api/v1/diseases
curl.exe http://127.0.0.1:5000/api/v1/cohorts/summary
curl.exe http://127.0.0.1:5000/api/v1/costs/overview
curl.exe http://127.0.0.1:5000/api/v1/risks/overview
curl.exe http://127.0.0.1:5000/api/v1/payments/overview
curl.exe http://127.0.0.1:5000/api/v1/data-quality/summary
curl.exe http://127.0.0.1:5000/api/v1/models/high-cost/metrics
```

自动化通过只说明代码和固定输入符合契约。真实验收还要核对 CSV、MySQL、API 和页面，并保存执行时间、提交号、数据版本、命令输出和截图。

## 5. HDFS 与 Hive 存储检查

在虚拟机中完成以下检查后，再在 PySpark 任务中使用 `--hdfs-status VERIFIED` 和 `--hive-status VERIFIED`：

1. 确认 HDFS 三个 DataNode 健康；
2. 把完整 CSV 上传为原始副本；
3. 建立 Hive 外部表并检查行数和字段；
4. 记录命令、时间和结果；
5. 运行 PySpark 时从 HDFS 或 Hive 表读取，保持原有清洗和聚合代码不变；
6. 继续将分析快照发布到 MySQL，供 Flask 和前端读取。

Windows 找不到 `hdfs`、`hive` 或 `mysql` 命令不表示集群故障；存储检查和 HDFS/Hive 输入任务应在已加载集群配置的虚拟机终端执行。

## 6. 常见问题

| 现象 | 检查方法 |
|---|---|
| `.venv` 指向不存在的 Python | 删除或移走该虚拟环境后，使用已安装的 Python 3.11 重新创建；不要提交 `.venv` |
| PySpark 提示 Java 不兼容 | 让 `JAVA_HOME` 指向 Java 8 或 17，重新打开终端 |
| `ANALYTICS_DATA_SOURCE` 配置错误 | 明确填写 `fixture` 或 `mysql`，不要留空 |
| API 返回 `DATABASE_UNAVAILABLE` | 检查 MySQL 地址、端口、账号权限和网络 |
| API 返回 `RESULT_NOT_READY` | 检查对应 `module_key/entity_key` 是否已发布 |
| 页面请求失败 | 先检查 Flask `5000` 端口，再检查 Vite 代理或 `VITE_API_BASE_URL` |
| AI 返回配置错误 | 检查 `DEEPSEEK_API_KEY`、模型名和网络；不得用固定文案冒充回答 |
| 前端构建出现 chunk 大小警告 | 构建成功不受影响；记录警告并在性能验收中评估 |

## 7. 交付检查

- `git status` 中没有密钥、`.env`、完整 CSV、快照或模型工件；
- 后端与数据测试通过；
- 前端构建通过；
- 八个页面均可打开，loading、success、empty、error 和 retry 行为明确；
- 真实模块的 MySQL、API 和页面使用同一数据版本；
- 模型输入不含收费、成本、住院时长或出院后字段；
- AI 回答包含工具轨迹、来源指标、数据版本和统计边界；
- 执行证据进入对应 `evidence/<Issue>/` 或 Issue 评论。
