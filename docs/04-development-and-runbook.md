# M0/M1 开发、运行与组长电脑复现手册

> 终局更新（2026-08-18）：M1 TOP10 复现记录继续保留；完整产品新增的统一快照、模型、十页前端和 AI 启动以本节为准，冻结契约见 [07-terminal-product-contract.md](07-terminal-product-contract.md)。

## 终局产品快速运行

联调模式：复制 `backend/.env.example` 为未提交的 `backend/.env`，保持 `ANALYTICS_DATA_SOURCE=fixture`；后端执行 `python -m pip install -r backend/requirements.txt` 和 `python backend/run.py`，前端执行 `cd frontend; npm ci; npm run dev`，访问 `http://127.0.0.1:5173/overview`。联调版本以 `fixture:` 开头，不能作为真实验收证据。

真实模式按顺序执行：

1. `run_full_analytics_pyspark.py --input <CSV> --output <snapshot.json>`；
2. `train_high_cost_model_pyspark.py --input <CSV> --artifact <model.json> --metrics <metrics.json>`；
3. MySQL 执行 `data/sql/002-analysis-snapshot.sql`；
4. `publish_analytics_snapshot_mysql.py --input <snapshot.json> --apply`；
5. 设置 `ANALYTICS_DATA_SOURCE=mysql`、`HIGH_COST_MODEL_PATH=<model.json>`；
6. 启动 Flask、Vue，并逐页核对同一 `data_version`；
7. AI 演示前只在本机设置 `DEEPSEEK_API_KEY`，验证正常、超时、模型错误和断网场景。

完整 CSV、快照工件、模型工件、真实 `.env` 和 API Key 均不提交 Git。前端通过 Vite `/api` 代理访问 Flask；部署时应保持同源或由反向代理提供 `/api/v1`。

### #39 真实数据任务交接

2026-08-18 已按上述命令完成真实全量快照、模型工件、独立 dashboard 核对，并完成 MySQL 正式发布。输入文件的 SHA-256 为 `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，最终快照为 691 条记录，快照与模型统一使用 `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`。发布后 MySQL 行数、版本/时间唯一性、真实 API 和事务回滚均已复验；HDFS 三节点和 Hive 外部表检查也已完成。可复查 stdout 和证据见 [`evidence/39/README.md`](../evidence/39/README.md)。

Issue #39 的真实数据发布和支撑层复验已完成：`analysis_snapshot_result` 已建表并授予发布账号所需权限，`--apply` 实际写入 691 条记录；真实 MySQL API 返回 200，故障注入回滚后旧批次保持可读；HDFS 报告 3 个 Live DataNode 且块健康，HiveServer2 和外部表检查通过。详细结果与下游配置见 `evidence/39/`。

> 关联 Issue：#12
>
> 基线日期：2026-08-17
>
> 本手册只记录已经核验的环境事实和当前仓库能够执行的最小命令。#9、#10、#11、#13 尚未把业务数据任务、API、前端和端到端证据合并到 `main`，因此本手册不会把这些下游内容写成已经完成。

## 1. 运行边界

第一轮只围绕“疾病病例量 TOP10”建立最小链路：

```text
Windows/VM 本地暂存
  → HDFS raw
  → Spark 唯一正式计算
  → HDFS result
  → MySQL 服务结果
  → Flask API
  → Vue + ECharts
