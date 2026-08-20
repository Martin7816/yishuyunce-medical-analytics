# Issue #39 执行证据

执行日期：2026-08-18（Asia/Shanghai）
执行范围：真实全量 CSV、统一分析快照、模型工件、独立核对、MySQL 正式发布、API 读取、事务回滚和 HDFS/Hive 支撑层检查。
真实输入不进入 Git；以下只记录文件名、大小、SHA-256、汇总结果和可复查命令。

## 输入版本

| 项目 | 实际值 |
|---|---|
| 文件名 | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 文件大小 | `832373138` bytes |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-18T11:11:56.038631Z` |

## 验收结果

| 用例 | 命令/证据 | 结果 |
|---|---|---|
| DT-REAL-01 | `run_full_analytics_pyspark.py --input <CSV> --output <snapshot.json>` | PySpark `PASS`；2,101,588 行；690 条统一快照记录 |
| DT-REAL-02 | `verify_dashboard_snapshot.py --input <CSV> --snapshot <snapshot-with-model.json>` | 独立标准库核对 `PASS`；记录数、205 个设施、平均值和五类分布逐项一致 |
| DT-MODEL-01 | `train_high_cost_model_pyspark.py --input <CSV> ...` | 模型 `PASS`；训练 1,681,301 行、测试 420,287 行；P75 阈值 77,202.39 |
| DT-CONTRACT-01 | `publish_analytics_snapshot_mysql.py --input <snapshot-with-model.json>` | dry-run `PASS`；691 条记录、唯一版本/时间、公共 payload 契约通过 |
| DT-MYSQL-APPLY-01 | `publish_analytics_snapshot_mysql.py --input <snapshot-with-model.json> --apply` | MySQL `PASS`；实际写入 691 条记录，`data_version` 正确 |
| DT-MYSQL-CONSISTENCY-01 | 发布后只读查询 | `COUNT(*)=691`；`COUNT(DISTINCT data_version)=1`；`COUNT(DISTINCT generated_at)=1` |
| DT-API-01 | Flask 真实 MySQL 模式 HTTP 检查 | health、dashboard、diseases、hospitals、data-quality、high-cost metrics 均 HTTP 200；版本一致 |
| DT-ROLLBACK-01 | 真实 MySQL 事务故障注入 + `python -m pytest backend/tests data/tests -q` | 注入 JSON 错误 3140 后旧批次仍为 691 条；自动化测试 `36 passed` |
| DT-HDFS-HIVE-01 | `hdfs dfsadmin -report`、HDFS 文件检查、HiveServer2/Beeline 元数据检查 | 3 个 Live DataNode、均 Normal、缺失/损坏/低副本块均 0；HDFS 文件 832373138 bytes、含表头 2101589 行；Hive 外部表登记成功 |
| DT-FRONTEND-01 | `npm run build` | Vite production build `PASS` |

模型记录从同一版本快照合并后，最终待发布工件为 691 条记录；模型工件与快照 `data_version` 一致。详细 stdout 保存在本目录的各用例文件中。

## 下游交接与关闭前结论

- `analysis_snapshot_result` 已由管理员完成建表和授权；发布账号对本次发布所需的 `SELECT, INSERT, DELETE` 已可用。
- 后端 `backend/.env` 已切换到 `ANALYTICS_DATA_SOURCE=mysql`，并指向本地模型工件；真实 API 已读取当前 MySQL 批次。
- HDFS 仅保存真实 CSV 的只读副本，Hive 外部表仅用于登记和检查；正式指标仍只认本机 PySpark 生成的 691 条快照，不在 Hive 重新计算。
- 详细命令和结果见 `l2-data-task/DT-MYSQL-01/`、`l2-data-task/DT-ROLLBACK-01/`、`l2-data-task/DT-HDFS-HIVE-01/`、`l3-api/`。
- 本地验收矩阵已无未解释的 `FAIL` 或 `BLOCKED`；GitHub Issue 关闭前仍需把本证据写入 Resolution，并确认 PR/分支已按仓库流程合并。
