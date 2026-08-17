# M0/M1 开发、运行与组长电脑复现手册

> 关联 Issue：#12
>
> 基线日期：2026-08-17
>
> 本手册只记录已经核验的环境事实和当前仓库能够执行的最小命令。#9、#10、#11、#13 尚未把全量数据任务、API、前端和端到端证据合并到 `main`，因此本手册不会把这些下游内容写成已经完成。

## 1. 运行边界

本轮围绕“疾病病例量 TOP10”建立一条唯一正式计算路径：

```text
本机受控 CSV
  → 本机 Conda 环境 csupy311
  → PySpark 3.4.0 local 模式（唯一正式清洗与 TOP10 聚合）
  → 结果工件
  → MySQL 服务结果
  → Flask API
  → Vue + ECharts
  → 独立标准库核对

本机 CSV → HDFS 原始副本 → Hive 元数据/检查（可选课堂展示）
```

虚拟机不要求安装 Spark。`hadoop001` 上 `spark-submit` 不存在已经通过诊断命令确认，属于当前边界下的预期状态；不要为了消除这个提示在 VM 中另外安装一套 Spark。VM 的 Hadoop/HDFS、Hive 和 MySQL 只在需要副本、课堂展示或服务结果库时启用。

当前仓库的可复现层次如下：

| 层次 | 当前状态 | 可复查内容 |
|---|---|---|
| M0 固定样例 | `VERIFIED` | 纯 Python 标准库读取样本、独立计数、TOP10 和契约边界 |
| M1 本机 PySpark 样例 | `VERIFIED` | PySpark 3.4.0 local 模式执行同一口径，结果与期望 JSON 一致 |
| VM 支撑环境 | `VERIFIED` | 三台 CentOS 7 64 位虚拟机、Hadoop/HDFS、Hive、MySQL；VM Spark 不属于必需项 |
| 本机 PySpark 全量任务 | `HANDOFF` | 当前只提交固定样例入口；完整 CSV 的全量运行由下游数据 Issue 留证 |
| Flask API | `HANDOFF` | 由 #10 固定表名、字段和错误语义后再维护后端依赖 |
| Vue/ECharts 页面 | `HANDOFF` | 由 #11 固定页面四态和 API 地址后再维护前端依赖 |
| 全链路一致性 | `HANDOFF` | 由 #13 按固定样例和全量版本复验 |

这里的 `HANDOFF` 是有意保留的边界，不表示可以用 Mock、假数据或未提交代码代替真实验收。

## 2. 版本与组件基线

### 2.1 组长电脑

以下结果来自组长电脑在 2026-08-17 的命令核验。绝对安装路径不写入仓库，其他成员按环境名和版本检查，不绑定组长电脑目录。

| 项目 | 实测基线 | 用途和边界 |
|---|---|---|
| 操作系统 | Windows 11 家庭中文版，`10.0.22631`，`64` 位 | VMware、WindTerm、Git 和本地 PySpark |
| PowerShell | `7.6.4`，`Core` | Windows 命令 shell；没有 Conda 初始化时改用 Anaconda Prompt |
| Git | `2.45.1.windows.1` | 获取干净 `main`、查看提交和协作 |
| 系统 Python | `3.11.4` | M0 独立核对脚本；只用标准库 |
| Conda 环境 | `csupy311` | 课程中的本机 Spark 开发环境 |
| PySpark | `3.4.0` | M1 唯一正式清洗和 TOP10 聚合运行时 |
| Node.js | `v22.13.1` | 当前主机前置条件；`main` 尚无前端代码 |
| npm | `10.9.2` | 当前主机前置条件；依赖清单由 #11 维护 |
| Java | `1.8.0_202` | 主机上可见；本机 PySpark 样例已使用该主机环境通过 |
| Windows 全局 `hdfs`/`hive`/`mysql` | 未加入 PATH | 需要 VM 支撑时通过 WindTerm/VM 终端执行 |

组长已确认组员使用相同的 Windows 操作系统版本和架构，并按老师课堂笔记下载课程软件。这个结论是组长提供的组内基线确认，不替代每台电脑的命令输出；逐台复核时仍执行下面的版本命令。

