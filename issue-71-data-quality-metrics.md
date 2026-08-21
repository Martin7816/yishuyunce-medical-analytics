# Issue #71 数据质量快照指标口径

> 快照键：`data_quality / summary`
> 适用任务：统一 PySpark 清洗帧的数据质量与任务管理聚合
> 公共约束：以 `docs/07-terminal-product-contract.md` 第 1、1.1、2、2.1 节为准；发生冲突时先在 #71 记录，不另建第二套契约。

## 1. 统计集合

所有指标均基于同一次 CSV 读取后缓存的 clean frame，不重新读取 CSV，不按患者去重，也不 collect 原始住院出院记录。

- **全部输入记录**：CSV 中进入 clean frame 的全部数据行。
- **范围内记录**：`Discharge Year` 转成字符串并去除首尾空白后等于 `2021` 的记录，即 `in_scope=true`。
- **有效分析记录**：范围内且 `Length of Stay` 能解析的住院出院记录，即 `in_scope=true AND los IS NOT NULL`。
- **金额有效记录**：`Total Charges` 与 `Total Costs` 均能解析为非负 `decimal(20,2)` 的记录，即 `valid_money=true`。
- 各异常指标允许重叠；同一条住院出院记录可以同时计入诊断缺失、LOS 异常和金额异常。

对应的 PySpark 条件为：

```python
in_scope = F.coalesce(F.col("in_scope"), F.lit(False))
valid_record = in_scope & F.col("los").isNotNull()
invalid_money = in_scope & ~F.coalesce(F.col("valid_money"), F.lit(False))
```

## 2. 正式指标

| key | 名称 | 统计范围 | 公式与边界 | 单位 |
|---|---|---|---|---|
| `raw_rows` | 原始记录 | 全部输入记录 | clean frame 首次物化得到的记录总数 | `条` |
| `valid_rows` | 纳入分析记录 | 全部输入记录 | `in_scope=true AND los IS NOT NULL` | `条` |
| `out_of_scope_rows` | 范围外记录 | 全部输入记录 | `in_scope=false`；年份为空、无法识别或不等于 `2021` 均计入 | `条` |
| `money_parse_or_negative` | 费用解析/负值异常 | 范围内记录 | charges 或 costs 任一为空、解析失败或小于 0 时计 1 条；同一行多个金额字段异常仍只计 1 条 | `条` |
| `missing_los` | 住院时长解析异常 | 范围内记录 | LOS 为空或无法转换为整数；`120 +` 不属于异常 | `条` |
| `diagnosis_missing` | 主诊断描述缺失 | 范围内记录 | diagnosis 为 null 或 trim 后为空；不因同一行 LOS 异常而漏计 | `条` |
| `los_capped` | 住院时长 120+ 截断 | 范围内记录 | 原始 LOS trim 后等于 `120 +`；清洗值映射为 120，同时保留 `los_capped=true` | `条` |

## 3. 清洗边界

- `Total Charges` 和 `Total Costs` 去除首尾空白及千分位逗号后转为 `decimal(20,2)`。
- 金额解析失败、为空或为负数时，记录不进入正式金额聚合，但不因此自动排除于其他非金额分析。
- `Length of Stay` 的 `120 +` 映射为数值 120，并标记 `los_capped=true`。
- 诊断描述等文本字段去除首尾空白。
- 诊断代码、机构代码等代码字段按字符串保留。
- 原始住院出院记录不按患者去重；本文不使用“患者数”描述记录数。

## 4. 批次、版本和时间

- 全部模块共享输入文件 SHA-256 生成的同一个 `data_version`。
- 全部模块共享同一个 `generated_at`。
- `data_version` 和 `generated_at` 使用快照文档或记录外层的冻结字段，不新增字符串 metric，也不扩展 payload 顶层字段。
- `generated_at` 必须为带 6 位微秒并以 `Z` 结尾的 UTC 字符串。