```

当前仓库的可复现层次如下：

| 层次 | 当前状态 | 可复查内容 |
|---|---|---|
| M0 固定样例 | `VERIFIED` | 纯 Python 标准库读取样本、独立计数、TOP10 和契约边界 |
| VM 环境基线 | `VERIFIED` | 三台 CentOS 7 64 位虚拟机、Hadoop/HDFS、MySQL，以及 Hive 和 `spark-submit` 的既有实机记录 |
| Spark 全量任务 | `VERIFIED` | 本机 PySpark 3.4.0 已读取真实全量 CSV 并生成服务结果工件；脚本见 `data/src/run_sparcs_top10_pyspark.py` |
| MySQL 服务结果发布 | `VERIFIED` | #31 已通过真实 `--apply`、提交后查询和失败回滚复验；当前批次为 10 行 |
| Flask API | `VERIFIED` | #10 的 PR #29 已合并；本机 `.env` 已切到 MySQL 并完成真实 HTTP 200 响应核对，默认示例仍可使用 fixture |
| Vue/ECharts 页面 | `HANDOFF` | 由 #11 固定页面四态和 API 地址后再维护前端依赖 |
| 全链路一致性 | `HANDOFF` | 由 #13 按固定样例和全量版本复验 |

这里的 `HANDOFF` 是有意保留的边界，不表示可以用 Mock、假数据或未提交代码代替真实验收。

## 2. 版本与组件基线

### 2.1 组长电脑

以下结果来自组长电脑在 2026-08-17 的命令核验。绝对安装路径不写入仓库，避免把其他成员的环境绑定到本机目录。

| 项目 | 实测基线 | 用途和边界 |
|---|---|---|
| 操作系统 | Windows 11 家庭中文版，`10.0.22631`，`64` 位 | VMware、WindTerm、Git 和本地固定样例 |
| PowerShell | `7.6.4`，`Core` | 文档中的 Windows 命令 shell |
| Git | `2.45.1.windows.1` | 获取干净 `main`、查看提交和协作 |
| Python | `3.11.4` | 当前 M0 核对脚本；只用标准库，不需要 `pip install` |
| Node.js | `v22.13.1` | 当前主机前置条件；`main` 尚无前端代码 |
| npm | `10.9.2` | 当前主机前置条件；依赖清单由 #11 维护 |
| Java | `1.8.0_202` | 主机上可见，但不是 Hadoop VM 的目标 Java 基线 |
| `hdfs`/`hive`/`spark-submit`/`mysql` | 不在 Windows PATH | 这是预期边界；大数据命令在 CentOS VM 中执行 |

成员电脑的操作系统和架构不要求完全相同，但当前仓库只收到了组长电脑的实际核验结果；没有其他成员的命令输出时不填猜测值。其他成员只要能获取仓库、运行固定样例，并通过 WindTerm/VM 执行集群命令即可。待各成员提交信息后，按同一格式追加：

| 成员 | 操作系统/架构 | 必要命令 | 当前登记状态 |
|---|---|---|---|
| 王敬博（组长） | Windows 11，64 位 | Git、Python、VMware/WindTerm | `VERIFIED`，见上表 |
| 叶艺鑫 | 未提供 | Git、Python；后端依赖由 #10 固定 | 待本人补充 |
| 魏世轩 | 未提供 | Git、Python；数据工具依赖由数据 Issue 固定 | 待本人补充 |
| 胡钰炜 | 未提供 | Git、Python；验收命令由 #13 固定 | 待本人补充 |
| 李佳明 | 未提供 | Git、Node/npm；前端依赖由 #11 固定 | 待本人补充 |

检查本机前置条件：

```powershell
git --version
python --version
node --version
npm --version
java -version

