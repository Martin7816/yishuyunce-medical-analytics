# M0/M1 最小技术链路与存储边界

> 决策状态：`DECIDED`（2026-08-17）
> 适用范围：第一轮“疾病病例量 TOP10”真实数据闭环
> 关联 Issue：#8、#9、#10、#12、#13

本文冻结 M0/M1 的组件职责、数据边界、启动顺序、失败处理和降级方式。字段名、表名和 API 字段由 #9、#10 继续固定；实际代码尚未在本 Issue 中虚构为完成。

## 1. 决策摘要

M1 采用以下单向链路：

```text
本地 CSV 暂存/上传
    → HDFS 原始层
    → Hive 元数据与检查层（不计算正式 TOP10）
    → Spark 唯一正式清洗与聚合
    → HDFS 结果工件
    → MySQL 服务结果表
    → Flask 只读 API
    → Vue + ECharts
```

本次取舍如下：

- HDFS 是 M1 的原始数据落地区。Windows 和本地 VM 文件只负责暂存、上传和复核；上传后的原始事实以 HDFS 对象及其数据版本为准。
- Spark 是唯一正式计算 TOP10 的组件，负责按 #7 的口径清洗、计数、稳定排序并生成结果工件。
- Hive 负责 HDFS 数据的表/元数据登记和课堂检查，可通过 HiveServer2 查询原始层或结果工件，但不得再次生成一份正式 TOP10，也不得写入服务结果表。
- Pandas 不进入 M1 正式计算；固定样本使用 Python 标准库独立核对，避免用同一实现自证。
- MySQL 只保存后端需要的小型服务结果、数据版本和刷新追溯信息。Hive 使用的 MySQL `hive` 元数据库属于基础设施，不是业务明细库，也不向 API 暴露。
- Flask 只查询已校验的 MySQL 服务结果；Vue/ECharts 只消费 API，不直连数据库、不计算病例量。

这样既使用了已经在 VMware/CentOS 中验证的 Hadoop、Hive、Spark、MySQL 环境，也只保留一处正式指标计算逻辑。

## 2. 数据流与唯一事实来源

```text
Windows/VM 本地原始 CSV
          │ 上传与校验
          ▼
HDFS 原始层（raw，原始事实）
          ├── Hive 外部表/元数据（检查与查询，不产正式指标）
          │
          └── Spark 任务（唯一正式清洗、分组、排序）
                    │
                    ├── HDFS TOP10 结果工件（审计交接）
                    │
                    └── MySQL 服务结果表（API 的唯一读取来源）
                              │
                              └── Flask → Vue/ECharts
```

“唯一”分三个层次定义，避免把存储副本误认为重复口径：

- 原始事实唯一来源：HDFS 原始对象、输入文件指纹和 `data_version`。
- 指标生成唯一来源：Spark 任务；Hive、Pandas、Flask 和前端不得复制 TOP10 逻辑。
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
| 本地文件 | 必须作为暂存 | 保存老师原始 CSV 的上传副本和固定样本 | CSV → 上传包/校验摘要 | 完整数据规模记录在 `docs/01-data-and-feasibility.md`；完整文件不进 Git |
| HDFS | M1 原始层必须 | 保存原始数据和可追溯结果工件 | 本地 CSV → HDFS raw/result | `hdfs dfsadmin -report` 已显示 3 个 Live datanodes，均 `Normal`，无缺失/损坏块 |
| Python 标准库核对 | M0 必须，非正式计算 | 独立核对字段、缺失和固定样本 TOP10 | 固定样本 → JSON 核对摘要 | `python data/src/verify_sparcs_mvp.py` 已通过固定样本，`status=PASS` |
| Hive | M1 支撑层，不做指标计算 | 登记 HDFS 外部表、检查原始层和课堂 SQL 访问 | HDFS → 元数据/检查查询 | VM 中 Hive 3.1.3 已确认；MySQL 修复后需按教师命令完成 schema/HiveServer2 验收 |
| Spark | M1 正式计算必须 | 唯一执行 #7 清洗、分组、计数、排序 | HDFS raw → TOP10 结果工件 | VM 中 `spark-submit` 已确认；正式任务和全量运行证据由后续开发补齐 |
| MySQL | M1 服务层必须 | 保存小型服务结果、版本和刷新追溯 | TOP10 工件 → 服务结果表 | MySQL 8.0.30 已在 hadoop001 启动并成功进入客户端；表契约由 #9 固定 |
| Flask | M1 必须 | 提供受控只读 API 和统一错误语义 | MySQL → JSON | 路径、响应和失败码由 #10 固定；不在 Route 重算指标 |
| Vue + ECharts | M1 展示必须 | 展示排名、名称、病例量和四种页面状态 | Flask → 图表页面 | 页面和四态由后续 Issue 验收；不得写死正式结果 |
| Pandas | M1 不需要 | 可用于临时探索，不产正式服务结果 | 小样本 → 临时分析 | 缺少 Pandas 不阻塞 M1；正式口径仍只认 Spark |
| AI、机器学习、复杂权限、微服务 | 暂不实现 | 不属于首轮 TOP10 闭环 | 无 M1 输入输出 | 有明确验收价值后另建 Issue |