## 5. 存储与任务状态

状态 section 固定使用：

```text
key   = storage
type  = status
title = 存储与任务状态
```

### 5.1 固定样例

| 名称 | 状态 |
|---|---|
| HDFS | `CHECK_REQUIRED` |
| Hive | `CHECK_REQUIRED` |
| MySQL | `CHECK_REQUIRED` |
| PySpark任务 | `FIXTURE_ONLY` |

fixture 不能出现 `VERIFIED` 或 `PASS` 等会被误读为真实环境验收的状态。

### 5.2 真实 CSV 已生成但尚未发布

| 名称 | 状态 |
|---|---|
| HDFS | 无执行证据时为 `CHECK_REQUIRED` |
| Hive | 无执行证据时为 `CHECK_REQUIRED` |
| MySQL | `NOT_PUBLISHED` |
| PySpark任务 | 真实运行成功时为 `PASS` |

HDFS、Hive、MySQL 和 PySpark 的已验证状态必须来自实际执行证据；没有检查证据时不得填写 `VERIFIED`。

## 6. 输出结构约束

- 唯一快照键为 `module_key=data_quality`、`entity_key=summary`。
- 每个 metric 只能包含 `key`、`label`、`value`、`unit`，且 `value` 必须是有限数字。
- 状态 section 的 item 使用字符串状态值。
- payload 顶层只允许 `title`、`description`、`options`、`filters`、`metrics`、`sections`。
- 不在网页请求、后端接口、Hive、Pandas或前端中重新计算正式指标。

## 7. 对当前实现的约束

后续实现必须完成以下调整：

1. 将数据质量的多次 `.count()` 改为一个可命名的聚合 DataFrame，并只 collect 一行汇总结果。
2. `diagnosis_missing` 按全部范围内记录统计，不能仅在 LOS 有效记录中统计。
3. `los_capped` 只统计范围内记录，不能把非 2021 年记录计入。
4. fixture 的 MySQL 状态使用 `CHECK_REQUIRED`，真实数据尚未发布时使用 `NOT_PUBLISHED`。
5. `raw_rows` 复用 clean frame 首次物化得到的计数，不重新读取 CSV。

## 8. 本步骤完成判定

- [x] 七个指标的 key、名称、统计范围、公式和单位已明确。
- [x] 异常重叠、年份范围、LOS、金额和诊断缺失边界已明确。
- [x] fixture 与真实任务的状态语义已明确。
- [x] `data_version` 和 `generated_at` 的承载位置已明确。
- [x] 后续代码与测试必须修正的现有差异已列出。

## 9. Clean frame 检查结果

检查对象：`data/src/run_full_analytics_pyspark.py` 中的 `clean_frame()`、`build_document()` 和 `main()`。

| 检查项 | 当前实现 | 结果 |
|---|---|---|
| 文本字段 | `F.trim(source(name).cast("string"))` | PASS |
| 代码字段 | 诊断代码、机构代码等通过同一字符串 trim 逻辑保留 | PASS |
| 金额字段 | 去除千分位逗号后转为 `decimal(20,2)` | PASS |
| 金额有效性 | charges/costs 均非空且非负时 `valid_money=true` | PASS |
| 普通 LOS | trim 后转为整数，非法内容得到 null | PASS |
| LOS `120 +` | 映射为 120，并保留 `los_capped=true` | PASS |
| 年份范围 | 年份 trim 后与字符串 `2021` 比较 | PASS |
| 空年份 | `in_scope` 可为 null，质量聚合阶段通过 `coalesce(..., false)` 按范围外处理 | PASS |
| 清洗阶段去重 | `clean_frame()` 中没有 `distinct()` 或 `dropDuplicates()` | PASS |
| CSV 读取次数 | `main()` 中只有一次 `spark.read...csv(input_path)` | PASS |
| 缓存顺序 | `clean_frame(raw).persist(MEMORY_AND_DISK)` 后才进入文档构建 | PASS |
| 首次物化 | `build_document()` 首个 action 为 `raw_count = cleaned.count()` | PASS |
| 原始记录 collect | clean frame 未 collect 原始住院出院记录 | PASS |

