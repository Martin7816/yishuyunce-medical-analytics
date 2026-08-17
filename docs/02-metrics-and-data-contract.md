# 疾病病例量 TOP10 指标与数据契约

> 文档版本：V1.1
> 更新日期：2026-08-17
> 状态：`FROZEN`（Issue #7、#9）
> 适用范围：M1“疾病病例量 TOP10”真实数据闭环

本文是数据任务、服务结果、API、页面和独立核对共同使用的唯一 TOP10 口径与字段契约。后续联调只修正文档、代码或测试中的错误；如果要改变统计范围、清洗方式、去重方式、排序规则或服务结果结构，必须先更新 Issue 并说明对下游结果的影响。

## 1. 已冻结的指标定义

指标标识为 `disease_case_count_top10`。在约定的数据版本内，对 2021 年 SPARCS 住院出院记录按 `CCSR Diagnosis Description` 分组，清洗后每条有效住院出院记录计数一次，按病例量降序、同量时按疾病名称升序排列，取前 10 项。

这里的“病例量”严格表示**有效住院出院记录数**，不是患者人数、唯一患者数或患病人数。数据没有患者唯一 ID，不能据此做跨次住院追踪。

| 项目 | 冻结规则 |
|---|---|
| 数据范围 | 老师提供的 2021 年 SPARCS 住院出院 CSV；正式统计条件为 `Discharge Year` 去除首尾空白后等于整数 `2021` |
| 分组字段 | 原始字段 `CCSR Diagnosis Description`；`CCSR Diagnosis Code` 只用于追溯，不参与分组和合并 |
| 一行的含义 | 一条住院出院记录；每条符合条件且有非空诊断描述的记录计数一次 |
| 有效诊断 | 诊断描述清洗后为非空字符串的记录 |
| 缺失/空白诊断 | 缺失值、空字符串和只含首尾空白的字符串清洗为空，不进入排行；原始行仍计入输入质量统计 |
| 其他字段异常 | `Length of Stay`、`Zip Code - 3 digits`、`Birth Weight` 等不参与本指标；其特殊值不导致该记录因本指标被删除 |
| 结构异常行 | CSV 行无法按表头解析时，数据任务应失败且不发布部分结果；当前固定样本和正式数据基线均为 0 行 |
| 重复处理 | 不去重。相同诊断描述自然合并计数；即使整行重复，也按两条住院出院记录计数 |
| 文本处理 | 只清理首尾空白；保留大小写、内部空白、标点、括号和原始措辞，不做语义改写、同义词合并或代码映射 |
| 排序 | `case_count` 降序；并列时 `diagnosis_name` 按 UTF-8/Unicode 二进制字典序升序 |
| 截断 | 完成全量分组和稳定排序后取前 10 项；少于 10 项时返回全部；第 10 名并列时仍严格返回 10 项，不扩展为所有并列项 |

### 1.1 数据范围与版本

本次冻结的真实数据版本不使用个人绝对路径标识，而使用来源文件名、大小和 SHA-256 指纹共同确定：

| 项目 | 值 |
|---|---|
| 来源文件名 | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 文件大小 | `832373138` bytes |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| 项目版本标识 | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| 全量核验结果 | 2,101,588 行，CSV 解析异常 0 行，`Discharge Year` 全部为 2021 |

数据任务必须在运行前记录实际 `data_version`。如果文件名、大小或 SHA-256 任一项不同，就视为新的数据版本，不能沿用旧版本的服务结果或 TOP10 数值。固定脱敏样本另标记为 `fixture:sparcs_mvp_sample:v1`，只用于逻辑核对，不代表全量分布。

显式保留 `Discharge Year=2021` 条件，是为了让任务在以后输入混入其他年份时仍保持统计范围稳定；本次真实文件全量核验恰好全部为 2021。缺失或其他年份的记录不计入本指标，并应在数据质量输出中记录数量。

## 2. 从原始字段到服务结果

只保留支持本指标所必需的字段，不为后续医院、费用、住院时长或 AI 功能提前建设宽表。原始 CSV 上传到 HDFS 原始层后作为只读事实使用；完整 CSV、个人绝对路径、密码、Token 和大型中间结果不得进入 Git。固定样例是从真实文件抽取的可提交验证材料，不能替代全量数据。

### 2.1 原始字段与逻辑清洗记录