# 这些命令在 Windows 找不到并不表示集群故障；不要为了消除提示把 VM 软件安装到 Windows PATH。
Get-Command hdfs,hive,spark-submit,mysql -ErrorAction SilentlyContinue
```

### 2.2 VMware 三节点

VMware 配置为 CentOS 7 64 位来宾，三台机器的项目地址和职责如下。`guestOS=centos7-64` 及 `x86_64` 安装介质是本机 VM 配置证据；服务版本和端口以 VM 内命令输出为准。

| 主机 | 地址 | 角色 | VM 配置 |
|---|---|---|---|
| `hadoop001` | `192.168.219.128` | NameNode、DataNode、SecondaryNameNode、ResourceManager、NodeManager、MySQL | 4 vCPU，4 GB |
| `hadoop002` | `192.168.219.129` | DataNode、NodeManager | 2 vCPU，1 GB |
| `hadoop003` | `192.168.219.130` | DataNode、NodeManager | 2 vCPU，1 GB |

已经记录的 VM 软件基线：

| 组件 | 实测版本/状态 | 说明 |
|---|---|---|
| JDK | `1.8.0_212` | 三节点大数据运行环境；不要用主机 Java 版本替代 |
| Hadoop | `3.3.4` | HDFS/YARN；`hadoop001` 为启动入口 |
| Hive | `3.1.3` | 只登记元数据和执行检查，不重新计算正式 TOP10 |
| MySQL | `8.0.30` | Hive 元数据库和后续业务服务结果库使用不同逻辑边界 |
| Spark | `spark-submit` 已确认可用 | 本仓库证据尚未保存具体版本字符串；首次进入 VM 时用下方命令补录，不凭空指定版本 |
| Python/Node/Flask/Vue/ECharts | 不作为 VM 基线 | Python 核对脚本在组长电脑执行；后端和前端依赖分别由 #10/#11 提供 |

补录 VM 版本时，在 `hadoop001` 执行以下只读命令，并把输出摘要写入 Issue 或后续证据，不要写入密码和个人路径：

```bash
hostname
uname -m
cat /etc/centos-release
java -version
hadoop version
hive --version
spark-submit --version
/opt/module/mysql/bin/mysql --version
```

### 2.3 端口和地址

| 服务 | 地址/端口 | 当前用途 | 状态判断 |
|---|---|---|---|
| HDFS NameNode RPC | `hadoop001:9000` | Spark/HDFS 读写 | 已在集群配置和实机记录中确认 |
| NameNode Web | `hadoop001:9870` | 查看 HDFS 状态 | 已在实机记录中确认监听 |
| YARN ResourceManager Web | `hadoop001:8088` | 查看 YARN 状态 | 已在实机记录中确认监听 |
| HiveServer2 | `hadoop001:10000` | Hive 表/查询检查 | 启动后用 `ss -lntp` 复核；不承担 TOP10 正式计算 |
| MySQL TCP | `hadoop001:3306` | 教师配置中的 MySQL 监听端口 | 使用 MySQL 启动后复核；本机连接优先记录 socket |
| MySQL Unix socket | `/opt/module/mysql/mysql.sock` | `hadoop001` 本地客户端连接 | 已在实际配置中确认 |
| Flask | `127.0.0.1:5000`（目标） | 由 #10 的 `docs/05-api.md` 固定 | 当前 `main` 已有后端；默认数据源仍为 fixture |
| Vue/Vite | 未固定 | #11 固定页面启动方式后再确定 | 当前 `main` 无前端 |

M1 不单独固定 Spark Standalone 端口：正式计算由 `spark-submit` 按数据任务配置提交，当前架构没有把一套额外的 Spark Master 服务加入必要链路。

## 3. 依赖与配置归属

### 3.1 当前仓库的最小依赖

M0 样本核对只使用 Python 标准库中的 `argparse`、`csv`、`json`、`pathlib`、`collections` 和 `subprocess`。因此从干净 `main` 开始不创建虚拟环境也可以运行固定样例；如果成员需要隔离环境，可以自行创建 `.venv`，但不能把环境目录提交 Git。

当前不存在 `backend/`、`frontend/` 或正式 Spark 作业目录。为了避免引入没有调用者的依赖，#12 不提前创建 Flask、数据库驱动、Vue、ECharts 或 Spark Python 包的伪清单。

### 3.2 下游依赖的唯一归属

| 内容 | 归属文件 | 当前状态 |
|---|---|---|
| Flask 和 MySQL 查询依赖 | `backend/requirements.txt` | 由 #10 在后端代码落位时创建或更新 |
| 后端环境变量示例 | `backend/.env.example` | 由 #9/#10 固定表和连接字段后创建；真实 `backend/.env` 只在本地存在 |
| Vue/ECharts 构建依赖 | `frontend/package.json` | 由 #11 在页面原型确认后创建或更新 |
| 前端地址示例 | `frontend/.env.example` | 由 #10/#11 共同固定 API 地址后创建；不与后端变量混用 |
| HDFS raw/result 路径 | 数据任务参数 | 不写入后端 `.env`；由 Spark 任务参数管理 |
| Hive 配置 | Hive 自己的配置目录 | 不作为 API 业务数据库 |
| MySQL 业务连接 | 后端 `.env` | 不提交密码、Token、API Key 或真实 `.env` |

这项归属决定了后续变更顺序：先由 #9 固定服务结果表和 `data_version`，再由 #10 固定后端连接变量和 API，最后由 #11 固定前端 API 地址。#12 不复制一份会与下游漂移的空配置。

## 4. 从干净 `main` 运行固定样例

这是当前 `main` 不依赖下游服务、可直接复查固定样例的基础路径。建议在不含中文、空格且路径较短的本地目录执行；仓库本身不依赖特定绝对路径。

```powershell
# 任选一个短路径；示例路径不是项目固定路径
git clone git@github.com:Martin7816/yishuyunce-medical-analytics.git yishuyunce-medical-analytics
Set-Location .\yishuyunce-medical-analytics
git switch main
git pull --ff-only