### 9.1 代码定位

- `clean_frame()`：负责字段选择、文本 trim、金额转换、LOS 转换、`in_scope` 和 `valid_money`。
- `main()`：读取一次 CSV，校验必需列，然后持久化 clean frame。
- `build_document()`：通过 `cleaned.count()` 首次物化缓存，并将该值作为 `raw_rows` 复用。
- 后续出现的 `groupBy()`、`distinct()` 和 `dropDuplicates()` 位于模块聚合或枚举索引构建中，不属于 clean frame 的原始记录去重。

### 9.2 第三步结论

当前 `clean_frame()` 已提供 #71 所需的清洗字段，第三步不需要修改 PySpark 清洗代码。第四步应在不改变公共清洗口径的前提下：

1. 新增单次数据质量汇总聚合；
2. 修正 `diagnosis_missing` 和 `los_capped` 的统计范围；
3. 根据 fixture/真实输入设置正确的存储和任务状态。

第三步状态：**PASS**。

## 10. 第四步：单次数据质量聚合

### 10.1 实现结果

- 新增 `build_data_quality_record(frame, raw_count, execution_status)`。
- 使用一个命名的 `quality_summary_frame` 同时计算六个派生计数，并且只执行一次 `collect()[0]`。
- `raw_rows` 继续复用 clean frame 首次物化得到的 `raw_count`。
- `build_records()` 不再为数据质量指标分别执行 `.count()`。
- `diagnosis_missing` 改为按全部范围内记录统计。
- `los_capped` 改为只统计范围内记录。
- fixture 目录中的输入统一识别为 `FIXTURE_ONLY`，MySQL 状态为 `CHECK_REQUIRED`。
- 真实输入仍使用 PySpark `PASS`、MySQL `NOT_PUBLISHED`，直至取得真实发布证据。

### 10.2 固定样例执行证据

执行输入：`data/fixtures/sparcs_mvp_sample.csv`
执行时间：`2026-08-19T00:00:00.000000Z`
输出：`.tmp/issue-71/step4-snapshot.json`（本地临时证据，不作为真实数据验收）

| 检查项 | 实际结果 | 状态 |
|---|---:|---|
| `data_quality / summary` 键数量 | 1 | PASS |
| `raw_rows` | 16 | PASS |
| `valid_rows` | 16 | PASS |
| `out_of_scope_rows` | 0 | PASS |
| `money_parse_or_negative` | 0 | PASS |
| `missing_los` | 0 | PASS |
| `diagnosis_missing` | 1 | PASS |
| `los_capped` | 1 | PASS |
| HDFS | `CHECK_REQUIRED` | PASS |
| Hive | `CHECK_REQUIRED` | PASS |
| MySQL | `CHECK_REQUIRED` | PASS |
| PySpark任务 | `FIXTURE_ONLY` | PASS |

公共发布器测试：`data/tests/test_snapshot_publisher.py`，结果 `8 passed`。

运行环境说明：`.venv-1` 当前未安装 PySpark；本次 Spark 验证使用仓库已有 `.venv`（PySpark 3.4.0）。Windows 上 Spark 退出时出现临时目录清理警告，但命令退出码为 0，快照生成和结构校验均成功。

第四步状态：**PASS**。

## 11. 第五步：数据质量固定样例

### 11.1 样例文件

固定样例：`data/fixtures/data_quality_snapshot_sample.csv`，共 10 条住院出院记录。

