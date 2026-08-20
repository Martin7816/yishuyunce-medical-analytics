# Issue #55 执行证据：住院记录群体分析数据快照

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

真实输入按 #39 冻结清洗口径执行：年份为 2021、住院天数 `120 +` 归一为 120、非法住院天数剔除；不去重。金额均仅以非负可解析值参与平均值计算。

## 执行命令与结果

固定边界样例：

```powershell
python data/src/run_full_analytics_pyspark.py --input data/fixtures/dashboard_edge_sample.csv --output <tmp>\edge-full.json --generated-at 2026-08-19T00:00:00Z
python data/src/verify_cohort_snapshot.py --input data/fixtures/dashboard_edge_sample.csv --snapshot <tmp>\edge-full.json
python data/src/publish_analytics_snapshot_mysql.py --input <tmp>\edge-full.json
```

结果为 PySpark `PASS`、独立核对 `PASS`、发布器 dry-run `PASS`；共 36 个合法群体键，20 个非空组合，16 个空组合。stdout 摘要见 `l2-data-task/DT-COHORT-FIXTURE-01/`。

真实全量群体快照：

```powershell
python data/src/run_full_analytics_pyspark.py --input "<本地完整 CSV>" --output <tmp>\real-full.json --module all --generated-at 2026-08-19T00:00:00Z
python data/src/verify_cohort_snapshot.py --input "<本地完整 CSV>" --snapshot <tmp>\real-full.json
```

结果为 PySpark `PASS`、独立标准库核对 `PASS`：年龄 5 个、性别 3 个、入院类型 6 个，完整笛卡尔积为 `(5+1)×(3+1)×(6+1)=168` 个键，其中 154 个非空、14 个空组合。空组合仍输出合法记录，`metrics` 和各分析 section 为空数组，不省略键。真实 stdout 摘要见 `l2-data-task/DT-COHORT-REAL-01/`。

最终发布工件在同一 `data_version` 上保留已验证的 `high_cost_model` 记录，合计 858 行，其中 `cohorts` 为 168 行；模型记录不是本 issue 的新增计算。发布器 dry-run 和 MySQL `--apply` 均为 `PASS`，MySQL 逐项核对为 858/858 行、168/168 个群体键、payload 不一致 0、版本数 1、时间数 1。证据见 `DT-MYSQL-01/`。

## 口径、公式与稳定性

群体实体键固定为 `age=<value or *>|gender=<value or *>|admission=<value or *>`。每个维度同时支持 `*` 和清洗帧中出现的有限枚举值；内部普通空格保留，例如 `age=50 to 69|gender=*|admission=*`，但不允许首尾空白或控制字符。

| 输出 | 口径 |
|---|---|
| `record_count` | 当前群体过滤后的记录数 |
| `emergency_rate` | `Emergency` 入院记录数 / 当前群体记录数，比例为 0—1 |
| `avg_los` | 有效住院天数的算术平均，单位天 |
| `avg_charges` | 有效非负总收费的算术平均，单位美元 |
| `avg_costs` | 有效非负总成本的算术平均，单位美元 |
| `disease` / `severity` | 同一群体分母下的计数，非空项按 value 降序、name 升序，严格 TOP10 |
| `age` / `gender` | 同一群体分母下的结构计数与比例 |

通配维度通过 Spark cube 保留缺失维度值，指定枚举过滤只匹配该值；因此通配和有限组合的分母均来自同一清洗帧。聚合在 Spark DataFrame 中完成，仅 collect 小型汇总表；输出键、选项、分类项均稳定排序。

## D-01—D-07 验收矩阵

| 编号 | 状态 | 证据 |
|---|---|---|
| D-01 单次扫描与缓存 | PASS | `data/src/run_full_analytics_pyspark.py` 在首次 action 前持久化清洗帧；固定/真实 PySpark stdout |
| D-02 清洗与边界 | PASS | 固定样例覆盖 `120 +`、负费用、非法值、缺失分类；真实原始/纳入数见两组 stdout |
| D-03 指标公式 | PASS | `data/src/verify_cohort_snapshot.py` 独立标准库逐键重算，固定与真实均 `PASS` |
| D-04 全量筛选矩阵 | PASS | 固定 36/16；真实 168/14；空组合键完整保留 |
| D-05 排序、TOP10、单位 | PASS | 固定/真实 payload 与独立结果逐项一致；比例 0—1、金额美元、住院天数单位明确 |
| D-06 发布、版本与回滚 | PASS | dry-run、MySQL apply、逐项核对和注入失败回滚均 `PASS` |
| D-07 合约与下游交接 | PASS | `docs/07-terminal-product-contract.md`、`docs/04-development-and-runbook.md` 已同步；#56 API 与 #57 前端使用同一实体键和 payload |

回滚测试只在事务内临时删除并注入失败，随后 rollback；前后总行数均为 858，数据库最终状态未改变，详见 `DT-ROLLBACK-01/mysql-rollback.json`。

## 下游交接

- #56 后端按 `module_key=cohorts` 与完整实体键读取，不重算指标；空组合是合法 payload。
- #57 前端按接口返回的 `options`、`entity_key` 和 `metrics/sections` 渲染，不自行拼接或合并群体键。
- 公共字段、版本、单位、排序和实体键规则已同步到契约与运行手册。
