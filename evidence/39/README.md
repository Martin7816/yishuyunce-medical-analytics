# Issue #39 执行证据

执行日期：2026-08-18（Asia/Shanghai）
执行范围：真实全量 CSV、统一分析快照、模型工件、独立核对和 MySQL 发布前检查。
真实输入不进入 Git；以下只记录文件名、大小、SHA-256、汇总结果和可复查命令。

## 输入版本

| 项目 | 实际值 |
|---|---|
| 文件名 | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 文件大小 | `832373138` bytes |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-18T10:30:00.000000Z` |

## 已通过

| 用例 | 命令/证据 | 结果 |
|---|---|---|
| DT-REAL-01 | `run_full_analytics_pyspark.py --input <CSV> --output <snapshot.json>` | PySpark `PASS`；2,101,588 行；690 条统一快照记录 |
| DT-REAL-02 | `verify_dashboard_snapshot.py --input <CSV> --snapshot <snapshot-with-model.json>` | 独立标准库核对 `PASS`；记录数、205 个设施、平均值和五类分布逐项一致 |
| DT-MODEL-01 | `train_high_cost_model_pyspark.py --input <CSV> ...` | 模型 `PASS`；训练 1,681,301 行、测试 420,287 行；P75 阈值 77,202.39 |
| DT-CONTRACT-01 | `publish_analytics_snapshot_mysql.py --input <snapshot-with-model.json>` | dry-run `PASS`；691 条记录、唯一版本/时间、公共 payload 契约通过 |
| DT-ROLLBACK-01 | `python -m pytest backend/tests data/tests -q` | `36 passed`；包含完整性校验失败后的 rollback 单元测试 |

模型记录从同一版本快照合并后，最终待发布工件为 691 条记录；模型工件与快照 `data_version` 一致。详细 stdout 保存在本目录的各用例文件中。

## 当前阻塞

网络到 `192.168.219.128:3306` 可达，但 `backend/.env` 中的 `issue31_publisher` 账号实际授权为：只对旧表 `disease_case_count_top10_result` 拥有 `SELECT, INSERT, DELETE`。对 `analysis_snapshot_result` 的只读查询返回 1142，执行 `data/sql/002-analysis-snapshot.sql` 也返回 1142 `CREATE command denied`。因此本轮没有把 `--apply` 冒充成成功，也没有关闭 Issue。

管理员需要在目标库执行 DDL，并至少授予发布账号新表的 `SELECT, INSERT, DELETE` 权限；完成后复验：

```powershell
python data/src/publish_analytics_snapshot_mysql.py --input <snapshot-with-model.json> --apply
```

复验需保存发布后行数、单一 `data_version`/`generated_at`、API 读取结果，以及注入插入失败后旧批次仍可读的 rollback 证据。HDFS/Hive 当前仍按冻结契约标记 `CHECK_REQUIRED`，没有伪造 `VERIFIED`。