python --version
python data/src/verify_sparcs_mvp.py
```

不需要执行 `pip install -r requirements.txt`：当前固定样例没有第三方 Python 依赖。成功输出必须包含：

```text
"status": "PASS"
"rows": 16
"malformed_rows": 0
"out_of_scope_rows": 0
"diagnosis_nonempty_rows": 15
"diagnosis_nonempty_distinct": 12
```

有本地完整 SPARCS CSV 时才执行全量复核；路径只作为命令行参数传入，不写入仓库：

```powershell
python data/src/verify_sparcs_mvp.py --full-source "<本地完整 SPARCS CSV 路径>"
```

全量复核要求与 `docs/01-data-and-feasibility.md` 中同一版本文件一致：2,101,588 条记录、0 条解析异常、477 个非空主诊断描述，TOP10 与记录的基线一致。没有完整文件时不要用固定样例结果冒充全量结果。

### 4.1 真实全量 TOP10 与服务结果工件

2026-08-18 已在组长电脑使用本机 PySpark 3.4.0 读取老师提供的完整 CSV，生成小型服务结果工件。完整 CSV 和工件均不提交 Git；命令中的路径只替换为本机实际路径：

```powershell
python -m pip install -r data/requirements.txt
python data/src/run_sparcs_top10_pyspark.py `
  --input "<本地完整 SPARCS CSV 路径>" `
  --expected data/fixtures/sparcs_mvp_expected_top10.json `
  --output "<本地临时目录>\issue10-real-service-result.json"
python data/src/verify_service_result_contract.py `
  --result "<本地临时目录>\issue10-real-service-result.json" `
  --expected-scope full_scan
python data/src/publish_top10_mysql.py `
  --input "<本地临时目录>\issue10-real-service-result.json"
```

本次实际结果为：2,101,588 行、0 条解析异常、0 条范围外记录、2,099,954 条非空诊断记录、477 个诊断分组；服务结果有 10 行，版本为 `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`。独立标准库核对和 PySpark 结果的 TOP10 完全一致。最后一条命令默认只做本地校验；连接到已执行 DDL 的 MySQL 时才增加 `--apply`，并提供 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE` 环境变量。

### 4.2 运营驾驶舱全量快照（Issue #43）

驾驶舱与其他分析模块复用同一份 PySpark 清洗帧，输出统一 `data_version`、`generated_at` 和 `analysis_snapshot_result` 记录。正式聚合不收集原始行；dashboard 只发布 overview 指标、年龄结构、主支付方式、疾病/医院 TOP10 和严重程度分布。

```powershell
python data/src/run_full_analytics_pyspark.py `
  --input "<本地完整 SPARCS CSV 路径>" `
  --output "<本地临时目录>\real-full.json" `
  --module all `
  --generated-at 2026-08-18T08:00:00Z
python data/src/verify_dashboard_snapshot.py `
  --input "<本地完整 SPARCS CSV 路径>" `
  --snapshot "<本地临时目录>\real-full.json"
python data/src/publish_analytics_snapshot_mysql.py `
  --input "<本地临时目录>\real-full.json"
```

发布前必须先执行 `data/sql/002-analysis-snapshot.sql` 并授予发布账号目标表的 `SELECT, INSERT, DELETE` 权限；`--apply` 会在一个事务中替换整批快照并校验行数、版本和时间戳。真实 CSV 不提交仓库，完整执行记录见 `evidence/43/README.md`。

### 4.3 医院运营分析快照（Issue #47）

医院模块沿用统一清洗帧，按字符串 `facility_id` 生成 `hospitals/index` 和每个 `hospitals/profile:{facility_id}`。医院画像的病例量使用 `case_count`，平均住院时长和金额只对可解析的非负值求平均，急诊率、外科率和 Major/Extreme 重症率的分母为该机构纳入分析的住院出院记录；主要疾病严格取 TOP5，内外科结构按数量降序、名称升序排列。医院排行按机构编码聚合，不会把同名机构合并。

生成全量快照后，使用不导入 PySpark 聚合实现的标准库脚本逐机构核对：

```powershell
python data/src/verify_hospital_snapshot.py `
  --input "<本地完整 SPARCS CSV 路径>" `
  --snapshot "<本地临时目录>\real-full.json"