| 层级 | 原始字段 | 内部字段 | 类型/空值 | 处理和用途 |
|---|---|---|---|---|
| 原始输入 | `Discharge Year` | `discharge_year` | 原始文本；清洗后 `INT`，有效记录不可空 | 去首尾空白后必须等于 `2021`；缺失或其他年份计入质量统计，不进入本指标 |
| 原始输入 | `CCSR Diagnosis Description` | `diagnosis_name` | 原始文本可空；清洗后非空字符串 | 只清理首尾 Unicode 空白；作为唯一分组来源；空值/空白记录排除 |
| 原始输入 | `CCSR Diagnosis Code` | `diagnosis_code` | 文本，可空 | 仅用于追溯和质量核对，不参与分组、合并或展示 |
| 逻辑清洗记录 | — | `diagnosis_name` | `STRING NOT NULL` | 清洗后仍为空的记录不生成清洗记录；不做大小写折叠、同义词合并或代码映射 |
| 逻辑清洗记录 | — | `diagnosis_code` | `STRING NULL` | 原值保留；代码缺失不删除诊断记录 |

“逻辑清洗记录”是 Spark 任务内部的最小数据形状，不单独创建 MySQL 明细表，也不把清洗后的住院明细提交 Git。CSV 行列数无法按表头解析时任务直接失败，不生成部分清洗结果；诊断名称超过服务表允许长度或无法编码时同样失败，不静默截断。

### 2.2 聚合结果与服务结果

| 层级 | 字段 | 类型/约束 | 用途 |
|---|---|---|---|
| 聚合结果 | `diagnosis_name` | `STRING NOT NULL`，同一版本内唯一 | 清洗后的分组键 |
| 聚合结果 | `case_count` | `BIGINT NOT NULL`，大于 0 | 有效住院出院记录数 |
| 服务结果 | `rank` | `TINYINT UNSIGNED NOT NULL`，1—10 连续 | 稳定排序后的名次；当前批次主键 |
| 服务结果 | `diagnosis_name` | `VARCHAR(255) NOT NULL`，`utf8mb4_bin` | 页面和 API 的展示名称；同一版本内唯一 |
| 服务结果 | `case_count` | `BIGINT UNSIGNED NOT NULL`，大于 0 | 病例量，单位是住院出院记录数 |
| 服务结果 | `unit` | `VARCHAR(32) NOT NULL`，固定为 `discharge_records` | 明确数量单位 |
| 服务结果 | `data_version` | `VARCHAR(255) NOT NULL`，`ascii_bin` | 输入文件指纹/数据批次标识；同一批次所有行相同 |
| 服务结果 | `generated_at` | `DATETIME(6) NOT NULL`，统一按 UTC 记录 | 本批结果生成时间；同一批次所有行相同 |

M1 的 MySQL 服务表固定为 `disease_case_count_top10_result`，完整 DDL 和刷新模板位于 [`data/sql/001-mvp-disease-top10-service.sql`](../data/sql/001-mvp-disease-top10-service.sql)。表只保存当前已经校验并发布的一个完整批次，不创建历史批次表、原始明细表或重复指标表。这样 API 只需按 `rank ASC` 读取一张小结果表；`PRIMARY KEY(rank)`、`UNIQUE(data_version, rank)` 和 `UNIQUE(data_version, diagnosis_name)` 共同保证当前结果不会混入重复名次、重复名称或多个版本。

第一轮服务结果明确不包含患者 ID、患者数、原始住院明细、诊断代码、医院维度、费用/成本、住院时长、年龄性别分层、分类模型标签或 AI 字段；`diagnosis_code` 只在清洗过程用于追溯，不能被 API 或页面当作结果字段。后续确有验收价值的扩展必须另建 Issue，并说明对当前契约的影响。

后端按以下只读查询读取结果，不在 Route 中重新清洗、分组、排序或回读 HDFS：

```sql
SELECT `rank`, `diagnosis_name`, `case_count`, `unit`, `data_version`, `generated_at`
FROM `disease_case_count_top10_result`
ORDER BY `rank` ASC;
```

后端将结果视为“可用”的条件是：查询得到 1—10 行、`rank` 从 1 连续递增、所有行只有一个 `data_version` 和一个 `generated_at`，且名称唯一、单位为 `discharge_records`。M1 不发布“零个有效诊断”的空批次；若输入没有可排行记录，发布任务失败并保留旧批次（首次发布则保持未初始化），避免后端把“尚未发布”误判为合法空结果。合法空数据状态由 #10 在明确查询场景后单独定义。