| 成员 | 已登记的操作系统/架构 | 本机数据环境 | 当前登记状态 |
|---|---|---|---|
| 王敬博（组长） | Windows 11，64 位 | `csupy311` / PySpark `3.4.0` 已实测 | `VERIFIED` |
| 叶艺鑫 | 与组长相同（组长确认） | 按课程笔记安装；待本人执行版本核对 | `SELF-CHECK` |
| 魏世轩 | 与组长相同（组长确认） | 按课程笔记安装；待本人执行版本核对 | `SELF-CHECK` |
| 胡钰炜 | 与组长相同（组长确认） | 按课程笔记安装；待本人执行版本核对 | `SELF-CHECK` |
| 李佳明 | 与组长相同（组长确认） | 按课程笔记安装；待本人执行版本核对 | `SELF-CHECK` |

组员逐台核对命令：

```powershell
conda activate csupy311
python --version
python -c "import pyspark; print(pyspark.__version__)"
python -m pip show pyspark py4j
```

如果 PowerShell 中没有 `conda` 命令，打开 Anaconda Prompt 后执行同样命令；这不是 Spark 需要安装到 VM 的理由。

组长电脑的通用前置检查：

```powershell
git --version
python --version
node --version
npm --version
java -version

# 这些命令在 Windows 全局 PATH 找不到是预期边界。
Get-Command hdfs,hive,mysql -ErrorAction SilentlyContinue
```

### 2.2 VMware 三节点

VMware 配置为 CentOS 7 64 位来宾，三台机器的地址和职责如下。服务版本和端口以 VM 内命令输出为准。

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
| Spark | 不安装、不要求 | `hadoop001` 的 `spark-submit` 未找到，符合本机 PySpark 正式计算边界 |
| Python/Node/Flask/Vue/ECharts | 不作为 VM 基线 | 本机 PySpark 在 Windows 运行；后端和前端依赖分别由 #10/#11 提供 |

VM 中用于确认“是否误以为安装过 Spark”的只读诊断命令：

```bash
printf '%s\n' '--- identity ---'
hostname
uname -m

printf '%s\n' '--- path ---'
printf '%s\n' "$PATH"
if [ -n "$SPARK_HOME" ]; then printf '%s\n' "SPARK_HOME=$SPARK_HOME"; else printf '%s\n' 'SPARK_HOME=<unset>'; fi

printf '%s\n' '--- commands ---'
command -v spark-submit || true
type -a spark-submit 2>/dev/null || true

printf '%s\n' '--- candidate files ---'
find /opt/module /opt -maxdepth 4 -type f -name spark-submit -print 2>/dev/null

printf '%s\n' '--- candidate directories ---'
find /opt/module /opt -maxdepth 2 -type d -iname 'spark*' -print 2>/dev/null
```

预期是 `SPARK_HOME=<unset>`、`spark-submit` 找不到且候选路径无输出；这只说明 VM 没有 Spark，不影响本机正式开发。不要执行 VM Spark 安装命令，也不要把 VM 的缺失写成项目故障。

### 2.3 端口和地址

| 服务 | 地址/端口 | 当前用途 | 状态判断 |
|---|---|---|---|
| HDFS NameNode RPC | `hadoop001:9000` | 可选原始副本上传和课堂展示 | 集群配置和实机记录已确认 |
| NameNode Web | `hadoop001:9870` | 查看可选 HDFS 副本状态 | 实机记录已确认监听 |
| YARN ResourceManager Web | `hadoop001:8088` | 查看可选集群状态 | 实机记录已确认监听 |
| HiveServer2 | `hadoop001:10000` | 可选 Hive 表/查询检查 | 不承担 TOP10 正式计算 |
| MySQL TCP | `hadoop001:3306` | 后续业务服务结果库 | 后端落位后复核 |
| MySQL Unix socket | `/opt/module/mysql/mysql.sock` | `hadoop001` 本地客户端连接 | 实际配置已确认 |
| Flask | 未固定 | #10 固定 API 合同后确定 | 当前 `main` 无后端 |
| Vue/Vite | 未固定 | #11 固定页面启动方式后确定 | 当前 `main` 无前端 |

