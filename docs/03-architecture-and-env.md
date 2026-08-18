# M0/M1 最小技术链路与存储边界

> 决策状态：`DECIDED`（2026-08-17；按 #12 实测结果修订）
> 适用范围：第一轮“疾病病例量 TOP10”真实数据闭环
> 关联 Issue：#8、#9、#10、#12、#13

本文冻结 M0/M1 的组件职责、数据边界、启动顺序、失败处理和降级方式。字段名、表名和 API 字段由 #9、#10 继续固定；实际代码尚未在本 Issue 中虚构为完成。

## 1. 决策摘要

M1 采用以下单向链路：

```text
本地 CSV（正式输入）
    → 本机 PySpark 3.4.0（唯一正式清洗与聚合）
    → 本机结果工件
    → MySQL 服务结果表
    → Flask 只读 API
    → Vue + ECharts

本地 CSV ─→ HDFS 原始副本 / Hive 检查（可选课堂展示，不改变正式计算）
```

本次取舍如下：

- 本机 CSV 是 M1 的正式输入事实；完整原始文件保留在本机受控目录，固定样例进入 Git。HDFS 只在需要课堂展示或审计副本时保存一份原始副本，不作为本轮正式计算的唯一来源。
- 本机 PySpark 3.4.0 是唯一正式计算 TOP10 的组件，负责按 #7 的口径清洗、计数、稳定排序并生成结果工件。
- Hive 是可选支撑层，负责 HDFS 副本的表/元数据登记和课堂检查，不生成正式 TOP10，也不写入服务结果表。
- VM 不要求安装 Spark；`hadoop001` 上 `spark-submit` 不存在是当前已确认且符合新边界的状态，不再作为环境故障。
- Pandas 不进入 M1 正式计算；固定样本使用 Python 标准库独立核对，避免用同一实现自证。
- MySQL 只保存后端需要的小型服务结果、数据版本和刷新追溯信息。Hive 使用的 MySQL `hive` 元数据库属于基础设施，不是业务明细库，也不向 API 暴露。
- Flask 只查询已校验的 MySQL 服务结果；Vue/ECharts 只消费 API，不直连数据库、不计算病例量。

这样保留本机已经按老师课程配置好的 PySpark，同时不凭空增加老师没有要求的 VM Spark 安装和维护工作，也只保留一处正式指标计算逻辑。

## 2. 数据流与唯一事实来源

```text
本地原始 CSV（正式输入）
          │
          ├── 本机 PySpark 任务（唯一正式清洗、分组、排序）
          │             │
          │             ├── 本机 TOP10 结果工件
          │             └── MySQL 服务结果表（API 的唯一读取来源）
          │                       │
          │                       └── Flask → Vue/ECharts
          │
          └── 可选上传 HDFS raw（副本/课堂检查，不产正式指标）
```

“唯一”分三个层次定义，避免把存储副本误认为重复口径：

- 原始事实唯一来源：本机受控 CSV、输入文件指纹和 `data_version`；HDFS 只保存可选副本。
- 指标生成唯一来源：本机 PySpark 任务；Hive、Pandas、Flask 和前端不得复制 TOP10 逻辑。
- API 服务唯一来源：MySQL 当前完整服务结果批次；API 不回读 HDFS，也不现场计算。

必须遵守：

- 完整 CSV、个人绝对路径、密码和 Token 不提交 Git。
- 每条有效住院出院记录计数一次；当前“病例量”不是唯一患者数。
- 结果工件必须携带输入指纹、规则版本、生成时间和结果完整性信息，但不携带个人绝对路径。
- MySQL 装载采用“先生成、后校验、事务替换”；失败时不得留下半批 TOP10。
- 前端 Mock 只服务并行开发，不能作为真实链路的替代证据。

## 3. 组件职责、输入输出与状态

