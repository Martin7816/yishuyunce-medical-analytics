# Issue #43 执行证据

执行日期：2026-08-18（Asia/Shanghai）。真实 CSV 不进入 Git；这里只记录文件名、SHA-256、汇总结果和可复查命令。

## 真实输入与版本

| 项目 | 实际值 |
|---|---|
| 文件名 | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 文件大小 | `832373138` bytes |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-18T10:30:00.000000Z` |

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

## MySQL 发布与复核

数据库管理员已完成目标表建表并授予 `issue31_publisher` 对 `analysis_snapshot_result` 的 `SELECT, INSERT, DELETE` 权限。账号授权和目标表只读检查通过：表存在，原批次为 691 行，版本/时间戳各唯一。

使用包含同一 dashboard 快照和模型记录的 691 条完整工件执行：

```powershell
python data/src/publish_analytics_snapshot_mysql.py --input "<临时目录>\analytics-snapshot-final.json" --apply
```

发布结果：`PASS`，691 rows；发布后数据库检查：691 行、1 个 `data_version`、1 个 `generated_at`。`dashboard/overview` 的 payload、版本和时间戳与工件逐项一致，数据库读取复核 `PASS`。实际数据库时间以 UTC 表示为 `2026-08-18T10:30:00.000000`，接口层按公共契约补充 `Z`。

故障回滚路径由仓库测试覆盖（`36 passed`）；字段、枚举、空组合 payload 和统一版本已直接交接给 #44、#45。