| 场景 | 覆盖内容 |
|---|---|
| 正常记录 | 正常年份、诊断、LOS、收费和成本 |
| 千分位金额 | `"1,000.00"` 去逗号后解析为 `decimal(20,2)` |
| LOS 截断 | `120 +` 映射为 120，并标记 `los_capped=true` |
| 主诊断描述缺失 | 2021 年范围内 diagnosis 为空 |
| 收费解析失败 | charges 为 `abc` |
| 成本解析失败 | costs 为 `bad` |
| 负金额 | charges 为 `-1.00` |
| LOS 解析失败 | 2021 年范围内 LOS 为 `bad` |
| 范围外多重异常 | 2020 年记录同时包含空诊断、非法 LOS 和金额异常，只计入范围外记录 |
| trim | 年份、诊断、代码、入院方式、LOS 和金额带首尾空白 |

### 11.2 手工预期

| 指标 | 预期值 |
|---|---:|
| `raw_rows` | 10 |
| `valid_rows` | 8 |
| `out_of_scope_rows` | 1 |
| `money_parse_or_negative` | 3 |
| `missing_los` | 1 |
| `diagnosis_missing` | 1 |
| `los_capped` | 1 |

边界预期：2020 年范围外记录中的空诊断、非法 LOS 和异常金额，不增加三个范围内异常指标；charges 和 costs 同行异常时，金额异常仍按一条住院出院记录计数。

### 11.3 PySpark 实际结果

执行输出：`.tmp/issue-71/step5-snapshot.json`（本地临时证据）。

| 检查项 | 实际结果 | 状态 |
|---|---:|---|
| `data_quality / summary` 键数量 | 1 | PASS |
| `raw_rows` | 10 | PASS |
| `valid_rows` | 8 | PASS |
| `out_of_scope_rows` | 1 | PASS |
| `money_parse_or_negative` | 3 | PASS |
| `missing_los` | 1 | PASS |
| `diagnosis_missing` | 1 | PASS |
| `los_capped` | 1 | PASS |
| HDFS | `CHECK_REQUIRED` | PASS |
| Hive | `CHECK_REQUIRED` | PASS |
| MySQL | `CHECK_REQUIRED` | PASS |
| PySpark任务 | `FIXTURE_ONLY` | PASS |
| fixture 版本前缀 | `fixture:` | PASS |

- `data_version`：`fixture:data_quality_snapshot_sample_sha256_127cb6a7e0afe1d84759b8f7d644b96dc5e11da7f014112cf959e38648d7f1c7`
- `generated_at`：`2026-08-19T00:00:00.000000Z`
- 命令退出码：0
- Windows Spark 退出时仍有临时目录清理警告，但快照生成、公共结构校验和逐指标断言均成功。

第五步状态：**PASS**。

## 12. 第六步：专项自动化测试

### 12.1 测试文件

新增 `data/tests/test_data_quality_snapshot.py`。整份测试使用 module 级 fixture，只启动一次 Spark，并将生成工件写入 pytest 临时目录，不污染仓库固定路径。

### 12.2 自动化覆盖

| 检查项 | 测试内容 | 状态 |
|---|---|---|
| 唯一快照键 | 只有一个 `data_quality / summary` | PASS |
| 七项指标 | 与第五步冻结预期精确相等 | PASS |
| 指标单位 | 七项指标统一使用 `条` | PASS |
| 范围外隔离 | 2020 年多重异常不污染范围内异常计数 | PASS |
| fixture 状态 | HDFS/Hive/MySQL=`CHECK_REQUIRED`，PySpark=`FIXTURE_ONLY` | PASS |
| section 类型 | `storage.type=status` | PASS |
| fixture 版本 | `data_version` 以 `fixture:` 开头 | PASS |
| 生成时间 | 固定为 `2026-08-19T00:00:00.000000Z` | PASS |
| payload 结构 | 必需字段存在，且不超出冻结顶层白名单 | PASS |

### 12.3 执行结果

专项测试：

```text
python -m pytest data/tests/test_data_quality_snapshot.py -q
7 passed in 15.55s
```

相关回归测试：