| 组件 | M1 状态 | 职责 | 输入 → 输出 | 当前证据/验收方式 |
|---|---|---|---|---|
| 本地文件 | M1 正式输入必须 | 保存受控原始 CSV、固定样本和结果输入 | CSV → PySpark 任务/核对摘要 | 完整数据规模记录在 `docs/01-data-and-feasibility.md`；完整文件不进 Git |
| 本机 PySpark | M1 正式计算必须 | 唯一执行 #7 清洗、分组、计数、排序 | 本地 CSV → TOP10 结果工件 | 本机 PySpark 3.4.0 已通过固定样例；脚本见 `data/src/run_sparcs_top10_pyspark.py` |
| HDFS | 可选支撑层 | 保存原始副本或课堂展示材料，不是正式输入唯一来源 | 本地 CSV → HDFS raw 副本 | `hdfs dfsadmin -report` 已显示 3 个 Live datanodes，均 `Normal`，无缺失/损坏块 |
| Python 标准库核对 | M0 必须，非正式计算 | 独立核对字段、缺失和固定样本 TOP10 | 固定样本 → JSON 核对摘要 | `python data/src/verify_sparcs_mvp.py` 已通过固定样本，`status=PASS` |
| Hive | M1 支撑层，不做指标计算 | 登记 HDFS 外部表、检查原始层和课堂 SQL 访问 | HDFS → 元数据/检查查询 | VM 中 Hive 3.1.3 已确认；MySQL 修复后需按教师命令完成 schema/HiveServer2 验收 |
| Spark | M1 正式计算必须 | 唯一执行 #7 清洗、分组、计数、排序 | 本机 CSV → TOP10 结果工件 | 本机 PySpark 3.4.0 已完成真实全量运行；脚本见 `data/src/run_sparcs_top10_pyspark.py` |
| MySQL | M1 服务层必须 | 保存小型服务结果、版本和刷新追溯 | TOP10 工件 → `disease_case_count_top10_result` | MySQL 8.0.30 已在 hadoop001 启动并成功进入客户端；表 DDL 和刷新契约见 [`docs/02-metrics-and-data-contract.md`](02-metrics-and-data-contract.md) |
| Flask | M1 必须 | 提供受控只读 API 和统一错误语义 | MySQL → JSON | 路径、响应和失败码由 #10 固定；不在 Route 重算指标 |
| Vue + ECharts | M1 展示必须 | 展示排名、名称、病例量和四种页面状态 | Flask → 图表页面 | 页面和四态由后续 Issue 验收；不得写死正式结果 |
| Pandas | M1 不需要 | 可用于临时探索，不产正式服务结果 | 小样本 → 临时分析 | 缺少 Pandas 不阻塞 M1；正式口径仍只认本机 PySpark |
| AI、机器学习、复杂权限、微服务 | 暂不实现 | 不属于首轮 TOP10 闭环 | 无 M1 输入输出 | 有明确验收价值后另建 Issue |

## 4. 存储边界

### 4.1 HDFS 可选副本层

逻辑目录约定如下，实际集群路径在数据任务配置中统一维护：

```text
/project/yishuyunce/raw/sparcs/2021/       # 本地正式输入的可选只读副本
/project/yishuyunce/results/top10/        # 本机 PySpark 结果的可选审计副本
```

上传 HDFS 的副本可以保留文件指纹和 `data_version`，但不能替换本机正式输入的版本记录。HDFS 不保存用户密码，不把 MySQL 当原始数据仓库。

### 4.2 Hive 元数据边界

Hive 的元数据库可以使用 MySQL 中独立的 `hive` 逻辑库；该库只保存 Hive 元数据，不承载业务 TOP10，也不作为 API 数据源。Hive 查询可以检查 HDFS 副本，但不能另算一套指标。

### 4.3 MySQL 服务结果边界

业务结果库只保存 `disease_case_count_top10_result` 当前已经校验并发布的一个完整批次，不保存原始住院明细和历史批次。正式表名、字段类型、唯一性、刷新事务和服务读取查询统一见 [`docs/02-metrics-and-data-contract.md`](02-metrics-and-data-contract.md) 及 [`data/sql/001-mvp-disease-top10-service.sql`](../data/sql/001-mvp-disease-top10-service.sql)；本文只说明它在整体链路中的存储位置，不另写第二份字段契约。

