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
| D-06 | 事务发布 | 等待真实 MySQL 发布、工件逐项比较、重复发布和失败回滚证据 | TODO |
| D-07 | 下游交接 | 等待向 #72、#73 发布字段、枚举、状态和 Mock 交接评论 | TODO |

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

第八步状态：**PASS**。D-06、D-07 尚未完成，#71 当前不能关闭。

## 15. 第九步：真实 CSV 全量验收

### 15.1 当前状态

**BLOCKED：当前机器的项目目录及 `D:\projects_medical` 范围内均不存在冻结的真实 CSV。**

缺少的输入文件：

```text
Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv
```

冻结的上游标识仅用于确认应提供哪一份文件，不能代替重新运行：

| 项目 | 上游已记录值 |
|---|---|
| 文件大小 | 832,373,138 bytes |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| 记录数 | 2,101,588 |
| 年份范围 | 全部为 2021 |
| 主诊断描述缺失 | 1,634 |
| LOS `120 +` | 1,561 |

这些数值来自 `docs/01-data-and-feasibility.md`、`evidence/39/README.md` 等既有上游证据。既有 evidence 只保存旧任务 stdout，没有真实 CSV，也没有包含 #71 七项指标的当前完整快照，因此不能据此把第九步标为 PASS。

### 15.2 已完成的阻塞排查

- 已递归检查当前仓库中的 CSV：只有 fixture 和 Python 依赖自带测试数据。
- 已在 `D:\projects_medical` 下按冻结的精确文件名查找：未找到。
- 已检查 `evidence/`：只有真实运行摘要、模块核对 stdout 和发布摘要，没有可供 #71 标准库重新计算的原始 CSV。
- 未扫描整个磁盘或个人目录，避免越过任务范围和暴露个人文件。

### 15.3 解除阻塞所需输入

将上述真实 CSV 放在 Git 仓库之外的本地路径，并把该路径仅作为命令行 `--input` 参数传入。不得把真实 CSV、个人绝对路径或敏感数据提交到 Git。

取得输入后必须重新执行：

1. 核对文件名、大小和 SHA-256；
2. 使用当前 `run_full_analytics_pyspark.py` 生成 `.tmp/issue-71/real-snapshot.json`；
3. 确认唯一 `data_quality / summary`、真实 `data_version` 和 PySpark `PASS`；
4. 使用 `verify_data_quality_snapshot.py` 对七项指标做标准库独立核对；
5. 确认核对器退出码为 0，且工件未保存个人绝对路径；
6. 将实际七项指标和执行证据补充到本节，才能把状态改为 PASS。

第九步状态：**BLOCKED（缺少冻结版本的真实 CSV）**。fixture 与历史 stdout 均不替代本步骤。