```text
python -m pytest \
  data/tests/test_data_quality_snapshot.py \
  data/tests/test_snapshot_publisher.py \
  data/tests/test_hospital_snapshot.py \
  data/tests/test_disease_snapshot.py \
  data/tests/test_cohort_snapshot.py -q
21 passed in 63.94s
```

第六步状态：**PASS**。

## 13. 第七步：标准库独立核对

### 13.1 核对器

新增 `data/src/verify_data_quality_snapshot.py`，只使用 Python 标准库：

- `csv.DictReader`：独立逐行读取 CSV；
- `decimal.Decimal`：独立解析金额并拒绝非有限值；
- `hashlib.sha256`：独立计算输入摘要；
- `json`：读取 PySpark 快照；
- `datetime` 和正则表达式：校验 6 位微秒 UTC 时间。

核对器未导入 PySpark、Pandas或 `run_full_analytics_pyspark.py`，不复用正式聚合函数。

### 13.2 独立检查范围

| 检查项 | 结果 |
|---|---|
| 七项指标逐项比较 | PASS |
| 七项指标 key 完整且无重复 | PASS |
| 七项单位为 `条` | PASS |
| 唯一 `data_quality / summary` | PASS |
| 输入文件名 | PASS |
| 输入 SHA-256 | PASS |
| `input.raw_rows` | PASS |
| fixture `data_version` | PASS |
| `generated_at` 格式 | PASS |
| `storage.type=status` | PASS |
| fixture 四项状态 | PASS |

### 13.3 正向运行证据

```text
python data/src/verify_data_quality_snapshot.py \
  --input data/fixtures/data_quality_snapshot_sample.csv \
  --snapshot .tmp/issue-71/step5-snapshot.json
```

- 状态：`PASS`
- 退出码：0
- 七项 expected 与 actual 全部一致。
- SHA-256：`127cb6a7e0afe1d84759b8f7d644b96dc5e11da7f014112cf959e38648d7f1c7`
- data_version：`fixture:data_quality_snapshot_sample_sha256_127cb6a7e0afe1d84759b8f7d644b96dc5e11da7f014112cf959e38648d7f1c7`

### 13.4 失败检测证据

自动化测试把临时快照中的 `diagnosis_missing` 从 1 篡改为 999，再运行同一个标准库核对器：

- 状态：`FAIL`
- 退出码：1
- 失败项：`diagnosis_missing`
- expected：1
- actual：999

原始正确快照未被修改。

### 13.5 回归结果

数据质量专项、发布器、医院、疾病和群体相关测试：

```text
23 passed in 64.00s
```

第七步状态：**PASS**。

## 14. 第八步：固定样例最终验收

### 14.1 验收矩阵

| 编号 | 检查项 | 证据 | 状态 |
|---|---|---|---|
| D-01 | 单次扫描 | `main()` 只读取一次 CSV；clean frame 先 persist，首次 action 为 `cleaned.count()`；#71 使用单个 `quality_summary_frame` 并只 collect 一行 | PASS |
| D-02 | 清洗口径 | `data_quality_snapshot_sample.csv` 覆盖金额、LOS、文本、代码、空值、年份范围和 `120 +`；专项断言通过 | PASS |
| D-03 | 指标公式 | 标准库核对器独立计算七项指标，expected 与 actual 全部一致；篡改指标可被拒绝 | PASS |
| D-04 | 快照键 | 唯一 `data_quality / summary`；input 文件名、SHA-256、raw_rows、fixture 版本和 generated_at 一致 | PASS |
| D-05 | 排序单位 | 本模块无排行；七项指标单位均为 `条`，storage section 类型为 `status` | PASS |
| D-06 | 事务发布 | 857 条真实快照事务发布；最终工件与 MySQL 逐项一致；重复发布和失败回滚通过 | PASS |
| D-07 | 下游交接 | #72、#73 已发布字段、枚举、状态和 Mock 交接评论 | PASS |