当前架构没有把 Spark Standalone Master 或 VM `spark-submit` 端口加入必要链路。

## 3. 依赖与配置归属

### 3.1 本机开发依赖

M0 独立核对只使用 Python 标准库，不需要安装第三方包。M1 正式数据计算使用课程笔记中的本机 Conda 环境和 PySpark `3.4.0`；这是当前唯一必须的 Spark 运行时，安装在 Windows 本机，不安装到 VM。

新电脑首次按老师笔记配置本机环境时，在 Anaconda Prompt 执行：

```powershell
conda activate base
conda create -n csupy311 python==3.11
conda activate csupy311
python -m pip install pyspark==3.4.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m pip install py4j -i https://pypi.tuna.tsinghua.edu.cn/simple
python -c "import pyspark; print(pyspark.__version__)"
```

组长环境已存在并验证 `PySpark 3.4.0`，不需要重复安装。提交的运行脚本不要求设置个人 `SPARK_HOME` 绝对路径，直接用激活后的 `python` 启动即可。

### 3.2 下游依赖的唯一归属

| 内容 | 归属文件/环境 | 当前状态 |
|---|---|---|
| PySpark 正式计算 | 本机 Conda 环境 `csupy311` | `3.4.0` 已验证；运行入口为 `data/src/run_sparcs_top10_pyspark.py` |
| Flask 和 MySQL 查询依赖 | `backend/requirements.txt` | 由 #10 在后端代码落位时创建或更新 |
| 后端环境变量示例 | `backend/.env.example` | 由 #9/#10 固定表和连接字段后创建；真实 `backend/.env` 只在本地存在 |
| Vue/ECharts 构建依赖 | `frontend/package.json` | 由 #11 在页面原型确认后创建或更新 |
| 前端地址示例 | `frontend/.env.example` | 由 #10/#11 共同固定 API 地址后创建 |
| HDFS 原始副本路径 | 可选上传命令参数 | 不写入后端 `.env`，不改变本机正式输入 |
| Hive 配置 | Hive 自己的配置目录 | 只做可选元数据和检查，不作为 API 业务数据库 |
| MySQL 业务连接 | 后端 `.env` | 不提交密码、Token、API Key 或真实 `.env` |

这项归属决定后续顺序：先由 #9 固定服务结果表和 `data_version`，再由 #10 固定后端连接变量和 API，最后由 #11 固定前端 API 地址。#12 不复制一份会与下游漂移的空配置。

## 4. 从干净 `main` 运行固定样例

这是当前 `main` 唯一完整、无需完整原始 CSV 和 VM 的复现路径。建议在不含中文、空格且路径较短的本地目录执行；仓库本身不依赖特定绝对路径。

```powershell
git clone git@github.com:Martin7816/yishuyunce-medical-analytics.git yishuyunce-medical-analytics
Set-Location yishuyunce-medical-analytics
git switch main
git pull --ff-only

conda activate csupy311
python -c "import pyspark; print(pyspark.__version__)"
python data/src/run_sparcs_top10_pyspark.py --input data/fixtures/sparcs_mvp_sample.csv --expected data/fixtures/sparcs_mvp_expected_top10.json
python data/src/verify_sparcs_mvp.py
```

本机 PySpark 命令成功时必须得到退出码 0，并包含：

```text
"status": "PASS"
"engine": "pyspark-local"
"pyspark_version": "3.4.0"
"rows": 16
"diagnosis_nonempty_rows": 15
"diagnosis_nonempty_distinct": 12
```

独立标准库核对还必须包含 `malformed_rows=0`、`out_of_scope_rows=0`，并与 `data/fixtures/sparcs_mvp_expected_top10.json` 中的 TOP10 一致。Windows 本机运行可能出现 `winutils.exe` 或 native Hadoop library 警告；只要固定样例退出码为 0 且结果一致，这些警告不构成失败，也不要求把 Hadoop 安装到本机。

有本地完整 SPARCS CSV 时才执行全量复核；路径只作为命令行参数传入，不写入仓库：