```

固定边界样例、真实全量医院键清单与独立核对结果见 [`evidence/47/README.md`](../evidence/47/README.md)。

### 4.4 住院记录群体分析快照（Issue #55）

群体模块继续复用 `run_full_analytics_pyspark.py` 已持久化的统一清洗帧，不重新读取 CSV。任务从 `age_group`、`gender`、`admission_type` 的有效枚举构造完整笛卡尔积：每个维度都包含 `*` wildcard，生成 `age={值或*}|gender={值或*}|admission={值或*}`；无记录组合也保留为 `metrics=[]/sections=[]` 的合法空 payload。

非空组合的记录数、急诊率、平均住院时长、平均收费和平均成本使用当前筛选后的记录分母；费用和住院时长平均值只使用对应的可解析非负值。主要疾病严格 TOP10，严重程度、年龄结构和性别结构按 `value` 降序、`name` 升序发布。`%` 值保持 0—1 比例，金额单位为美元，记录数单位为条。

固定边界样例和真实全量均使用独立标准库脚本复核：

```powershell
python data/src/run_full_analytics_pyspark.py `
  --input "<本地 CSV>" `
  --output "<本地临时目录>\cohorts-full.json" `
  --module all `
  --generated-at 2026-08-19T00:00:00Z
python data/src/verify_cohort_snapshot.py `
  --input "<本地 CSV>" `
  --snapshot "<本地临时目录>\cohorts-full.json"
python data/src/publish_analytics_snapshot_mysql.py `
  --input "<本地临时目录>\cohorts-full.json"
```

真实 CSV、快照和数据库凭证不提交 Git；#55 的实际键数量、空组合数量、版本、MySQL 对照和回滚结果以 `evidence/55/README.md` 为准。后端使用 `GET /api/v1/cohorts/summary` 按相同 entity key 读取，前端只渲染返回顺序，不在请求或页面重新聚合。

### 4.5 病情严重程度与风险快照（Issue #63）

风险模块继续复用统一清洗帧，实体键固定为 `age={值或*}|diagnosis={值或*}`，请求白名单为 `age_group`、`diagnosis_code`。年龄枚举来自纳入清洗帧，疾病选项来自诊断编码及其稳定描述标签；通配与全部有限笛卡尔积都必须发布，合法空组合保留为 `metrics=[]/sections=[]`。

风险指标的分母是当前筛选后的有效住院出院记录数；`Major`/`Extreme` 为高风险记录。快照发布高风险记录数、比例（`0—1`，单位 `%`）、高风险平均住院时长/收费/成本，并提供严重程度、死亡风险、离院去向、高风险年龄和高风险疾病 TOP10 分布。排行统一按 `value` 降序、`name` 升序，结果只作群体描述，不作诊断、治疗或因果判断。

固定边界样例和完整 CSV 均使用独立标准库脚本逐键重算，命令如下：

```powershell
python data/src/run_full_analytics_pyspark.py `
  --input "<本地 CSV>" `
  --output "<本地临时目录>\real-full.json" `
  --module all `
  --generated-at 2026-08-19T00:00:00Z
python data/src/verify_risk_snapshot.py `
  --input "<本地 CSV>" `
  --snapshot "<本地临时目录>\real-full.json"
python data/src/publish_analytics_snapshot_mysql.py `
  --input "<本地临时目录>\real-full.json"