## 3. 文本标准化与边界示例

标准化的目标是消除不会改变名称含义的首尾空白，不替业务人员判断不同文本是否为同一疾病。输入文件读取时处理文件开头的 UTF-8 BOM；诊断值只按统一的首尾 Unicode 空白规则清理。非空的零宽字符或其他非空白控制字符不被静默删除、替换或语义解释，应计入质量检查并保持原文，若要另行处理必须新增决策。

| 原始 `CCSR Diagnosis Description` | 清洗结果 | 处理 |
|---|---|---|
| 缺失值 | 空 | 排除，不计入 TOP10 |
| `""` | 空 | 排除，不计入 TOP10 |
| `"   "` | 空 | 排除，不计入 TOP10；这是规则样例，不宣称真实全量中存在该值 |
| `" LIVEBORN "` | `LIVEBORN` | 与清洗后的 `LIVEBORN` 合并计数 |
| `liveborn` | `liveborn` | 因不做大小写折叠，与 `LIVEBORN` 保持不同名称 |
| `CORONAVIRUS DISEASE 2019 (COVID-19)` | 原样保留 | 不改写括号、连字符或疾病描述 |

首尾空白清理必须在本机 PySpark 正式任务、独立核对和后续服务结果生成中使用同一语义；不能由 API 或前端重新猜测。

## 4. 重复、并列与 TOP10 边界

重复行不删除的业务依据是：一行只代表一次住院出院记录，当前没有患者唯一 ID，也没有经过确认的业务规则可以判断两行是同一次事件。相同诊断描述的多行应累计为病例量。固定样本中两行 `COMPLICATION OF OTHER SURGICAL OR MEDICAL CARE, INJURY, INITIAL ENCOUNTER` 得到 `case_count=2`，两行 `LIVEBORN` 也得到 `case_count=2`，不是重复删除后的 1。

先对所有非空分组完成计数，再按以下复合键排序：

```text
(-case_count, diagnosis_name)
```

因此并列时按名称升序确定名次，名次在截断前生成。固定样本有 12 个非空诊断值，3 个值的病例量为 2；前 10 项中的病例量为 1 的名称继续按名称升序排列，`PREVIOUS C-SECTION` 和 `URINARY TRACT INFECTIONS` 因位于第 10 项之后被截断。这个边界是“严格前 10”，不是“并列全部返回”。

固定样本的独立期望结果保存在 [`data/fixtures/sparcs_mvp_expected_top10.json`](../data/fixtures/sparcs_mvp_expected_top10.json)，当前结果为：

| 排名 | `diagnosis_name` | `case_count` |
|---:|---|---:|
| 1 | COMPLICATION OF OTHER SURGICAL OR MEDICAL CARE, INJURY, INITIAL ENCOUNTER | 2 |
| 2 | LIVEBORN | 2 |
| 3 | TRAUMATIC BRAIN INJURY (TBI); CONCUSSION, INITIAL ENCOUNTER | 2 |
| 4 | ACUTE MYOCARDIAL INFARCTION | 1 |
| 5 | ASTHMA | 1 |
| 6 | CORONAVIRUS DISEASE 2019 (COVID-19) | 1 |
| 7 | DIABETES MELLITUS WITH COMPLICATION | 1 |
| 8 | MULTIPLE SCLEROSIS | 1 |
| 9 | NONINFECTIOUS GASTROENTERITIS | 1 |
| 10 | PARALYSIS (OTHER THAN CEREBRAL PALSY) | 1 |

## 5. 固定样例映射与刷新约定

### 5.1 raw → cleaned → aggregate → service result

固定样例使用 `fixture:sparcs_mvp_sample:v1` 作为 `data_version`，服务结果的 `generated_at` 只用于固定契约验证；真实任务运行时必须生成新的 UTC 时间，不得把样例时间写入全量结果。完整的服务结果期望值保存在 [`data/fixtures/sparcs_mvp_expected_top10.json`](../data/fixtures/sparcs_mvp_expected_top10.json) 的 `service_result` 节点。