```powershell
python data/src/run_sparcs_top10_pyspark.py --input "<本地完整 SPARCS CSV 路径>"
python data/src/verify_sparcs_mvp.py --full-source "<本地完整 SPARCS CSV 路径>"
```

全量复核要求与 `docs/01-data-and-feasibility.md` 中同一版本文件一致：2,101,588 条记录、0 条解析异常、2,099,954 条非空诊断记录、477 个非空诊断值，TOP10 与记录的基线一致。没有完整文件时不要用固定样例结果冒充全量结果。

## 5. 可选 VM 启动、健康检查与停止

只运行本机 PySpark、开发 API 或开发前端时，可以不启动 VM。需要 HDFS 副本、Hive 展示或 VM 中的 MySQL 服务结果时，才执行本节。

### 5.1 启动前检查

1. 在 VMware 中启动三台 VM，确认三台主机都能进入 CentOS；在 `hadoop001` 执行 `ssh hadoop002 hostname` 和 `ssh hadoop003 hostname`。
2. 从组长电脑只检查 SSH 可达性，不要求 Windows 直接执行 Linux 大数据命令：

   ```powershell
   Test-NetConnection 192.168.219.128 -Port 22
   ```

3. 所有 Linux 命令在 `hadoop001` 终端执行，需要密码的命令都使用交互式输入；密码不写入脚本、文档或 Issue。

### 5.2 按需启动

#### MySQL

```bash
sudo systemctl start mysql8
sudo systemctl --no-pager status mysql8
/opt/module/mysql/bin/mysql --socket=/opt/module/mysql/mysql.sock -uroot -p -e 'SELECT VERSION();'
ss -lntp | grep ':3306'
```

若 MySQL 因残留 socket 锁文件启动失败：

```bash
ps -ef | grep '[m]ysqld'
# 只有确认没有 mysqld 进程后，才清理 socket/lock 临时文件；不要操作 mysql/data。
sudo rm -f /opt/module/mysql/mysql.sock /opt/module/mysql/mysql.sock.lock
sudo systemctl start mysql8
```

#### Hadoop/YARN（可选）

```bash
cd /opt/module/hadoop
sbin/start-all.sh
jps
hdfs dfsadmin -report
```

健康检查要求：`Live datanodes (3)`，三台节点 `Decommission Status` 为 `Normal`，`Missing`、`Corrupt` 和 `Under replicated blocks` 均为 0。

#### HiveServer2（可选）

```bash
cd /opt/module/hive
bin/schematool -dbType mysql -info

# 只有上条命令明确提示 schema 尚未初始化时，才手动执行下面这条。
# bin/schematool -dbType mysql -initSchema

hive --service hiveserver2 > "$HIVE_HOME/hiveserver2.log" 2>&1 &
ss -lntp | grep ':10000'
```

HiveServer2 只提供表和查询检查，不承担正式 TOP10 计算。本机 PySpark 任务不通过 `spark-submit` 读取 HDFS，也不依赖 HiveServer2。

### 5.3 停止顺序

按“前端 → Flask → HiveServer2 → Hadoop/YARN → MySQL → VMware”逆序停止。当前已有组件可执行：

```bash
cd /opt/module/hadoop
sbin/stop-all.sh
sudo systemctl stop mysql8
```

本机 PySpark 是一次性任务，脚本在退出前调用 `spark.stop()`，不需要另行停止 Spark 服务。HiveServer2 应根据启动时记录的 PID 或服务管理方式停止，停止前确认不要误杀其他 Java 进程。最后从 VMware 界面正常关机，不直接删除或移动虚拟磁盘。

## 6. 常见问题与降级