## 5. 启动顺序与配置归属

### 5.1 运行环境边界

Windows 主机通过 VMware 和 WindTerm 连接 CentOS 集群；大数据命令不要求出现在 Windows PATH 中。当前集群地址为：

| 主机 | 地址 | 角色/实测状态 |
|---|---|---|
| hadoop001 | `192.168.219.128` | NameNode、DataNode、ResourceManager、NodeManager、SecondaryNameNode；MySQL |
| hadoop002 | `192.168.219.129` | DataNode、NodeManager |
| hadoop003 | `192.168.219.130` | DataNode、NodeManager |

### 5.2 本机正式计算与可选 VM 支撑顺序

1. 在 Anaconda Prompt 或已初始化 Conda 的 PowerShell 中激活本机数据环境，并先运行固定样例：

   ```powershell
   conda activate csupy311
   python data/src/run_sparcs_top10_pyspark.py `
     --input data/fixtures/sparcs_mvp_sample.csv `
     --expected data/fixtures/sparcs_mvp_expected_top10.json
   python data/src/verify_sparcs_mvp.py
   ```

   正式计算在本机 PySpark local 模式完成，不要求 Windows PATH 中出现 `hdfs`、`hive` 或 VM 的 `spark-submit`。

2. 如果需要把原始副本上传 HDFS 或展示 Hive，再启动 VMware 三节点；只做本机 TOP10、API 和页面开发时可以跳过 VM。

3. 在 VMware 中启动三台 VM，确认 hadoop001 可以 SSH 到 hadoop002、hadoop003；需要 MySQL 服务结果时，在 hadoop001 启动 MySQL：

   ```bash
   sudo systemctl start mysql8
   /opt/module/mysql/bin/mysql -uroot -p
   ```

   当前 MySQL 配置使用 `/opt/module/mysql/mysql.sock`。`mysqlx=0` 关闭不参与 Hive/JDBC 链路的 X Plugin；若异常退出后遗留 Socket 锁，先确认没有 `mysqld` 进程，再只清理 Socket/lock 临时文件，不碰 `data` 目录。

4. 需要 HDFS 副本或课堂展示时，在 hadoop001 启动 Hadoop/YARN：

   ```bash
   cd /opt/module/hadoop
   sbin/start-all.sh
   jps
   hdfs dfsadmin -report
   ```

   验收要求：3 个 Live datanodes、Decommission Status 为 `Normal`、Missing/Corrupt/Under replicated blocks 均为 0。

5. 需要 Hive 检查时，首次初始化 Hive 元数据库并启动 HiveServer2：

   ```bash
   cd /opt/module/hive
   bin/schematool -dbType mysql -initSchema
   hive --service hiveserver2 > "$HIVE_HOME/hiveserver2.log" 2>&1 &
   ss -lntp | grep ':10000'
   ```

   `schematool` 只在 schema 尚未初始化时执行；HiveServer2 只提供表/查询访问，不承担正式 TOP10 计算。

6. 本机 PySpark 任务生成并校验结果工件后，再按 #9 的事务模板装载 MySQL；随后依次启动 Flask 和 Vue，按 #10/#11 验收 API 与页面四态。

配置归属：正式输入和结果路径由本机数据任务参数控制；HDFS 副本路径由可选上传命令控制；Hive 配置归 Hive；MySQL 业务连接由 `backend/.env` 管理；真实 `.env` 不提交 Git；API 和前端地址由 #10/#11 固定。

## 6. 当前环境证据

截至 2026-08-17，已经获得以下实机证据：

