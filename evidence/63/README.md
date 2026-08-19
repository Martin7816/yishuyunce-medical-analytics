# Issue #63 执行证据：病情严重程度与风险分析数据快照

执行日期：2026-08-19（Asia/Shanghai）。完整 CSV、完整快照 JSON 和数据库凭证不进入 Git；本目录只保存可复查的摘要与 stdout 结果。

## 输入与版本

| 项目 | 固定边界样例 | 真实 CSV |
|---|---:|---:|
| 文件名 | `dashboard_edge_sample.csv` | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 原始记录数 | 4 | 2,101,588 |
| 纳入风险清洗帧记录数 | 3 | 2,101,588 |
| SHA-256 | — | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `dashboard_edge_sample_sha256_fbdfedf9e512492daf9c536c406fdd50cf7f439f61b65f6b47fb0626e6ddb215` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-19T00:00:00.000000Z` | `2026-08-19T00:00:00.000000Z` |

清洗沿用 #39 统一口径：年份去首尾空白后为 `2021`，住院天数 `120 +` 映射为 `120`，无法解析的住院天数不纳入风险分母；金额只在各自可解析且非负时参与平均值计算；记录不按患者去重。

## 生成、独立核对与契约检查

固定样例生成了全量快照 58 条，其中风险模块 12 条；独立标准库脚本逐键重算风险指标、section、排序和空组合，结果为 `PASS`。发布器 dry-run 也为 `PASS`。对应 stdout 见 `l2-data-task/DT-RISK-FIXTURE-01/`。

真实风险阶段调用 `data/src/run_full_analytics_pyspark.py` 中的统一 `clean_frame` 和 `build_risk_records`，只收集 Spark 小型聚合结果，不收集原始住院行；使用 D 盘临时目录和低并发配置完成全量风险工件。结果为 2,868 个合法键：

- 5 个年龄枚举、477 个诊断编码，完整矩阵为 `(5+1)×(477+1)=2,868`；
- 2,614 个非空组合、254 个合法空组合，空键没有省略；
- wildcard 分母为 2,101,588 条，高风险 `Major/Extreme` 为 700,276 条；
- 真实文件 SHA-256、`data_version` 和 `generated_at` 与快照一致。

真实生成摘要和逐键独立核对见 `l2-data-task/DT-RISK-REAL-01/`。

## 口径与公共字段

风险实体键固定为 `age={value or *}|diagnosis={value or *}`；筛选字段固定为 `age_group`、`diagnosis_code`。wildcard 和所有有限组合均发布；合法空组合的 `metrics`、`sections` 为空数组，但保留标题、描述、过滤条件和实体键。

指标包括 `high_risk_count`、`high_risk_rate`、高风险平均住院时长、平均收费、平均成本。比例值保持 `0—1`，单位为 `%`；记录数单位为 `条`；金额单位为 `美元`。严重程度、死亡风险以当前筛选记录为分母，离院去向、年龄结构、疾病 TOP10 只描述 `Major/Extreme` 记录；排行按 `value` 降序、`name` 升序。

## MySQL 发布、逐键查询与回滚

发布前读取到目标表已有统一批次 691 条，其中风险模块 1 条；本次以该批次为基线，仅替换风险模块，保留其他模块，形成 3,558 条完整发布工件。这样不会以风险子集覆盖其他已发布模块。

- publisher dry-run：`PASS`，工件 3,558 条；
- `--apply`：`PASS`，事务替换后表内 3,558 条；
- 独立 SQL 查询：总行数 3,558，版本数 1，时间数 1，风险键 2,868，缺失/多余键 0，风险 payload 不一致 0；
- 故障注入回滚：`PASS`，删除后故意抛错并 rollback，前后均 3,558 行、风险 2,868 行，批次摘要哈希相同。

具体结果见 `l2-data-task/DT-MYSQL-01/` 和 `l2-data-task/DT-ROLLBACK-01/`。

## D-01—D-07 验收矩阵

| 编号 | 状态 | 证据 |
|---|---|---|
| D-01 单次扫描与统一清洗帧 | PASS | `run_full_analytics_pyspark.py` 在首次 action 前物化持久化清洗帧；风险函数只接收清洗帧，不读取 raw 或收集原始行 |
| D-02 清洗与边界 | PASS | fixture 覆盖 `120 +`、非法住院天数、空值和负金额；真实原始/纳入数及 SHA-256 已核对 |
| D-03 指标公式 | PASS | `verify_risk_snapshot.py` 不导入生产聚合，标准库逐行重算全部矩阵、指标、section 和 TOP10 |
| D-04 筛选快照 | PASS | fixture 12/4；真实 2,868/254；wildcard、有限组合和空组合均存在 |
| D-05 排序、TOP10、单位 | PASS | 独立核对逐项相等；比例 0—1、金额美元、住院时长天、记录数条，疾病严格 TOP10 |
| D-06 事务发布、查询、回滚 | PASS | dry-run、MySQL `--apply`、逐键 SQL 对照和故障注入 rollback 均 PASS |
| D-07 合约与下游交接 | PASS | `docs/04-development-and-runbook.md`、`docs/07-terminal-product-contract.md` 已同步；#64/#65 交接评论已补充 |

## 回归测试

在同一工作树执行 `python -m pytest data/tests -q`：`16 passed in 157.77s`。