## 4. 存储边界

### 4.1 HDFS 原始层与结果层

逻辑目录约定如下，实际集群路径在数据任务配置中统一维护：

```text
/project/yishuyunce/raw/sparcs/2021/       # 原始 CSV，只读事实层
/project/yishuyunce/results/top10/        # Spark 结果工件
```

原始 CSV 上传 HDFS 后，以文件指纹和 `data_version` 追踪输入。HDFS 不保存用户密码，不把 MySQL 当原始数据仓库。

### 4.2 Hive 元数据边界

Hive 的元数据库可以使用 MySQL 中独立的 `hive` 逻辑库；该库只保存 Hive 元数据，不承载业务 TOP10，也不作为 API 数据源。Hive 查询可以检查 HDFS 原始层或结果工件，但不能绕过 Spark 另算一套指标。

### 4.3 MySQL 服务结果边界

业务结果库只保存当前可服务的小结果批次。逻辑上至少需要：

- `data_version`：输入指纹与指标规则版本；
- `rank`：1—10 的稳定排名；
- `diagnosis_name`：清洗后的主诊断描述；
- `case_count`：病例量整数；
- `generated_at`：结果生成时间。

正式表名、字段类型、唯一性、刷新事务和 API 映射由 #9 固定；本文不提前创造第二份契约。

## 5. 启动顺序与配置归属

### 5.1 运行环境边界

Windows 主机通过 VMware 和 WindTerm 连接 CentOS 集群；大数据命令不要求出现在 Windows PATH 中。当前集群地址为：

| 主机 | 地址 | 角色/实测状态 |
|---|---|---|
| hadoop001 | `192.168.219.128` | NameNode、DataNode、ResourceManager、NodeManager、SecondaryNameNode；MySQL |
| hadoop002 | `192.168.219.129` | DataNode、NodeManager |
| hadoop003 | `192.168.219.130` | DataNode、NodeManager |

### 5.2 教师方法的启动顺序

1. 在 VMware 中启动三台 VM，确认 hadoop001 可以 SSH 到 hadoop002、hadoop003。
2. 在 hadoop001 启动 MySQL：

   ```bash
   sudo systemctl start mysql8
   /opt/module/mysql/bin/mysql -uroot -p
   ```

   当前 MySQL 配置使用 `/opt/module/mysql/mysql.sock`。`mysqlx=0` 关闭不参与 Hive/JDBC 链路的 X Plugin；若异常退出后遗留 Socket 锁，先确认没有 `mysqld` 进程，再只清理 Socket/lock 临时文件，不碰 `data` 目录。

3. 在 hadoop001 启动 Hadoop/YARN：

   ```bash
   cd /opt/module/hadoop
   sbin/start-all.sh
   jps
   hdfs dfsadmin -report
   ```

   验收要求：3 个 Live datanodes、Decommission Status 为 `Normal`、Missing/Corrupt/Under replicated blocks 均为 0。

4. 首次初始化 Hive 元数据库并启动 HiveServer2：

   ```bash
   cd /opt/module/hive
   bin/schematool -dbType mysql -initSchema
   hive --service hiveserver2 > "$HIVE_HOME/hiveserver2.log" 2>&1 &
   ss -lntp | grep ':10000'
   ```

   `schematool` 只在 schema 尚未初始化时执行；HiveServer2 只提供表/查询访问，不承担正式 TOP10 计算。

