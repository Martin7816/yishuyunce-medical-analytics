# Issue #47 执行证据：医院运营分析数据快照

执行日期：2026-08-18（Asia/Shanghai）。真实 CSV、快照工件、模型工件和数据库凭证均不进入 Git；本目录只保存可复查的摘要、命令和结果。

## 输入版本

| 项目 | 实际值 |
|---|---|
| 文件名 | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 文件大小 | `832373138` bytes |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-18T12:00:00.000000Z` |

## D-01—D-05：生成与独立核对

统一任务在 `clean_frame(raw).persist(StorageLevel.MEMORY_AND_DISK)` 后才执行首次 action；医院模块由 `facility_ranking_rows`、`grouped_summary_metrics(..., count_key="case_count")` 和 `grouped_rows` 生成。排行、选项和画像均按字符串 `facility_id` 组织，展示名称不作为聚合键。

固定边界样例包含 `120 +`、负费用、缺失诊断、同一医院多条记录和 `Facility ID` 别名：

```powershell
python data/src/run_full_analytics_pyspark.py --input data/fixtures/dashboard_edge_sample.csv --output <tmp>\edge.json --generated-at 2026-08-18T08:00:00Z
python data/src/verify_hospital_snapshot.py --input data/fixtures/dashboard_edge_sample.csv --snapshot <tmp>\edge.json
```

结果：PySpark `PASS`，4 条原始记录，12 条全量快照记录；独立医院核对 `PASS`，2 个机构、2 个画像、0 个空画像。结果摘要见 `l2-data-task/DT-HOSPITAL-FIXTURE-01/`。

真实全量执行：

```powershell
python data/src/run_full_analytics_pyspark.py --input "<本地完整 CSV>" --output "<tmp>\real-full.json" --module all --generated-at 2026-08-18T12:00:00Z
python data/src/verify_dashboard_snapshot.py --input "<本地完整 CSV>" --snapshot "<tmp>\real-full.json"
python data/src/verify_hospital_snapshot.py --input "<本地完整 CSV>" --snapshot "<tmp>\real-full.json"
```

结果：全量任务 `PASS`，2,101,588 条原始记录、690 条分析快照记录；医院独立核对 `PASS`，205 个机构、205 个画像、0 个空画像，纳入机构画像的记录为 2,090,946 条。医院 TOP5 为 Mount Sinai Hospital 49,945、North Shore University Hospital 49,203、NYU Langone Hospitals 42,864、New York-Presbyterian Hospital - New York Weill Cornell Center 42,221、New York-Presbyterian Hospital - Columbia Presbyterian Center 41,787。完整 stdout 摘要见 `l2-data-task/DT-HOSPITAL-REAL-01/`。

## D-06：快照契约与事务发布

模型记录使用同一 `data_version` 合并后，最终发布工件为 691 条记录，其中医院模块为 `index + 205 profile` 共 206 条；医院画像使用 `case_count`，不再使用通用 `record_count`。发布器 dry-run 和 MySQL `--apply` 均 `PASS`。发布后查询结果：总行数 691、医院行数 206、医院 payload 与工件逐项不一致数 0、`data_version` 数 1、`generated_at` 数 1。

```powershell
python data/src/publish_analytics_snapshot_mysql.py --input "<tmp>\real-full-with-model.json"
python data/src/publish_analytics_snapshot_mysql.py --input "<tmp>\real-full-with-model.json" --apply
```

发布 stdout、MySQL 逐项核对和事务测试结果见 `l2-data-task/DT-CONTRACT-01/`、`DT-MYSQL-01/`、`DT-TEST-01/`。事务失败回滚路径由 `data/tests/test_snapshot_publisher.py` 覆盖；真实历史批次回滚证据沿用 [`evidence/39/`](../39/)。

## D-07：下游交接

- #48 读取 `hospitals/index` 和 `hospitals/profile:{facility_id}`；`facility_a`、`facility_b` 只能取 `index.options.facilities[].value`，`metric` 只能取 `case_count`、`avg_los`、`avg_charges`、`avg_costs`、`emergency_rate`、`severe_rate`。
- #49 按接口返回顺序渲染医院排行、画像指标、主要疾病 TOP5 和内外科结构；不在前端重算、合并同名机构或改单位。
- 公共字段、版本、单位和实体键规则已同步到 `docs/07-terminal-product-contract.md` 与 `docs/04-development-and-runbook.md`。

## 验收矩阵

| 编号 | 状态 | 证据 |
|---|---|---|
| D-01 单次扫描 | PASS | `data/src/run_full_analytics_pyspark.py` 清洗帧持久化后再 action；真实全量 stdout |
| D-02 清洗口径 | PASS | 固定边界样例、真实全量 dashboard 独立核对 |
| D-03 指标公式 | PASS | `verify_hospital_snapshot.py` 标准库逐机构核对 |
| D-04 筛选快照 | PASS | 205 个 facility 选项与 205 个 profile 键，0 个空画像 |
| D-05 排序和单位 | PASS | 医院 TOP5 对照、`case_count`/美元/天/% 字段核对 |
| D-06 事务发布 | PASS | 691 行 MySQL 发布、206 条医院 payload 逐项一致、版本/时间各唯一 |
| D-07 下游交接 | PASS | 公共契约和运行手册已同步，字段/枚举/实体键已列明 |