| 现象 | 判断和处理 |
|---|---|
| `ModuleNotFoundError: pyspark` | 先执行 `conda activate csupy311` 和版本检查；确认版本不是 `3.4.0` 后，按本手册的本机安装命令处理 |
| 本机未激活环境时找不到 `spark-submit` | 不用它作为正式入口；激活 `csupy311` 后执行仓库中的 `python data/src/run_sparcs_top10_pyspark.py ...` |
| VM 找不到 `spark-submit` | 当前边界下是预期状态，不安装、不写成故障；正式 TOP10 不走 VM Spark |
| 本机运行出现 `winutils.exe` 或 native Hadoop library 警告 | 先看进程退出码和 JSON 结果；固定样例退出码为 0 且结果一致时可接受，不提交个人 `winutils.exe` 或绝对路径 |
| HDFS 报告节点不足或块异常 | 只影响可选副本/课堂展示；先恢复三节点和 HDFS 健康状态，不能声称 HDFS 已验收 |
| HiveServer2 不可用 | 跳过 Hive 展示；不改用 Hive/Pandas 另算 TOP10，继续使用本机 PySpark 正式路径 |
| 完整原始 CSV 不存在 | 运行固定样例或独立核对；不能声称已完成全量结果 |
| MySQL 启动失败 | 先看 `systemctl status mysql8` 和错误日志；只有确认无 `mysqld` 时才清理 socket/lock，不碰数据目录 |
| Flask/MySQL 依赖未安装 | 当前 `main` 没有后端，不能用主机偶然安装的 Flask 版本当项目依赖；等待 #10 的清单 |
| API 或前端地址错误 | 由 #10/#11 按约定显示错误态；Mock 只验证界面结构，不替代真实验收 |

## 7. 组长电脑复现记录

### 7.1 本次可直接复现的记录

在仓库根目录、激活 `csupy311` 后执行：

```powershell
python data/src/run_sparcs_top10_pyspark.py --input data/fixtures/sparcs_mvp_sample.csv --expected data/fixtures/sparcs_mvp_expected_top10.json
python data/src/verify_sparcs_mvp.py
```

实际结果：本机 PySpark 进程退出码为 0，`status=PASS`、`engine=pyspark-local`、`pyspark_version=3.4.0`；固定样例 `rows=16`、非空诊断记录 `15`、非空诊断值 `12`，TOP10 与期望 JSON 一致。独立标准库脚本也退出码为 0，`malformed_rows=0`、`out_of_scope_rows=0`。

本次同时确认：

- 组长电脑的 `csupy311` 可导入 PySpark `3.4.0`；
- Windows 全局环境不提供 `hdfs`、`hive`、`mysql`，正式计算不依赖这些命令；
- VM 诊断显示 `hadoop001` 为 `x86_64`、`SPARK_HOME` 未设置、`spark-submit` 和候选 Spark 目录不存在；
- 仓库没有真实 `.env`、完整原始 CSV、密码、Token 或个人绝对路径。

### 7.2 已有 VM 证据与限制

`docs/03-architecture-and-env.md` 已记录 VM 实机证据：三节点可互相 SSH，`hdfs dfsadmin -report` 显示 3 个 Live datanodes 且无缺失/损坏/低副本块，`hadoop001` 的 9000、9870、8088 已监听，Java 1.8.0_212、Hadoop 3.3.4、Hive 3.1.3、MySQL 8.0.30 已确认，MySQL 已成功进入客户端。

VM 没有 Spark 版本字符串，因为 Spark 不属于本项目必需组件；本机 PySpark `3.4.0` 的版本证据已通过 Conda 环境导入和固定样例运行取得。完整 CSV、MySQL 业务结果实际装载、Flask API 和 Vue 页面仍需对应下游 Issue 和 #13 复验。

## 8. 交接清单

- #9：提交业务服务结果表、`data_version`、事务刷新和 MySQL 连接字段；数据结果由本机 PySpark 生成后再装载。
- #10：提交 Flask 依赖、API 端口、健康检查和失败响应，补齐后端启动与停止命令。
- #11：提交 `package.json`、前端环境变量和页面端口，补齐前端启动命令。
- #13：按本文先运行本机 PySpark 固定样例和全量版本，再留下可选 HDFS 副本、MySQL/API/页面一致性证据。

在上述交接完成前，#12 的本机开发环境、已核验版本、VM 可选支撑边界、启动顺序、停止方式和故障降级已经固定；未实现组件保持明确的 `HANDOFF` 状态。