```

风险快照的固定样例为 12 个键（8 个非空、4 个空组合）；本次真实 CSV 为 2,868 个键（2,614 个非空、254 个空组合），5 个年龄枚举、477 个诊断编码，原始/纳入记录均为 2,101,588。独立核对、MySQL 逐键比较和事务回滚的实际输出见 [`evidence/63/README.md`](../evidence/63/README.md)。

## 5. VM 启动、健康检查与停止

### 5.1 启动前检查

1. 在 VMware 中启动三台 VM，确认三台主机都能进入 CentOS；在 `hadoop001` 执行 `ssh hadoop002 hostname` 和 `ssh hadoop003 hostname`。
2. 从组长电脑只检查 SSH 可达性，不要求 Windows 能直接执行 `hdfs`：

   ```powershell
   Test-NetConnection 192.168.219.128 -Port 22
   ```

3. 所有 Linux 命令在 `hadoop001` 终端执行，所有需要密码的命令都使用交互式输入；密码不写入脚本、文档或 Issue。

### 5.2 按顺序启动

#### MySQL

```bash
sudo systemctl start mysql8
sudo systemctl --no-pager status mysql8
/opt/module/mysql/bin/mysql --socket=/opt/module/mysql/mysql.sock -uroot -p -e 'SELECT VERSION();'
ss -lntp | grep ':3306'
```

第一次初始化 Hive 元数据库前，确认 MySQL 已正常启动。若 MySQL 因残留 socket 锁文件启动失败：

```bash
ps -ef | grep '[m]ysqld'
# 只有确认没有 mysqld 进程后，才清理 socket/lock 临时文件；不要操作 mysql/data。
sudo rm -f /opt/module/mysql/mysql.sock /opt/module/mysql/mysql.sock.lock
sudo systemctl start mysql8
```

#### Hadoop/YARN

```bash
cd /opt/module/hadoop
sbin/start-all.sh
jps
hdfs dfsadmin -report
```

健康检查要求：`Live datanodes (3)`，三台节点 `Decommission Status` 为 `Normal`，`Missing`、`Corrupt` 和 `Under replicated blocks` 均为 0。

#### HiveServer2

```bash
cd /opt/module/hive
bin/schematool -dbType mysql -info

# 只有上条命令明确提示 schema 尚未初始化时，才手动执行下面这条；已初始化时不要重复执行。
# bin/schematool -dbType mysql -initSchema

hive --service hiveserver2 > "$HIVE_HOME/hiveserver2.log" 2>&1 &
ss -lntp | grep ':10000'
```

如果 `schematool -info` 已能读取 schema，跳过 `-initSchema`；如果 HiveServer2 启动失败，先查看 `$HIVE_HOME/hiveserver2.log`，不要改用 Hive 重新计算 TOP10。

#### Spark 和业务服务

当前 `main` 已有本机 PySpark 正式计算脚本、MySQL 服务结果发布脚本和 #10 Flask API；#31 已完成真实 MySQL 装载、回滚保护和 API 真数据验收。本机默认 `.env` 已设置 `TOP10_DATA_SOURCE=mysql`，未配置 `.env` 时仍回退到 fixture。下游完成后必须按下面的顺序接入：

```text
本机 Spark 正式任务读取受控 CSV
  → 生成并校验服务结果工件
  → 事务装载 MySQL 服务结果
  → 启动 Flask，只读 MySQL
  → 启动 Vue，只读 Flask API