### 14.2 最终 fixture 工件

- 输入：`data/fixtures/data_quality_snapshot_sample.csv`
- 本地输出：`.tmp/issue-71/final-fixture-snapshot.json`
- 快照键数量：1
- 输入记录：10
- SHA-256：`127cb6a7e0afe1d84759b8f7d644b96dc5e11da7f014112cf959e38648d7f1c7`
- data_version：`fixture:data_quality_snapshot_sample_sha256_127cb6a7e0afe1d84759b8f7d644b96dc5e11da7f014112cf959e38648d7f1c7`
- generated_at：`2026-08-19T00:00:00.000000Z`
- PySpark 命令退出码：0

### 14.3 最终指标

| 指标 | PySpark | 标准库 | 状态 |
|---|---:|---:|---|
| `raw_rows` | 10 | 10 | PASS |
| `valid_rows` | 8 | 8 | PASS |
| `out_of_scope_rows` | 1 | 1 | PASS |
| `money_parse_or_negative` | 3 | 3 | PASS |
| `missing_los` | 1 | 1 | PASS |
| `diagnosis_missing` | 1 | 1 | PASS |
| `los_capped` | 1 | 1 | PASS |

### 14.4 最终执行结果

- PySpark 生成：PASS
- 公共结构校验：PASS
- 标准库独立核对：PASS，退出码 0
- 篡改检测：PASS，错误快照退出码 1
- 数据质量、发布器、医院、疾病和群体相关回归：`23 passed in 64.62s`
- `git diff --check`：PASS（仅有工作区 LF/CRLF 提示，无空白错误）
- 密钥、个人绝对路径和真实数据扫描：未发现
- `.tmp/`：仅为本地运行工件，不纳入提交

fixture 仅证明并行开发基线和固定口径可复现，不替代真实 CSV、HDFS/Hive/MySQL 或最终验收证据。

第八步状态：**PASS**。固定样例验收完成；D-06、D-07 的后续证据分别见第十步和第十一步。

## 15. 第九步：真实 CSV 全量验收

### 15.1 真实输入

真实 CSV 保存在 Git 仓库外；证据只记录文件名和冻结标识，不记录个人绝对路径。

| 项目 | 实际值 | 状态 |
|---|---|---|
| 文件名 | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` | PASS |
| 文件大小 | 832,373,138 bytes | PASS |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` | PASS |
| 记录数 | 2,101,588 | PASS |

文件名、大小和 SHA-256 与 `docs/01-data-and-feasibility.md`、`evidence/39/README.md` 冻结的上游版本完全一致。

### 15.2 PySpark 全量执行

- 输入：仓库外真实 CSV；
- 输出：`.tmp/issue-71/real-snapshot.json`；
- 模式：`--module all`；
- 命令退出码：0；
- 统一快照记录数：857；
- `data_quality / summary` 键数量：1；
- data_version：`sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`；
- generated_at：`2026-08-20T00:49:28.752790Z`；
- data_version 不含 `fixture:` 前缀；
- 工件未保存真实 CSV 的个人绝对路径。

Windows 本地 Spark 仍报告 `winutils.exe` 和退出时 PID 清理警告，但主命令退出码为 0，工件写入、公共结构校验和后续独立核对均成功。

### 15.3 七项真实指标

| 指标 | PySpark | 标准库 | 单位 | 状态 |
|---|---:|---:|---|---|
| `raw_rows` | 2,101,588 | 2,101,588 | 条 | PASS |
| `valid_rows` | 2,101,588 | 2,101,588 | 条 | PASS |
| `out_of_scope_rows` | 0 | 0 | 条 | PASS |
| `money_parse_or_negative` | 0 | 0 | 条 | PASS |
| `missing_los` | 0 | 0 | 条 | PASS |
| `diagnosis_missing` | 1,634 | 1,634 | 条 | PASS |
| `los_capped` | 1,561 | 1,561 | 条 | PASS |