- hadoop001/002/003 可以互相通信并 SSH 登录。
- `hdfs dfsadmin -report` 显示 `Live datanodes (3)`，总配置容量约 105.30 GB，三台节点均 `Normal`，缺失块、损坏副本和低副本块均为 0。
- hadoop001 的 NameNode、DataNode、SecondaryNameNode、ResourceManager、NodeManager 已运行；9000、9870、8088 端口已监听。
- 组长电脑的 Conda 环境 `csupy311` 可导入 PySpark `3.4.0`；固定样例经本机 PySpark local 模式运行并通过独立标准库脚本核对。
- VM 中 Java 1.8.0_212、Hadoop 3.3.4、Hive 3.1.3、MySQL 8.0.30 已确认；VM 未安装 Spark，`spark-submit` 未找到符合本次修订后的边界。
- MySQL 因残留 Socket 锁文件曾启动失败；确认 PID 9024 实际为 `rsyslogd` 后清理临时锁文件，已能进入 MySQL 8.0.30 客户端。该问题不涉及数据库数据目录。
- 本机 PySpark TOP10 固定样例和真实全量任务均已落位并通过独立基线核对；#31 已完成 MySQL 业务结果实际装载和失败回滚复验，#10 已完成 MySQL 真数据 API 实测；Hive schema/HiveServer2 完整复验和 Vue 页面仍属于下游 Issue。

## 7. 故障与降级

| 故障 | M1 处理 | 允许的降级 |
|---|---|---|
| Windows 主机找不到 `hdfs`/`hive`/`mysql` | 预期边界；正式 TOP10 使用本机 PySpark，HDFS/Hive/MySQL 需要时通过 WindTerm 在 VM 执行 | 不把 Windows PATH 结果写成集群不可用 |
| VM 未启动或 SSH 不通 | 阻塞 MySQL/HDFS 实机链路，先恢复 VM/网络 | 本机 PySpark 仍可生成真实全量工件，但不能声称 MySQL/API 已完成 |
| HDFS 不可用 | 不影响本机正式计算；需要副本或课堂展示时标记支撑层阻塞 | 继续使用本机受控 CSV，但不能声称 HDFS 副本已验收 |
| Hive/HS2 不可用 | 不影响本机 PySpark 正式计算 | 跳过 Hive 展示，不用 Hive 另算 TOP10 |
| 本机 PySpark 未安装或任务失败 | 不刷新 MySQL 服务结果；先激活 `csupy311` 并检查 `pyspark.__version__` | 固定样例可退回标准库独立核对，但不冒充正式计算 |
| VM 找不到 `spark-submit` | 当前边界下是预期状态，不安装、不把它写成故障 | 不用 VM Spark 作为验收前置 |
| MySQL 不可用 | Flask 返回明确依赖失败，不现场计算 | 使用 Mock 做接口开发，不替代真实验收 |
| 结果为空但请求合法 | 由 #10 明确 API 的空结果语义；M1 不发布零有效诊断的空批次 | 不填充假数据 |
| Flask/前端地址错误 | API 或页面显示错误态，修正配置后重试 | Mock 只验证界面结构 |

## 8. 与后续 Issue 的交接

- #12：具体版本表、依赖归属、组长电脑固定样例复现和 VM 启停/故障处理见 [M0/M1 开发、运行与组长电脑复现手册](04-development-and-runbook.md)。
- #9：已固定 `disease_case_count_top10_result` 的字段、`data_version`、事务刷新和校验；不创建原始明细表。实际 Spark 结果装载由下游数据任务完成。
- #10：只查询 MySQL 服务结果，固定正常、空数据、非法请求和数据库失败响应。
- #11：只消费 API，完成加载、正常、空数据和错误四态。
- #13：按本文启动顺序补充 HDFS 原始数据、Spark 全量结果、MySQL/API/页面的一致性证据。

## 9. 当前完成边界

本文已冻结组件职责、唯一计算位置、HDFS/Hive/MySQL 存储边界、启动顺序和故障降级，并记录了 VMware 三节点集群与 MySQL 的实际证据。本机 Spark 正式任务、MySQL 业务结果实际装载和 Flask 真数据 API 已完成实测；HiveServer2 完整复验和 Vue 页面继续由对应 Issue 实现和验收。
