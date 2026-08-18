# Issue #43 执行证据

执行日期：2026-08-18（Asia/Shanghai）。真实 CSV 不进入 Git；这里只记录文件名、SHA-256、汇总结果和可复查命令。

## 真实输入与版本

| 项目 | 实际值 |
|---|---|
| 文件名 | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 文件大小 | `832373138` bytes |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-18T00:00:00.000000Z` |

## 聚合与独立校验

固定样例、边界样例和真实全量均由 `run_full_analytics_pyspark.py` 生成；真实全量结果为 2,101,588 行、690 条快照记录。`verify_dashboard_snapshot.py` 使用标准库流式读取 CSV，未导入 PySpark，逐项核对 dashboard 记录。

真实 dashboard 指标：

| 指标 | 值 |
|---|---:|
| `record_count` | 2,101,588 |
| `facility_count` | 205 |
| `avg_los` | 5.74 |
| `avg_charges` | 73,305.42 |
| `avg_costs` | 21,990.13 |
| `emergency_rate` | 0.6263 |
| `surgical_rate` | 0.2348 |
| `severe_rate` | 0.3332 |

分布条目数：`age=5`、`payment=9`、`disease_top10=10`、`hospital_top10=10`、`severity=4`。固定样例和边界样例验证了金额清洗、`120 +`、缺失 LOS 分母、外科/重症率和稳定排序。

复核命令：

```powershell
python data/src/run_full_analytics_pyspark.py --input "<本地完整 CSV>" --output "<临时目录>\real-full.json" --module all --generated-at 2026-08-18T08:00:00Z
python data/src/verify_dashboard_snapshot.py --input "<本地完整 CSV>" --snapshot "<临时目录>\real-full.json"
python -m pytest -q backend/tests data/tests
```

结果：独立 dashboard 核对 `PASS`；回滚路径和快照契约测试 `36 passed`。

## MySQL 发布状态

发布脚本的 dry-run 通过，但当前 `backend/.env` 的 `issue31_publisher` 账号对 `analysis_snapshot_result` 没有 `SELECT`、`INSERT`、`DELETE` 或 `CREATE` 权限：查询和执行 `data/sql/002-analysis-snapshot.sql` 均返回 MySQL 1142。因此没有伪造 `--apply` 成功，也没有关闭 Issue。

管理员完成目标库建表并授予上述权限后复验：

```powershell
python data/src/publish_analytics_snapshot_mysql.py --input "<临时目录>\real-full.json" --apply
```

需保存发布后记录数、唯一 `data_version`/`generated_at`、API 读取结果及故障注入回滚证据。字段、枚举、空组合 payload 和统一版本已可直接交接给 #44、#45。