### 15.4 标准库独立核对

使用 `verify_data_quality_snapshot.py` 独立扫描完整 CSV：

- 退出码：0；
- 总状态：PASS；
- 七项 expected 与 actual 全部一致；
- metric key 和单位：PASS；
- input 文件名、SHA-256 和 raw_rows：PASS；
- data_version：PASS；
- generated_at 六位微秒 UTC 格式：PASS。

### 15.5 真实环境状态

| 名称 | 实际状态 | 说明 |
|---|---|---|
| HDFS | `CHECK_REQUIRED` | 尚无真实 HDFS 检查证据 |
| Hive | `CHECK_REQUIRED` | 尚无真实 Hive 检查证据 |
| MySQL | `NOT_PUBLISHED` | 尚未执行第十步事务发布 |
| PySpark任务 | `PASS` | 真实全量运行和独立核对通过 |

第九步状态：**PASS**。真实 CSV、真实全量 PySpark、七项独立核对、版本和路径泄漏检查均已完成；MySQL 发布证据见第十步，下游交接证据见第十一步。

## 16. 第十步：MySQL 事务发布验收

### 16.1 发布前校验

真实工件执行发布器 dry-run：

| 项目 | 实际结果 | 状态 |
|---|---:|---|
| 模式 | `dry-run` | PASS |
| 快照记录数 | 857 | PASS |
| data_version | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` | PASS |
| 公共结构与主键校验 | 通过 | PASS |

### 16.2 首次发布与逐项比较

- 发布模式：`mysql`；
- 发布器状态：PASS；
- 事务发布行数：857；
- 发布后总行数：857；
- distinct data_version：1；
- distinct generated_at：1；
- `data_quality / summary` 行数：1；
- payload 与发布工件：一致；
- data_version：一致；
- generated_at：一致。

### 16.3 重复发布

对同一真实工件再次执行 `--apply`：

- 发布器状态：PASS；
- 发布后总行数仍为 857；
- 未产生重复主键；
- 未产生混合版本或混合时间；
- 后续只读核对继续 PASS。

### 16.4 发布状态闭环

首次发布和数据库查询提供了真实 MySQL 成功证据。生成器新增显式 `--mysql-status` 参数：

- 默认真实工件为 `NOT_PUBLISHED`；
- 只有取得实际发布证据后才使用 `--mysql-status VERIFIED`；
- fixture 无论传入何值都强制使用 `CHECK_REQUIRED`，避免 fixture 伪装真实验收。

最终真实工件：`.tmp/issue-71/real-snapshot-verified.json`。

| 项目 | 最终结果 | 状态 |
|---|---|---|
| 记录数 | 857 | PASS |
| generated_at | `2026-08-20T01:23:35.486156Z` | PASS |
| HDFS | `CHECK_REQUIRED` | PASS |
| Hive | `CHECK_REQUIRED` | PASS |
| MySQL | `VERIFIED` | PASS |
| PySpark任务 | `PASS` | PASS |
| 七项标准库独立核对 | 全部一致 | PASS |

最终工件发布后，`verify_data_quality_mysql.py` 只读查询结果：

```text
status=PASS
total_rows=857
expected_total_rows=857
distinct_data_versions=1
distinct_generated_at=1
data_quality_rows=1
expected_data_quality_rows=1
payload_match=true
data_version_match=true
generated_at_match=true
```

### 16.5 回滚证据

`data/tests/test_snapshot_publisher.py` 使用故障注入让发布后完整性检查失败，验证：

- 已开启事务；
- 调用 rollback；
- 未调用 commit；
- 连接正确关闭。

测试结果：`8 passed`。受控故障测试避免在共享真实数据库中故意写入半批次；发布器生产代码对任何异常统一 rollback 后重新抛出。

第十步状态：**PASS**。D-06 已完成；D-07 下游交接证据见第十一步。

## 17. 第十一步：下游交接包

### 17.1 交接给 #72（后端）

- 数据库键：`module_key=data_quality`、`entity_key=summary`。
- API：`GET /api/v1/data-quality/summary`；仅允许可选参数 `data_version`。
- 路由只读取快照，不重新计算、排序、换单位或修补空值。
- payload 顶层字段：`title`、`description`、`metrics`、`sections`。
- 七项 metric key：`raw_rows`、`valid_rows`、`out_of_scope_rows`、`money_parse_or_negative`、`missing_los`、`diagnosis_missing`、`los_capped`；单位均为 `条`。
- 状态 section：`key=storage`、`type=status`；item 名称固定为 `HDFS`、`Hive`、`MySQL`、`PySpark任务`。
- 当前真实批次：`data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，`generated_at=2026-08-20T01:23:35.486156Z`。
- 当前真实状态：HDFS/Hive=`CHECK_REQUIRED`、MySQL=`VERIFIED`、PySpark任务=`PASS`。
- MySQL 已验证 857 条快照记录，且 payload、版本、时间与最终工件逐项一致。