5. 数据任务使用 `spark-submit` 读取 HDFS raw，生成并校验结果工件，再事务装载 MySQL。Spark 正式任务完成后，依次启动 Flask 和 Vue，按 #10/#11 验收 API 与页面四态。

配置归属：原始路径和结果路径由数据任务参数控制；Hive 配置归 Hive；MySQL 业务连接由 `backend/.env` 管理；真实 `.env` 不提交 Git；API 和前端地址由 #10/#12 固定。

## 6. 当前环境证据

截至 2026-08-17，已经获得以下实机证据：

- hadoop001/002/003 可以互相通信并 SSH 登录。
- `hdfs dfsadmin -report` 显示 `Live datanodes (3)`，总配置容量约 105.30 GB，三台节点均 `Normal`，缺失块、损坏副本和低副本块均为 0。
- hadoop001 的 NameNode、DataNode、SecondaryNameNode、ResourceManager、NodeManager 已运行；9000、9870、8088 端口已监听。
- VM 中 Java 1.8.0_212、Hadoop 3.3.4、Hive 3.1.3、MySQL 8.0.30 和 `spark-submit` 已确认。
- MySQL 因残留 Socket 锁文件曾启动失败；确认 PID 9024 实际为 `rsyslogd` 后清理临时锁文件，已能进入 MySQL 8.0.30 客户端。该问题不涉及数据库数据目录。
- Spark 正式 TOP10 任务、Hive schema/HiveServer2 复验、MySQL 业务结果表、Flask API 和 Vue 页面仍属于下游 Issue，不在本 Issue 中冒充完成。

## 7. 故障与降级

| 故障 | M1 处理 | 允许的降级 |
|---|---|---|
| Windows 主机找不到 `hdfs`/`hive`/`mysql` | 不作为项目故障；通过 WindTerm 在 CentOS VM 执行 | 不把 Windows PATH 结果写成集群不可用 |
| VM 未启动或 SSH 不通 | 阻塞实机链路，先恢复 VM/网络 | 固定样本可继续做本地契约开发，不冒充全量结果 |
| HDFS 不可用 | 停止正式全量任务，不改用另一份隐藏原始文件 | 固定样本和核对脚本继续验证规则 |
| Hive/HS2 不可用 | 不影响 Spark 唯一计算；需要 Hive 展示时标记该支撑层阻塞 | 直接使用 Spark 读取 HDFS raw，禁止 Pandas/Hive 另算 TOP10 |
| Spark 未安装或任务失败 | 不刷新 MySQL 服务结果 | 固定样本/Mock 只用于开发，正式结果待 Spark 恢复 |
| MySQL 不可用 | Flask 返回明确依赖失败，不现场计算 | 使用 Mock 做接口开发，不替代真实验收 |
| 结果为空但请求合法 | API 返回明确空数据结构，页面进入空数据态 | 不填充假数据 |
| Flask/前端地址错误 | API 或页面显示错误态，修正配置后重试 | Mock 只验证界面结构 |

## 8. 与后续 Issue 的交接

- #9：固定业务结果表字段、`data_version`、事务刷新和校验；不创建原始明细表。
- #10：只查询 MySQL 服务结果，固定正常、空数据、非法请求和数据库失败响应。
- #11：只消费 API，完成加载、正常、空数据和错误四态。
- #12：记录 VM 中 Java/Hadoop/Hive/Spark/MySQL 的版本、端口、配置和组长电脑启动步骤；Windows PATH 不作为目标运行环境。
- #13：按本文启动顺序补充 HDFS 原始数据、Spark 全量结果、MySQL/API/页面的一致性证据。

## 9. 当前完成边界

本 Issue 已冻结组件职责、唯一计算位置、HDFS/Hive/MySQL 存储边界、启动顺序和故障降级，并记录了 VMware 三节点集群与 MySQL 的实际证据。Spark 正式任务、HiveServer2 完整复验、MySQL 业务结果表、Flask API 和 Vue 页面继续由对应 Issue 实现和验收。