```

对应的实际命令由 #9、#10、#11 固定后，再由 #13 在本手册或验收文档中补齐；任何临时 Mock 只能用于并行开发，不算真实复现。

### 5.3 停止顺序

按“前端 → Flask → HiveServer2 → Hadoop/YARN → MySQL → VMware”逆序停止。当前已有组件可执行：

```bash
cd /opt/module/hadoop
sbin/stop-all.sh
sudo systemctl stop mysql8
```

HiveServer2 应根据启动时记录的 PID 或服务管理方式停止，停止前确认不要误杀其他 Java 进程。最后再从 VMware 界面正常关机，不直接删除或移动虚拟磁盘。

## 6. 常见问题与降级

| 现象 | 判断和处理 |
|---|---|
| Windows 找不到 `hdfs`、`hive` 或 `mysql` | 预期边界；通过 WindTerm/VM 终端执行，不修改 Windows PATH |
| 仓库路径含中文、空格或过长 | 优先换到短的 ASCII 路径；固定样例不依赖绝对路径，VM 上传路径另由任务参数设置 |
| SSH 不通 | 先确认三台 VM 已启动、IP 未变化，再在 `hadoop001` 检查互相 SSH；不把密码写进仓库 |
| 端口已占用 | Windows 用 `Get-NetTCPConnection -LocalPort <端口>`，Linux 用 `ss -lntp`；先确认进程归属，不盲目结束未知进程 |
| MySQL 启动失败 | 先看 `systemctl status mysql8` 和错误日志；只有确认无 `mysqld` 时才清理 socket/lock，不碰数据目录 |
| HDFS 报告节点不足或块异常 | 停止正式全量任务，先恢复三节点和 HDFS 健康状态；不能切换到另一份未登记原始数据 |
| HiveServer2 不可用 | 只影响 Hive 检查层；Spark 正式计算仍不能改由 Hive/Pandas 另算，页面/API也不填假数据 |
| 完整原始 CSV 不存在 | 运行固定样例或独立核对；不能声称已完成全量结果 |
| PySpark/MySQL 数据依赖未安装 | 按 `data/requirements.txt` 安装；固定样例独立核对不需要第三方依赖，但不能用它冒充真实计算 |
| Flask 默认仍为 fixture | 可用固定 Mock 做契约开发；真实验收必须设置 `TOP10_DATA_SOURCE=mysql`，并确认 API 返回本 Issue 发布的 `data_version` |

## 7. 组长电脑复现记录

### 7.1 本次可直接复现的记录

在仓库根目录执行：

```powershell
python data/src/verify_sparcs_mvp.py
```

实际结果：进程退出码为 0，顶层 `status=PASS`；固定样例 `rows=16`、`malformed_rows=0`、`out_of_scope_rows=0`、非空诊断记录 `15`、非空诊断值 `12`，TOP10 与 `data/fixtures/sparcs_mvp_expected_top10.json` 一致。

本次同时确认：

- 组长电脑可执行 Git、Python、Node/npm 和 Java 版本检查；
- Windows 不提供 `hdfs`、`hive`、`spark-submit`、`mysql` 命令，符合 VM 运行边界；
- 仓库没有真实 `.env`、完整原始 CSV 或个人绝对路径；
- VM 三节点配置文件保留在本机 VMware 目录，来宾设置为 CentOS 7 64 位，未把虚拟磁盘或配置路径写入项目。

2026-08-18 的真实全量复现记录：本机 PySpark 3.4.0 读取完整数据并通过 `--expected` 核对，输出 2,101,588 行、477 个诊断分组和 10 行服务结果；`verify_service_result_contract.py --result ... --expected-scope full_scan`、`publish_top10_mysql.py --apply` 和提交后 MySQL 查询均为 `PASS`。故意写入超出 `BIGINT UNSIGNED` 的值触发 MySQL 1264 后，事务回滚且旧批次仍为 10 行；#10 实际 HTTP `GET /api/v1/diseases/top10` 返回 200，`data_version` 与 MySQL 一致。

### 7.2 已有 VM 证据与限制

`docs/03-architecture-and-env.md` 已记录 2026-08-17 的 VM 实机证据：三节点可互相 SSH，`hdfs dfsadmin -report` 显示 3 个 Live datanodes 且无缺失/损坏/低副本块，`hadoop001` 的 9000、9870、8088 已监听，Java 1.8.0_212、Hadoop 3.3.4、Hive 3.1.3、MySQL 8.0.30 已确认，MySQL 已成功进入客户端。

当前仓库尚未保存 VM 中 `spark-submit --version` 的具体输出，也尚未合并正式 API/前端命令；这些不能在 #12 中用猜测补齐，需在对应组件落位时补充实际输出并由 #13 复验。正式 TOP10 已在本机 PySpark local 模式完成，VM 只承担可选存储和 MySQL 服务结果支持。

## 8. 交接清单

- #31：使用真实服务结果工件执行 DDL 和 `publish_top10_mysql.py --apply`，记录 MySQL 结果表可用性和 `data_version`。
- #10：按 `docs/05-api.md` 使用本 Issue 发布的真实批次设置 MySQL 数据源，补齐后端启动与停止命令。
- #11：提交 `package.json`、前端环境变量和页面端口后，补齐前端启动命令。
- #13：按本手册顺序运行固定样例和全量版本，留下 HDFS、Spark、MySQL、API 和页面一致性证据。

在上述交接完成前，#12 的环境边界、已核验版本、端口归属、启动顺序、停止方式和故障降级已经固定；未实现组件保持明确的 `HANDOFF` 状态。