### 17.2 交接给 #73（前端）

- 页面路由：`/data-quality`；数据来自 `GET /api/v1/data-quality/summary`。
- 指标卡按 API 返回的 `metrics` 原顺序展示，不在页面计算或重排。
- `storage` 使用公共 `status` renderer；状态字符串按原值展示，不推断未验证状态。
- `CHECK_REQUIRED` 表示尚无对应环境检查证据；`VERIFIED` 表示已经取得存储验证证据；`PASS` 表示真实 PySpark 任务成功。
- fixture 的 `data_version` 必须以 `fixture:` 开头，且 HDFS/Hive/MySQL=`CHECK_REQUIRED`、PySpark任务=`FIXTURE_ONLY`；页面必须明确提示 fixture，不能当作真实验收。
- 真实批次的七项值依次为：2,101,588、2,101,588、0、0、0、1,634、1,561。
- loading/success/empty/error/retry 继续使用公共四态；页面不得直连 MySQL，也不得触发数据任务。

### 17.3 D-07 完成边界

上述冻结交接包已由 `wisxn` 分别发布到 #72 和 #73：#72 评论时间为 `2026-08-20T13:24:30Z`，#73 评论时间为 `2026-08-20T13:25:09Z`。两条评论均包含字段、枚举、真实批次、状态语义和 fixture/Mock 边界；#72、#73 当前均已关闭。

第十一步状态：**PASS**。D-07 已完成。#71 仍需等待共享分支合入 `main`，并由维护者在 #70 发布 #71 的独立 Resolution 后才能关闭。

## 18. 合入 main 前的契约同步

2026-08-21 将最新 `origin/main` 合入共享分支时，`data/src/run_full_analytics_pyspark.py` 与 #102 已合入的业务字段分母审计发生内容冲突。最终保留 #71 的七项必需指标、真实 MySQL 状态参数和独立标准库核对，同时接纳公共契约新增的 `severity_valid_rows`、`severity_missing_rows`、`field_validity`、`field_missing` 和 `options.audit`。#71 核对器继续逐项验证七项冻结质量指标，并允许公共契约以后增加不重名的新指标。

同步后验证：

```text
python -m pytest data/tests/test_data_quality_snapshot.py -q
9 passed in 17.64s

python -m pytest data/tests/test_data_quality_snapshot.py data/tests/test_snapshot_publisher.py data/tests/test_hospital_snapshot.py data/tests/test_disease_snapshot.py data/tests/test_cohort_snapshot.py data/tests/test_risk_snapshot.py -q
27 passed in 83.98s
```

后端测试在当前 `.venv` 与 `.venv-1` 中均因未安装 Flask 而无法启动；本次同步未修改 `main` 已有后端实现。最终状态：**READY_TO_MERGE**。