| 输入或情况 | 清洗结果 | 聚合结果 | 服务结果处理 |
|---|---|---|---|
| `CCSR Diagnosis Description = " LIVEBORN "` | `diagnosis_name = "LIVEBORN"` | 与其他 `LIVEBORN` 记录合并计数 | 按稳定排序生成一个名称和一个 `rank` |
| 诊断值为空、空字符串或全是空白 | 不生成清洗记录 | 不进入分组；原始行计入质量统计 | 不出现在服务表 |
| 两行名称相同（包括样例中的重复记录） | 两条有效清洗记录 | 合并为 `case_count = 2`，不去重 | 只保留一个疾病名称行，数量为 2 |
| 诊断名称超过 `VARCHAR(255)` 或含无法编码内容 | 不截断、不替换 | 当前任务失败 | 不刷新服务表，保留旧批次 |
| 第 10 名出现并列 | 全量分组后按 `(-case_count, diagnosis_name)` 排序 | 先确定稳定名次 | 严格取前 10 行，不扩展并列项 |

### 5.2 当前批次刷新

服务结果发布程序必须先在 Spark/HDFS 侧生成并核验完整候选结果，再进入 MySQL。候选结果至少要满足：行数 1—10、`rank` 连续、名称唯一、数量为正整数、排序正确；所有行使用同一个 `data_version`、`generated_at` 和 `unit`。之后按 [`data/sql/001-mvp-disease-top10-service.sql`](../data/sql/001-mvp-disease-top10-service.sql) 的模板执行：

1. `START TRANSACTION`；
2. 删除当前已提交结果；
3. 一次性插入候选批次的全部行；
4. 在事务内检查行数、连续排名、单一版本和单一生成时间；
5. 全部通过才 `COMMIT`，任何异常、约束冲突或数量不一致都 `ROLLBACK`。

InnoDB 的事务可见性保证 API 不会读到删除后、插入前的半批数据；刷新失败时旧批次继续可读。成功刷新后只保留新当前批次，重复发布同一个 `data_version` 的结果仍得到同样的当前表内容，因此刷新是幂等的。数据版本变化时不得把新旧行混插，也不能沿用旧版本的服务结果。

M1 不保留历史批次和原始明细；如果后续确实需要审计历史，再单独提出范围变更 Issue，不在本轮提前增加表和字段。

## 6. 可复查证据

固定样本来自同一份真实 CSV 的脱敏字段子集，包含 16 行、1 条缺失诊断、15 条非空诊断、12 个非空诊断值，以及重复分组、并列和其他字段特殊值。它不含完整原始数据，也不能替代全量结果。

在仓库根目录执行：

```powershell
python data/src/verify_sparcs_mvp.py
```

应得到 `status=PASS`，并同时通过独立计数、侦察脚本、固定期望结果和规则边界示例。随后执行服务结果契约检查：

```powershell
python data/src/verify_service_result_contract.py
```

该命令重新读取固定样例，独立生成 TOP10，再检查服务结果的字段集合、类型、排名连续性、排序、单位、版本一致性和生成时间一致性，应得到 `status=PASS`。因此固定样例不是只检查“算出了什么”，还检查“后端将读取什么”。

拥有本地完整 CSV 时，再执行：

```powershell
python data/src/verify_sparcs_mvp.py --full-source "<本地 SPARCS CSV 路径>"
```

全量核对基线是 2,101,588 行、0 条解析异常、2,099,954 条非空诊断记录、477 个非空诊断值，TOP10 与 `docs/01-data-and-feasibility.md` 第 4 节一致。核对脚本只读本地文件，不把完整数据写入仓库。

## 7. 对下游的交接

- **#9 数据表与字段契约**：使用 `disease_case_count_top10_result` 及其 DDL；按当前批次事务刷新，保存 `data_version` 和 `generated_at`，失败时不得发布半成品。
- **#10 API 契约**：见 [`docs/05-api.md`](05-api.md)；只查询已经生成的服务结果，沿用 `rank`、`diagnosis_name`、`case_count`、`unit`、`data_version` 和必要的批次元数据；Route 不复制清洗、聚合或另一套排序。
- **#11 页面原型**：病例量显示为住院出院记录数；名称、排名和数量按服务结果顺序展示，不能写成患者人数。
- **#13 端到端验收**：用固定样本和全量版本分别核对数据任务、服务结果、API 和图表；任何一层出现不同排序或数量都按公共契约问题处理。

本 Issue 只冻结疾病病例量 TOP10，不新增医院、费用、住院时长、分类模型、AI 指标或患者级分析。
