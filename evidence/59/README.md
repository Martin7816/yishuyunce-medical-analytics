# Issue #59 执行证据：医疗费用与成本分析数据快照

执行日期：2026-08-19（Asia/Shanghai）。真实 CSV、数据库凭证和完整快照 JSON 不进入 Git；本目录只保存可复查的摘要、命令和结果。

## 输入与版本

| 项目 | 固定边界样例 | 真实 CSV |
|---|---|---|
| 文件名 | `dashboard_edge_sample.csv` | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 原始记录数 | 4 | 2,101,588 |
| 纳入清洗帧记录数 | 3 | 2,101,588 |
| 文件大小 | — | 832,373,138 bytes |
| SHA-256 | — | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `dashboard_edge_sample_sha256_fbdfedf9e512492daf9c536c406fdd50cf7f439f61b65f6b47fb0626e6ddb215` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-19T00:00:00.000000Z` | `2026-08-19T00:00:00.000000Z` |

真实输入沿用 #39 冻结清洗边界：金额去千分位后按非负 decimal 解析，`120 +` 归一为 120 并保留 `los_capped`，编码字段按字符串保留，文本去首尾空白，不按患者去重。真实 CSV 使用 `Permanent Facility Id` 作为机构编码来源。

## 执行结果

固定边界样例的 PySpark 全量快照为 `PASS`，共 87 条统一快照记录；其中 `costs` 为 15 条，6 条非空、9 条合法空组合。独立标准库复核和发布器 dry-run 均为 `PASS`。真实全量使用 `local[1]` 复现，PySpark 输出 7,197 条统一快照记录，独立复核为 `PASS`；成本模块 3,415 条，3,310 条非空、105 条合法空组合。真实输出的诊断、医院、严重程度枚举数量分别为 477、205、4；该工作流同时保留已验收的 `cohorts=168`、`risks=2,868`、`payments=60` 等并行模块记录。

固定样例命令：

```powershell
python data/src/run_full_analytics_pyspark.py --input data/fixtures/dashboard_edge_sample.csv --output <tmp>\\edge-full.json --module all --master local[1] --generated-at 2026-08-19T00:00:00Z
python data/src/verify_cost_snapshot.py --input data/fixtures/dashboard_edge_sample.csv --snapshot <tmp>\\edge-full.json
python data/src/publish_analytics_snapshot_mysql.py --input <tmp>\\edge-full.json
```

真实命令：

```powershell
python data/src/run_full_analytics_pyspark.py --input "<本地完整 CSV>" --output <tmp>\\real-full.json --module all --master local[1] --generated-at 2026-08-19T00:00:00Z
python data/src/verify_cost_snapshot.py --input "<本地完整 CSV>" --snapshot <tmp>\\real-full.json
python data/src/publish_analytics_snapshot_mysql.py --input <tmp>\\real-full.json --apply
python data/src/verify_cost_mysql.py --snapshot <tmp>\\real-full.json
```

## 口径、公式与稳定性

实体键固定为 `diagnosis=<value or *>|facility=<value or *>|severity=<value or *>`。诊断和医院筛选互斥，严重程度可叠加；合法矩阵为 `(1 + diagnosis_count + facility_count) × (1 + severity_count)`。所有正式金额指标保留两位小数。

| 输出 | 口径 |
|---|---|
| `record_count` | 当前费用筛选后的有效记录数 |
| `avg_charges` / `avg_costs` | 当前筛选后的收费/成本算术平均，单位美元 |
| `median_*` / `p25_*` / `p75_*` / `p90_*` | `percentile_approx` 的 P50/P25/P75/P90，accuracy=10000，单位美元 |
| `charge_cost_gap` | `avg(charges - costs)`，单位美元 |
| `daily_charges` / `daily_costs` | 仅 `los > 0` 记录的 `avg(charges / los)`、`avg(costs / los)`，单位美元/天 |
| 比较 sections | 对当前未筛选的诊断、医院或严重程度维度计算均值，按 value 降序、name 升序，严格 TOP10 |

Spark 使用命名聚合 DataFrame 和 cube 生成通配及有限组合，最终只 collect 小型聚合汇总。独立校验器只使用 Python 标准库读取原始 CSV 并重算键集合、记录数、均值、差值、单日指标及比较 section；真实数据的 Spark 近似分位数按相对误差 0.1%（同时绝对误差不超过 0.01）核对，固定样例使用精确边界值。

## D-01—D-07 验收矩阵

| 编号 | 状态 | 证据 |
|---|---|---|
| D-01 单次扫描与缓存 | PASS | `run_full_analytics_pyspark.py` 复用统一清洗帧；固定/真实 PySpark stdout |
| D-02 清洗与边界 | PASS | 固定样例覆盖 `120 +`、负费用、非法值和缺失分类；真实原始/纳入数一致 |
| D-03 指标公式 | PASS | `verify_cost_snapshot.py` 独立标准库逐键重算；固定与真实均 `PASS` |
| D-04 全量筛选矩阵 | PASS | 固定 15/9；真实 3,415/105；合法空组合键完整保留 |
| D-05 排序、TOP10、单位 | PASS | payload 与独立结果逐项一致；金额美元、单日金额美元/天、严格 TOP10 |
| D-06 发布、版本与回滚 | PASS | dry-run、MySQL apply、逐成本键核对和注入失败回滚均 `PASS` |
| D-07 合约与下游交接 | PASS | 公共契约、运行手册已同步；#60 后端和 #61 前端按同一 entity key/options/payload 消费 |

回滚探针只在事务内临时删除并注入失败，随后 rollback；前后总行数均为 7,197，成本行数均为 3,415，数据库最终状态未改变，详见 `l2-data-task/DT-MYSQL-01/rollback.json`。

## 下游交接

- #60 后端使用 `GET /api/v1/costs/overview` 的 `diagnosis_code` 或 `facility_id` 二选一筛选和可选 `severity`；读取 `costs` 的完整 entity key，不重算指标。
- #61 前端使用 `costs` wildcard payload 的 `options.severity`，疾病/医院 index 的 `options` 作为筛选白名单，按 payload 的 metrics/sections 渲染，不自行聚合。
- 下游必须保留 `data_version`、`generated_at`、金额单位、空组合 `metrics=[]/sections=[]` 语义；HDFS/Hive 未在本次本机验收中虚构为 `VERIFIED`，仍按公共契约显示 `CHECK_REQUIRED`。
