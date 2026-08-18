# M1 疾病病例量 TOP10 测试与验收

> 文档版本：V0.2
> 更新日期：2026-08-18
> 状态：`EXECUTING`（L1/L2 与 API 正常路径已有真实证据；页面四态与端到端仍 BLOCKED；未宣布 M1 通过、未宣布 #10 FROZEN）
> 关联 Issue：#13（准备 M1 TOP10 验收方案与证据框架，先于 #10 的并行任务）、#26（补全并执行 M1 TOP10 全链路验收，进行中）
> 适用范围：M1“疾病病例量 TOP10”真实数据闭环的验收执行、独立核对、问题复验与证据整理
> 单一入口：本文是岗位5（结果核对、系统质量与端到端验收）后续 M1 验收的唯一正式入口，不再另建重复的验收文档

本文冻结的是**验收方法、用例模板、证据规范和状态边界**，不是 TOP10 口径本身。指标口径、数据范围、清洗规则、排序与截断、服务结果字段契约均已在上游冻结，本文只引用，不重写：

- 指标与数据契约：[02-metrics-and-data-contract.md](02-metrics-and-data-contract.md)（`FROZEN`，Issue #7、#9）
- 数据与可行性：[01-data-and-feasibility.md](01-data-and-feasibility.md)（`VERIFIED`）
- 架构与环境边界：[03-architecture-and-env.md](03-architecture-and-env.md)（`DECIDED`）
- 开发、运行与组长电脑复现手册：[04-development-and-runbook.md](04-development-and-runbook.md)

## 1. 文档目的与当前状态

### 1.1 目的

1. 为岗位5的 M1 验收固定统一的执行顺序、用例结构、证据规范和复验流程；
2. 在 Issue #10 正式 API 契约冻结前，先把不依赖 API 的验收准备工作全部就位；
3. 把仍等待 #10（以及 #11、下游数据任务）的内容集中登记，冻结后只补空位，不重写整篇文档。

### 1.2 当前阶段：验收执行中（API 正常路径已验，页面与端到端未开始）

| 层 | 上游状态 | 本 Issue 可做 | 本 Issue 不可做 |
|---|---|---|---|
| 口径与契约 | `FROZEN`（#7、#9） | 引用为用例预期 | 修改或另写一套口径 |
| 固定样本与独立核对 | `VERIFIED` | 复验、填写证据 | 修改 fixture 或核对脚本 |
| 数据任务与服务结果 | 全量两次复跑、MySQL 实表与回滚演练 `VERIFIED`（#31） | 填写 DT 用例实际结果与证据来源 | 宣称 MySQL/API 全链路完成 |
| Flask API | 契约 `CONFIRMED`（#10）；真实正常路径 `VERIFIED`（#31） | 按 [05-api.md](05-api.md) 回填 API 用例（标注来源 #10 CONFIRMED） | 宣布 #10 FROZEN；宣称 API 四类全部通过 |
| Vue/ECharts 页面 | `HANDOFF`（待 #11） | 预置四态与检查项模板 | 填写页面触发方式 |
| 全链路与组长电脑复现 | `HANDOFF`（待相关实现落位后由 Issue #26 执行） | 预置比较链与 checklist | 宣称 M1 PASS |

### 1.3 当前禁止宣布的结论

- 不宣布“API 已通过”——Issue #10 正式 API 契约尚未完成；
- 不宣布“页面已通过”——Issue #11 页面实现尚未完成；
- 不宣布“M1 全链路已通过”——最终全链路验收在后续 Issue #26 执行；
- 固定样本 `PASS` 不等于真实全链路通过证据；Mock 结果不等于正式验收证据；
- RAW/侦察结果不是另一套正式业务口径，只作为与正式任务对比的基线（[01 第 4、8 节](01-data-and-feasibility.md)）。

### 1.4 当前已确认的事实（截至 2026-08-18）

| 项目 | 状态 | 依据 |
|---|---|---|
| 固定样本独立核对脚本 | `PASS`（本 Issue 复验，退出码 0） | [01 第 7 节](01-data-and-feasibility.md)、本文第 3 章 |
| 服务结果契约检查脚本 | `PASS`（本 Issue 复验，退出码 0） | [02 第 6 节](02-metrics-and-data-contract.md)、本文第 4 章 |
| 本机 PySpark 固定样例 | `VERIFIED`（#12 实测记录） | [04 第 7.1 节](04-development-and-runbook.md) |
| 本机 PySpark 全量任务 | `VERIFIED`（2026-08-18） | [04 第 4.1 节](04-development-and-runbook.md) |
| MySQL 业务结果实际装载 | `VERIFIED`（#31：`--apply` 提交 10 行、逐行查询一致、1264 回滚保留旧批次） | [03 第 9 节](03-architecture-and-env.md)、[04 第 7.1 节](04-development-and-runbook.md)、#31 Resolution |
| Flask API | `VERIFIED`（#31 真实 HTTP 200、10 项；契约状态 #10 `CONFIRMED`，FROZEN 待 #10） | [05-api.md](05-api.md)、#31 Resolution |
| Vue/ECharts 页面 | `BLOCKED`（待 #11/#25） | [03 第 3 节](03-architecture-and-env.md) |
| M1 全链路一致性 | `BLOCKED`（页面与端到端未完成；#26 进行中） | 本文第 1.3 节 |

## 2. 验收执行顺序

验收按以下五层顺序推进；上层被阻断时不宣布其上游层“对下游已生效”，但已独立完成的层可以单独记录结果。

| 层 | 名称 | 内容 | 主要依据 | 当前状态 |
|---|---|---|---|---|
| L1 | 数据与固定样本 | 固定样本独立核对、全量基线核对 | [01](01-data-and-feasibility.md) 第 6、7 节 | `PASS`（固定样本与全量基线） |
| L2 | 数据任务与服务结果 | PySpark 清洗聚合、服务结果契约、MySQL 事务装载 | [02](02-metrics-and-data-contract.md) | 全量两次复跑、服务结果契约、MySQL 实表与回滚演练 `PASS`（#31） |
| L3 | Flask API | 只读查询服务结果、四类响应语义 | [05-api.md](05-api.md)（#10 `CONFIRMED`） | API-01 真实数据 `PASS`（#31/#26）；API-02~04 契约与自动化测试已回填，真实 HTTP 证据待采集（`PENDING_HTTP_EVIDENCE`） |
| L4 | Vue/ECharts 页面 | 四态、展示一致性与交互检查 | #11 实现后执行 | `BLOCKED`（待 #11） |
| L5 | 端到端集成与组长电脑复现 | 全链路一致性比较、组长电脑 checklist | 本文第 7、8 章 | `BLOCKED`（待相关实现落位后由 Issue #26 执行） |

执行规则：

1. 每层验收只使用上一层已经确认的输出作为输入，不使用 Mock 或前端写死数据充当上层结果；
2. 每层完成时填写该层用例表中的“实际结果”“证据”“状态”，并记录测试时间；
3. 层与层之间任何名称、排名、数量、单位或 `data_version` 不一致，都按公共契约问题记录（模板见第 10 章）；
4. M1 整体只有在 L1—L5 全部通过且证据归档后才可宣布 PASS（由 #26 执行）。

## 3. 固定样本与独立核对

### 3.1 涉及的真实仓库文件

| 文件 | 作用 |
|---|---|
| `data/fixtures/sparcs_mvp_sample.csv` | 固定脱敏样本：16 条记录、12 个字段，来自同一份真实 2021 SPARCS CSV |
| `data/fixtures/sparcs_mvp_expected_top10.json` | 独立期望结果：样本摘要、样本 TOP10、服务结果期望节点、全量基线 |
| `data/src/verify_sparcs_mvp.py` | Python 标准库独立计数 + 调用侦察脚本对拍 + 契约边界样例 |
| `data/src/verify_service_result_contract.py` | 从样本独立重算 TOP10，也可核对 PySpark 服务结果工件（不连接 MySQL） |
| `data/src/publish_top10_mysql.py` | 校验小型服务结果工件，并在显式 `--apply` 时事务替换 MySQL 当前批次 |

样本事实（从 [01 第 6 节](01-data-and-feasibility.md)与 fixture 文件读取）：

- 数据行数 16；包含 1 条空诊断记录；
- 非空诊断记录 15 条；非空诊断值 12 个；
- 特殊值覆盖：`Length of Stay=120 +`、`Zip Code - 3 digits=OOS`、`Birth Weight=UNKN`；
- 样本 `data_version` 固定为 `fixture:sparcs_mvp_sample:v1`，只用于逻辑核对，不代表全量分布。

### 3.2 输入、执行命令与预期结果

输入：仓库内的固定样本与期望 JSON（默认路径，无需任何本地完整 CSV 或 VM）。

在仓库根目录执行：

```powershell
python data/src/verify_sparcs_mvp.py
python data/src/verify_service_result_contract.py
```

预期结果：

- 两个脚本均退出码 0；
- `verify_sparcs_mvp.py` 顶层 `"status": "PASS"`，并报告：
  `rows=16`、`malformed_rows=0`、`out_of_scope_rows=0`、
  `diagnosis_nonempty_rows=15`、`diagnosis_nonempty_distinct=12`，
  样本 TOP10 与期望 JSON 完全一致，契约边界样例 `PASS`；
- `verify_service_result_contract.py` 顶层 `"status": "PASS"`，
  `data_version=fixture:sparcs_mvp_sample:v1`、`rows=10`、`unit=discharge_records`。

固定样本期望 TOP10（从 `data/fixtures/sparcs_mvp_expected_top10.json` 的 `sample.top10` 读取）：

| 排名 | 主诊断描述 | 病例量（住院出院记录数） |
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

### 3.3 实际结果填写位置与本次复验记录

| 用例编号 | 检查目标 | 输入/前置条件 | 操作步骤 | 预期结果 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|
| L1-01 | 固定样本独立核对 | 仓库默认 fixture 路径；Python 标准库可用 | 仓库根目录执行 `python data/src/verify_sparcs_mvp.py` | 退出码 0，`status=PASS`，计数摘要与期望一致 | 2026-08-17 复验 PASS；2026-08-18 #26 本轮复验：退出码 0，`status=PASS`，`rows=16`、`malformed_rows=0`、`out_of_scope_rows=0`、`diagnosis_nonempty_rows=15`、`diagnosis_nonempty_distinct=12`，TOP10 与期望一致，契约边界样例 PASS（7 个输入值、3 个分组） | 本机脚本 stdout（JSON）；待归档 `evidence/26/l1-fixture/L1-01/`（本轮未创建） | `PASS` |
| L1-02 | 服务结果契约检查 | 同上 | 仓库根目录执行 `python data/src/verify_service_result_contract.py` | 退出码 0，`status=PASS`，`rows=10`、`unit=discharge_records` | 2026-08-17 复验 PASS；2026-08-18 #26 本轮复验：退出码 0，`status=PASS`，`data_version=fixture:sparcs_mvp_sample:v1`、`rows=10`、`unit=discharge_records` | 本机脚本 stdout（JSON）；待归档 `evidence/26/l1-fixture/L1-02/`（本轮未创建） | `PASS` |
| L1-03 | 全量基线核对（有完整 CSV 时） | 本地完整 2021 SPARCS CSV（路径只作命令行参数，不写入仓库） | 执行 `python data/src/verify_sparcs_mvp.py --full-source "<本地 SPARCS CSV 路径>"` | 2,101,588 行、0 解析异常、2,099,954 条非空诊断记录、477 个非空诊断值，TOP10 与 [01 第 4 节](01-data-and-feasibility.md) 基线一致 | 2026-08-18：完整文件 SHA-256 与 [02 第 1.1 节](02-metrics-and-data-contract.md) 一致，独立核对 `PASS` | 本地命令 stdout（未提交原始文件）；待归档 `evidence/26/l1-full/L1-03/`（本轮未创建） | `PASS` |

说明：

- L1-01/L1-02 的实际结果为本 Issue 在 2026-08-17 的只读复验，仅确认“固定样本可复查”，不是 M1 通过证据；
- 复验失败时不安装新依赖、不修改环境、不修改上游脚本或 fixture，如实记录失败原因并上报；
- 全量基线只适用于文件名、大小与 SHA-256 均与 [02 第 1.1 节](02-metrics-and-data-contract.md) 一致的原始文件。

## 4. 数据任务 / 服务结果验收模板

本章覆盖本机 PySpark 正式数据任务、服务结果发布与 MySQL 装载。统一用例结构：

| 用例编号 | 检查目标 | 输入/前置条件 | 操作步骤 | 预期结果 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|

口径与清洗用例：

| 用例编号 | 检查目标 | 输入/前置条件 | 操作步骤 | 预期结果 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|
| DT-01 | 统计口径一致 | 任务实际输入 CSV | 核对数据任务是否按“`Discharge Year` 去首尾空白后等于 `2021`”筛选 | 非 2021 记录不计入本指标，并计入质量统计（`out_of_scope_rows`） | 实现核对：任务按 `trim(Discharge Year)=2021` 过滤（`data/src/run_sparcs_top10_pyspark.py`）；#31 真实全量两次复跑 `out_of_scope_rows=0`（输入文件全部为 2021） | Issue #31 评论与 Resolution、PR #32/#33；待归档 `evidence/26/l2-data/DT-01/`（本轮未创建） | `PASS` |
| DT-02 | 分组字段一致 | 任务实现与日志 | 核对只按 `CCSR Diagnosis Description` 分组；`CCSR Diagnosis Code` 只用于追溯 | 分组维度唯一；代码字段不参与分组、合并与展示 | 实现核对：只按清洗后的诊断描述 `groupBy("diagnosis")` 分组，代码字段未进入分组、合并与展示（`data/src/run_sparcs_top10_pyspark.py`） | 源码核对；待归档 `evidence/26/l2-data/DT-02/`（本轮未创建） | `PASS` |
| DT-03 | 清洗规则一致 | 任务实现 | 核对只清理诊断名称首尾空白 | 保留大小写、内部空白、标点、括号；不做大小写折叠、同义词合并或代码映射（对照 [02 第 3 节](02-metrics-and-data-contract.md) 示例） | 实现核对：仅 `regexp_replace` 清理首尾 Unicode 空白（`data/src/run_sparcs_top10_pyspark.py`）；L1-01 契约边界样例 PASS（7 个输入值、3 个分组：` LIVEBORN ` 合并、`liveborn` 不折叠、重复计数，见 `verify_sparcs_mvp.py`）；`CORONAVIRUS DISEASE 2019 (COVID-19)` 保留原样由 L1-01 样本 TOP10 逐字符核对与 [02 第 3 节](02-metrics-and-data-contract.md) 示例共同支持 | L1-01 stdout（2026-08-18 复验）；待归档 `evidence/26/l2-data/DT-03/`（本轮未创建） | `PASS` |
| DT-04 | 空诊断排除 | 任务实现与输出 | 核对缺失、空字符串、全空白诊断的处置 | 清洗后为空的不进入排行；原始行仍计入输入质量统计 | 实现核对：清洗后长度为 0 的诊断被过滤（`length(diagnosis)>0`）；#31 真实全量 2,101,588 行中 `malformed_rows=0`、2,099,954 条非空诊断记录、477 个诊断分组 | Issue #31 Resolution、[04 第 4.1 节](04-development-and-runbook.md)；待归档 `evidence/26/l2-data/DT-04/`（本轮未创建） | `PASS` |
| DT-05 | 不去重 | 任务实现 | 用含重复诊断（样例中 `COMPLICATION …`、`LIVEBORN` 各 2 条）核对计数 | 相同诊断自然合并计数；即使整行重复也按两条住院出院记录计数 | 固定样例两重复诊断各计 2（L1-01）；实现无 distinct/dropDuplicates，仅 `groupBy(...).count()`；#31 真实全量两次复跑 TOP10 完全一致 | L1-01 stdout、Issue #31 Resolution；待归档 `evidence/26/l2-data/DT-05/`（本轮未创建） | `PASS` |
| DT-06 | 排序与并列一致 | 任务输出 | 核对复合键 `(-case_count, diagnosis_name)` | `case_count` 降序；并列时 `diagnosis_name` 按 UTF-8/Unicode 二进制字典序升序 | 实现核对：`orderBy(desc(case_count), asc(diagnosis))`；#31 全量工件通过 `verify_service_result_contract.py --expected-scope full_scan` 的排序校验；固定样例并列 3 项按名称升序（L1-01） | Issue #31 Resolution、契约脚本 stdout；待归档 `evidence/26/l2-data/DT-06/`（本轮未创建） | `PASS` |
| DT-07 | 严格 TOP10 | 任务输出 | 核对截断发生在全量稳定排序之后 | 严格返回前 10 项；少于 10 项返回全部；第 10 名并列不扩展（对照 [02 第 4 节](02-metrics-and-data-contract.md)） | 实现核对：稳定排序后 `limit(10)`；固定样例第 10 名并列项 `PREVIOUS C-SECTION`、`URINARY TRACT INFECTIONS` 被截断（L1-01）；#31 全量服务结果严格 10 行 | L1-01 stdout、Issue #31 Resolution；待归档 `evidence/26/l2-data/DT-07/`（本轮未创建） | `PASS` |
| DT-08 | 结构异常行处理 | 任务输入 | 构造或检查无法按表头解析的 CSV 行场景 | 任务失败且不发布部分结果；正式数据基线为 0 行 | 实现核对：读取模式为 `FAILFAST`，解析异常即任务失败、不生成部分结果；#31 正式全量 `malformed_rows=0`（基线 0 行） | 源码核对、Issue #31 Resolution；待归档 `evidence/26/l2-data/DT-08/`（本轮未创建） | `PASS`（实现核对 + 正式基线 0 行） |
| DT-09 | 超长/不可编码诊断名 | 任务实现 | 检查对超过 `VARCHAR(255)` 或无法编码名称的处理 | 不截断、不替换，任务失败，不刷新服务表 | 实现核对：发布器与后端服务对超过 255 字符的名称直接失败、不截断、不替换（`publish_top10_mysql.py` 发布器校验、`backend/app/services/disease_top10.py` API 侧校验）；真实全量 TOP10 中最长名称为 `SCHIZOPHRENIA SPECTRUM AND OTHER PSYCHOTIC DISORDERS`，实际长度 52 字符，≤255，未触发长名称失败路径（不声称它是全部 477 个分组名称中的最长项） | 源码核对；待归档 `evidence/26/l2-data/DT-09/`（本轮未创建） | `PASS`（实现核对；真实数据未出现超长值，未做故障注入） |
| DT-10 | 重复执行结果一致 | 同一输入文件 | 同一输入重复运行任务两次以上 | 每次得到相同 TOP10 与计数摘要；刷新幂等（重复发布同一 `data_version` 结果一致） | 固定样例多次复验一致（L1-01/L1-02）；#31 真实全量两次复跑：`service_result`、TOP10 与输入指纹（文件名+大小+SHA-256）完全一致，`data_version=sparcs_2021_20231012_sha256_185808e2…` | Issue #31 评论与 Resolution、[04 第 7.1 节](04-development-and-runbook.md)；待归档 `evidence/26/l2-data/DT-10/`（本轮未创建） | `PASS` |

服务结果与发布用例：

| 用例编号 | 检查目标 | 输入/前置条件 | 操作步骤 | 预期结果 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|
| DT-11 | 服务结果字段契约 | 结果工件或 MySQL 表 | 核对字段集合与类型：`rank` TINYINT UNSIGNED 1—10 连续、`diagnosis_name` VARCHAR(255) utf8mb4_bin 非空且批内唯一、`case_count` BIGINT UNSIGNED 大于 0、`unit` 固定 `discharge_records`、`data_version`/`generated_at` 见 DT-12/DT-14（DDL 见 `data/sql/001-mvp-disease-top10-service.sql`） | 与 [02 第 2.2 节](02-metrics-and-data-contract.md) 完全一致；不包含患者 ID、诊断代码、明细等字段 | 固定样本契约检查 PASS（L1-02）；#31 全量工件 `verify_service_result_contract.py --result … --expected-scope full_scan` PASS；MySQL 实表逐行查询与工件一致，字段不含患者 ID/诊断代码/明细 | Issue #31 Resolution、契约脚本 stdout；待归档 `evidence/26/l2-mysql/DT-11/`（本轮未创建） | `PASS` |
| DT-12 | `data_version` 一致 | 任务输入指纹 | 核对任务运行前记录的实际 `data_version` 与输入文件指纹（文件名+大小+SHA-256）对应；批内所有行同一值 | 同批行 `data_version` 唯一；版本变化时不混插新旧行、不沿用旧结果 | 固定样本 PASS（L1-02）；#31 真实 `data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` 与指纹对应，两次复跑一致；MySQL 实表 `version_count=1`（来自 `publish_top10_mysql.py` 事务内 `validate_published_rows` 校验，通过后才 COMMIT） | Issue #31 Resolution、发布器事务内校验；#31 提交后验证为逐行查询核对（与工件一致，非独立聚合 COUNT 查询）；待归档 `evidence/26/l2-mysql/DT-12/`（本轮未创建） | `PASS` |
| DT-13 | `unit` 一致 | 服务结果所有行 | 逐行核对 | 所有行 `unit=discharge_records` | 固定样本 PASS（L1-02）；#31 全量工件与 MySQL 实表逐行核对 `unit=discharge_records`（`unit_count=1` 来自 `publish_top10_mysql.py` 事务内 `validate_published_rows` 校验） | Issue #31 Resolution、发布器事务内校验；#31 提交后验证为逐行查询核对（与工件一致，非独立聚合 COUNT 查询）；待归档 `evidence/26/l2-mysql/DT-13/`（本轮未创建） | `PASS` |
| DT-14 | `generated_at` 一致 | 服务结果所有行 | 核对批内所有行同一 `generated_at`（UTC、DATETIME(6)）；真实任务必须生成新时间 | 同批唯一；不得沿用 fixture 的 `2026-08-17T00:00:00Z` | 固定样本 PASS（L1-02）；#31 真实批 `generated_at=2026-08-18T01:36:42.446058Z`（新生成，未沿用 fixture 时间），批内唯一（`generated_at_count=1` 来自 `publish_top10_mysql.py` 事务内 `validate_published_rows` 校验） | Issue #31 Resolution、发布器事务内校验；#31 提交后验证为逐行查询核对（与工件一致，非独立聚合 COUNT 查询）；待归档 `evidence/26/l2-mysql/DT-14/`（本轮未创建） | `PASS` |
| DT-15 | 术语一致：不混淆患者数与记录数 | 任务、服务结果、API、页面文案 | 检查任何层是否出现“患者数/患病人数”表述 | `case_count` 一律表述为住院出院记录数；`unit=discharge_records` 明示单位（术语见 [CONTEXT.md](../CONTEXT.md)） | 数据与 API 层核对：服务结果 `unit=discharge_records` 明示单位；[05-api.md](05-api.md) 与后端错误文案不使用“患者数/患病人数”；页面文案待 #25 页面落位后按 UI-07 核对 | 文档与源码核对；待归档 `evidence/26/l2-data/DT-15/`（本轮未创建） | `PASS`（数据与 API 层；页面层待 #25） |
| DT-16 | 事务刷新与失败保护 | MySQL 8.0.30（hadoop001）已启动；DDL 已执行 | 按 `data/sql/001-mvp-disease-top10-service.sql` 事务模板执行装载，并核对事务内 COUNT/版本/排名检查 | 全部通过才 COMMIT；异常 ROLLBACK 且旧批次继续可读；不发布空批次（0 个有效诊断时任务失败） | #31：`publish_top10_mysql.py --apply` 事务提交 10 行，提交后查询逐行一致；故意写入超出 `BIGINT UNSIGNED` 的值触发 MySQL 1264 → 发布器 ROLLBACK，随后查询仍为 10 行、旧批次完整保留（`rollback_preserved=True`） | Issue #31 评论与 Resolution、[04 第 7.1 节](04-development-and-runbook.md)；待归档 `evidence/26/l2-mysql/DT-16/`（本轮未创建） | `PASS` |
| DT-17 | 服务结果可用性 | MySQL 表内容 | 按 [02 第 2.2 节](02-metrics-and-data-contract.md) 只读查询检查：1—10 行、`rank` 连续、名称唯一、单一 `data_version`、单一 `generated_at`、`unit` 正确 | 满足全部条件才视为“可用”，API 才允许返回 | #31 提交后查询：10 行、`rank` 1—10 连续、名称唯一、单一 `data_version`、单一 `generated_at`、`unit=discharge_records`；随后 #10 真实 API 正常返回该批次（见 API-01） | Issue #31 Resolution；待归档 `evidence/26/l2-mysql/DT-17/`（本轮未创建） | `PASS` |

## 5. API 验收模板

> 前置：Issue #10 正式 API 契约冻结后执行。更新（2026-08-18，#26 第一轮回填）：本章请求构造、预期响应与错误语义已按 [05-api.md](05-api.md) 补入。**来源：Issue #10 `CONFIRMED`；FROZEN 尚待 #10 最终关闭/冻结**。回填不代表契约已冻结，也不代表 #26 第 1 项最终完成。
>
> 状态说明：`PENDING_HTTP_EVIDENCE` 是 #26 期间的中间状态——契约与自动化测试结果已回填，但尚未采集真实 HTTP 请求/响应/状态码证据（#26 第 4 项要求）；采集并通过后改为 `PASS`。
>
> 已冻结的边界：API 只查询已校验的 MySQL 服务结果（`disease_case_count_top10_result`），Route 不重新清洗、分组、排序或回读 HDFS（[02 第 2.2 节](02-metrics-and-data-contract.md)）；MySQL 不可用时返回明确依赖失败、不现场计算（[03 第 7 节](03-architecture-and-env.md)）；响应内容必须与服务结果语义一致（沿用**服务结果字段** `rank`、`diagnosis_name`、`case_count`、`unit`、`data_version` 和必要的批次元数据，见 [02 第 2.2 节](02-metrics-and-data-contract.md)）。API JSON 顶层结构与字段名已由 #10 写入 [05-api.md](05-api.md)（来源：Issue #10 `CONFIRMED`；FROZEN 尚待 #10 最终关闭/冻结）。

| 用例编号 | 类别 | 检查目标 | 前置条件 | 输入/请求构造 | 预期响应 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|---|
| API-01 | 正常结果 | 返回已发布服务结果批次，内容与数值与服务结果一致 | MySQL 已有可用批次（DT-17 通过） | `GET /api/v1/diseases/top10`（无查询参数、无请求体；来源 #10 CONFIRMED） | `200 OK`；统一结构 `code=OK`、`message`、`data`、`trace_id`；`data` 含 `metric=disease_case_count_top10`、`unit=discharge_records`、`data_version`、`generated_at` 与 `items[]`（`rank` 1—10 连续、`diagnosis_name`、`case_count`），与服务结果语义一致（来源 #10 CONFIRMED） | #31 实机：真实 HTTP GET 返回 200、10 项，`data_version=sparcs_2021_20231012_sha256_185808e2…` 与 MySQL 一致（#31/#26 Issue 评论的真实联调记录）；2026-08-18 后端 pytest 12 passed（含成功契约用例） | Issue #31 Resolution、#26 Issue 评论、[05-api.md](05-api.md) 第 4 节；HTTP 响应原文待归档 `evidence/26/l3-api/API-01/`（本轮未创建） | `PASS`（真实数据正常路径；契约来源 #10 CONFIRMED，FROZEN 待 #10） |
| API-02 | 合法空结果 | 合法请求但无可展示结果的语义 | fixture empty 模式启动后端（`TOP10_FIXTURE_STATE=empty`）；生产空表场景见预期列 | `GET /api/v1/diseases/top10`（来源 #10 CONFIRMED） | 合法空快照：`200 OK` 且 `data.items=[]`，批次元数据（`unit`、`data_version`、`generated_at`）仍存在；生产 MySQL 空表表示“尚未发布”，返回 `503 RESULT_NOT_READY`，不误判为空数据（来源 #10 CONFIRMED） | 契约来源 [05-api.md](05-api.md) 第 6、7 节；后端 pytest `test_legal_empty_snapshot_returns_empty_items`、`test_unpublished_result_is_not_misreported_as_empty` 通过；真实 HTTP 空态请求与生产空表场景尚未采集 | pytest 输出（2026-08-18）；待归档 `evidence/26/l3-api/API-02/`（本轮未创建） | `PENDING_HTTP_EVIDENCE`（契约与自动化测试已回填，真实 HTTP 证据待采集） |
| API-03 | 非法参数 | 参数缺失、类型错误、越界等的统一错误语义 | 该端点不接受任何查询参数与请求体（来源 #10 CONFIRMED） | `GET …?limit=5`；GET 携带请求体；`POST /api/v1/diseases/top10` | 携带任意查询参数 → `400 INVALID_QUERY_PARAMETER`（`details` 列出参数名）；GET 携带请求体 → `400 INVALID_REQUEST_FORMAT`；非 GET 方法 → `405 METHOD_NOT_ALLOWED`；URL 不存在 → `404 RESOURCE_NOT_FOUND`（来源 #10 CONFIRMED） | 契约来源 [05-api.md](05-api.md) 第 2、7 节；后端 pytest `test_query_parameter_is_rejected`、`test_get_body_is_rejected`、`test_wrong_method_uses_json_error` 通过；真实 HTTP 请求/响应原文尚未采集 | pytest 输出（2026-08-18）；待归档 `evidence/26/l3-api/API-03/`（本轮未创建） | `PENDING_HTTP_EVIDENCE`（契约与自动化测试已回填，真实 HTTP 证据待采集） |
| API-04 | 依赖失败 | MySQL 不可用等依赖故障的响应 | 可控地停止 MySQL（仅测试环境；本轮未执行） | 测试注入 Repository 抛出对应错误；真实场景为停止 MySQL 或错误配置 | MySQL 连接/查询失败 → `503 DATABASE_UNAVAILABLE`；结果表为空 → `503 RESULT_NOT_READY`；配置缺失 → `500 SERVER_MISCONFIGURED`；已发布结果违反契约 → `500 SERVICE_RESULT_INVALID`；未预期异常 → `500 INTERNAL_ERROR`；不现场计算、不返回假数据（来源 #10 CONFIRMED） | 契约来源 [05-api.md](05-api.md) 第 7 节；后端 pytest 覆盖上述全部错误码并通过；#31 的 1264 回滚演练属于数据发布侧，不是 API 侧；真实停库 HTTP 演练未执行 | pytest 输出（2026-08-18）；待归档 `evidence/26/l3-api/API-04/`（本轮未创建） | `PENDING_HTTP_EVIDENCE`（契约与自动化测试已回填，真实 HTTP 证据待采集） |

## 6. 页面验收模板

> 前置：Issue #11 页面实现落位后执行。页面触发方法（如何进入各状态、重试入口形态）以 #11 实现为准，未提供前标记“待补”，不猜测。
>
> 已冻结的边界：页面只消费 Flask API，不直连数据库、不重新计算 TOP10、不得写死正式结果（[03 第 2、3 节](03-architecture-and-env.md)）；Mock 只服务并行开发，不能作为真实链路的替代证据。

四态用例：

| 用例编号 | 检查目标 | 前置条件 | 触发方法 | 预期表现 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|
| UI-01 | loading 态 | 页面已按 #11 方式启动（启动命令 `TBD - 待 Issue #11 冻结`） | 待补（#11 实现后填写） | 数据未返回时显示可辨识的加载状态，不显示空白或陈旧数据 | | 页面截图 | `BLOCKED` |
| UI-02 | success 态 | MySQL 已有可用批次且 API 正常返回（前置用例：DT-17、API-01） | 待补（#11 实现后填写） | 展示 API 返回的 TOP10：排名、名称、病例量与单位完整且与服务结果一致 | | 页面截图 + 同刻 API 响应 | `BLOCKED` |
| UI-03 | empty 态 | API 合法空结果语义已由 #10 冻结（前置用例：API-02） | 待补（#11 实现后填写） | 合法空结果时显示明确空状态，不与加载或错误混淆；空结果语义与 API-02 一致 | | 页面截图 | `BLOCKED` |
| UI-04 | error 态 | 可构造 API 依赖失败场景（前置用例：API-04） | 待补（#11 实现后填写） | 依赖失败或请求失败时显示明确错误提示，并提供可触发的重试路径 | | 页面截图 | `BLOCKED` |

展示与一致性用例：

| 用例编号 | 检查目标 | 前置条件 | 操作步骤 | 预期结果 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|
| UI-05 | 排名与顺序 | success 态已通过（UI-02），页面展示真实 API 数据 | 对比页面渲染与服务结果/API 响应 | 排名 1—10 与服务结果完全一致，顺序不重排 | | 截图 + API 响应对比 | `BLOCKED` |
| UI-06 | 主诊断描述 | success 态已通过（UI-02），页面展示真实 API 数据 | 逐项对比页面名称与 API 返回的服务结果名称（`diagnosis_name` 为服务结果字段；API JSON 字段名 `TBD - 待 Issue #10 冻结`） | 名称逐字符一致（含大小写、标点、括号），不截断改写 | | 截图 + API 响应对比 | `BLOCKED` |
| UI-07 | 病例量与单位 | success 态已通过（UI-02），页面展示真实 API 数据 | 逐项对比页面数值与 API 返回的服务结果病例量（`case_count` 为服务结果字段；API JSON 字段名 `TBD - 待 Issue #10 冻结`） | 数值一致；单位信息与服务结果 `unit=discharge_records` 一致；文案不写成“患者数/患病人数” | | 截图 + API 响应对比 | `BLOCKED` |
| UI-08 | 长疾病名称 | success 态已通过（UI-02） | 使用全量基线 TOP10 中最长名称 `SCHIZOPHRENIA SPECTRUM AND OTHER PSYCHOTIC DISORDERS` 核对展示 | 名称完整可辨识，不丢字、不截断（具体呈现方式以 #11 实现为准，验收时逐字符比对） | | 截图 | `BLOCKED` |
| UI-09 | 并列结果 | success 态已通过（UI-02） | 使用固定样本并列项（病例量同为 2 的三项）核对 | 并列项按名称升序展示，顺序与服务结果一致，不出现重名次 | | 截图 | `BLOCKED` |
| UI-10 | 浏览器窗口变化 | success 态已通过（UI-02） | 调整窗口宽度/缩放 | 排名、名称、数量仍可辨识，数据不丢失不重算（具体响应式标准由 #11 实现时补充） | | 截图 | `BLOCKED` |
| UI-11 | 页面不重新计算 TOP10 | 前端源码已随 #11 提交到仓库 | 检查前端源码与网络行为 | 页面只请求 API 并渲染返回结果，无本地分组/排序/截断逻辑，无直连 MySQL | | 源码检查记录 + 网络面板 | `BLOCKED` |
| UI-12 | 页面不用 Mock 冒充正式验收 | 页面处于 success 态；验收环境可访问真实 API | 核对页面请求目标与数据来源 | 正式验收必须指向真实 API 与真实服务结果；Mock 仅验证界面结构，不得作为 UI-05—UI-09 的证据 | | 请求记录 + API 响应 | `BLOCKED` |

## 7. 端到端一致性检查

> 预留比较链，待相关实现落位后由 Issue #26 执行。当前不填写任何通过结论。

比较链：

```text
固定样本 / 真实 CSV（正式输入，含 data_version 指纹）
  → 本机 PySpark 数据任务（唯一正式计算）
  → 服务结果（MySQL 当前批次 / 结果工件）
  → Flask API（只读查询，不重算）
  → Vue/ECharts 页面（只消费 API，不重算）
  → 岗位5独立核对（Python 标准库脚本）
```

一致性矩阵（要求在适用层之间逐项一致）：

| 比较项 | 数据任务工件 | MySQL 服务结果 | Flask API 响应 | 页面显示 | 独立核对 |
|---|---|---|---|---|---|
| `diagnosis_name` 集合与顺序 | 检查 | 检查 | 检查 | 检查 | 检查 |
| `rank` | 适用 | 检查 | 检查 | 检查 | 适用 |
| `case_count` | 检查 | 检查 | 检查 | 检查 | 检查 |
| `unit=discharge_records` | 检查 | 检查 | 检查 | 检查 | 检查 |
| `data_version` | 检查 | 检查 | 检查 | 不适用（展示层面） | 检查 |
| `generated_at` | 检查 | 检查 | 检查 | 不适用 | 不适用 |
| 行数（1—10） | 检查 | 检查 | 检查 | 检查 | 检查 |
| 排序键 `(-case_count, diagnosis_name)` | 检查 | 检查 | 不适用（按 rank 读取） | 不适用（按 rank 渲染） | 检查 |

执行要点：

- API 响应列按**服务结果语义**逐项比较；API 最终 JSON 顶层结构、字段名与类型以 Issue #10 冻结为准（`TBD - 待 Issue #10 冻结`），冻结前不把服务结果字段名当作 API JSON key；
- E2E-01 固定样本链路：以 `fixture:sparcs_mvp_sample:v1` 走通五层比较，任何一层不一致都按公共契约问题记录；
- E2E-02 全量链路：完整 CSV 的文件名、大小、SHA-256 必须与 [02 第 1.1 节](02-metrics-and-data-contract.md) 一致；全量 TOP10 基线见 [01 第 4 节](01-data-and-feasibility.md)（侦察结果与独立核对一致，是核对基线，不是另一套正式口径）；
- 页面层不产生新的数值：页面显示只能来自 API 响应；
- 独立核对是第 6 个比较点，使用标准库脚本，不与 PySpark 任务共用实现。

## 8. 组长电脑复现清单

按 [04-development-and-runbook.md](04-development-and-runbook.md) 逐项执行并勾选；命令尚未存在的步骤不编造，标记 `TBD`。

- [ ] **获取最新 main**
  - [ ] `git clone git@github.com:Martin7816/yishuyunce-medical-analytics.git yishuyunce-medical-analytics`（或更新已有克隆：`git switch main && git pull --ff-only`）
  - [ ] 记录当前 `git rev-parse HEAD` 作为复现基线
- [ ] **环境确认**（命令见 [04 第 2.1 节](04-development-and-runbook.md)）
  - [ ] `git --version`、`python --version`、`node --version`、`npm --version`、`java -version`
  - [ ] `conda activate csupy311`
  - [ ] `python -c "import pyspark; print(pyspark.__version__)"` 输出 `3.4.0`
  - [ ] `Get-Command hdfs,hive,mysql -ErrorAction SilentlyContinue` 无结果为预期边界
- [ ] **配置检查**
  - [ ] 仓库不含真实 `.env`、完整原始 CSV、密码、Token、个人绝对路径（[03 第 2 节](03-architecture-and-env.md)）
  - [ ] 后端连接配置：`TBD - 待 Issue #10 冻结`（`backend/.env.example` 由 #9/#10 落位）
  - [ ] 前端地址配置：`TBD - 待 Issue #11 冻结`（`frontend/.env.example` 由 #10/#11 落位）
- [ ] **数据准备**
  - [ ] 固定样本已随仓库存在：`data/fixtures/sparcs_mvp_sample.csv`
  - [ ] 完整 2021 SPARCS CSV 位于本地受控目录（路径只作命令参数，不写入仓库）
- [ ] **数据任务**（命令见 [04 第 4 节](04-development-and-runbook.md)）
  - [ ] 固定样例：`python data/src/run_sparcs_top10_pyspark.py --input data/fixtures/sparcs_mvp_sample.csv --expected data/fixtures/sparcs_mvp_expected_top10.json`，退出码 0，`status=PASS`、`engine=pyspark-local`、`pyspark_version=3.4.0`、`rows=16`、`diagnosis_nonempty_rows=15`、`diagnosis_nonempty_distinct=12`
  - [ ] 全量（有完整 CSV 时）：`python data/src/run_sparcs_top10_pyspark.py --input "<本地完整 SPARCS CSV 路径>"`
  - [ ] `winutils.exe`/native Hadoop 警告出现时：退出码 0 且结果一致即可接受，不提交 `winutils.exe`
- [ ] **服务结果**
  - [ ] MySQL 启动（VM hadoop001）：`sudo systemctl start mysql8`，版本检查与 3306 监听（[04 第 5.2 节](04-development-and-runbook.md)）；Socket 锁故障按手册只清理临时文件
  - [ ] 执行 DDL：`data/sql/001-mvp-disease-top10-service.sql`
  - [ ] 结果装载程序：`TBD - 待下游数据任务提交`（装载必须走事务刷新模板，DT-16）
- [ ] **后端启动**：`TBD - 待 Issue #10 冻结`（Flask 启动命令、端口、健康检查）
- [ ] **前端启动**：`TBD - 待 Issue #11 冻结`（Vite/Vue 启动命令、端口）
- [ ] **页面访问**：`TBD - 待 Issue #10/#11 冻结`（页面 URL 与 API 地址）
- [ ] **独立核对**（岗位5）
  - [ ] `python data/src/verify_sparcs_mvp.py`（固定样本）
  - [ ] `python data/src/verify_service_result_contract.py`
  - [ ] 有完整 CSV 时：`python data/src/verify_sparcs_mvp.py --full-source "<本地完整 SPARCS CSV 路径>"`
  - [ ] API 响应与页面显示按第 7 章矩阵逐项比对
- [ ] **保存证据**：按第 9 章规范归档，记录复现时间（UTC）与 `data_version`

## 9. 证据记录规范

### 9.1 应保存的证据

| 测试类型 | 必须保存的内容 |
|---|---|
| 命令执行 | 完整命令文本、退出码、stdout/stderr 全文 |
| 数据核对 | 核对脚本输出的完整 JSON |
| SQL 检查 | 执行的 SQL 文本、查询结果（含行数、排名连续性、版本/时间唯一性检查） |
| API 测试 | HTTP request（方法、URL、参数、头）、response（状态码、JSON body）、请求时间（UTC） |
| 页面测试 | 页面截图（含浏览器尺寸）、同刻 API 响应、触发状态的方式说明 |
| 版本追溯 | 对应 Git commit、`data_version`、测试执行时间（UTC） |

证据命名与保存位置约定：

```text
evidence/<issue>/<layer>/<case-id>/...
```

例如 `evidence/13/l1-fixture/L1-01/verify-sparcs-mvp-stdout.json`。本 Issue 只定义约定，不预建目录、不提交示例证据；正式验收首次产生证据时按此结构归档。每条证据必须能对应到本文的用例编号。

### 9.2 不得进入 Git 的内容

- 完整原始 CSV（固定脱敏样本除外）；
- 密钥、密码、Token、API Key、真实 `.env`；
- 个人绝对路径（含本地 CSV 路径、个人安装路径）；
- 大型中间结果、临时日志、截图外的二进制大文件；
- 任何人身份与隐私数据。

原则（[03 第 2 节](03-architecture-and-env.md)）：完整 CSV、个人绝对路径、密码和 Token 不提交 Git；证据在仓库内必须可复现、可追溯、不含秘密。

### 9.3 已有证据来源与待归档位置（2026-08-18，#26 第一轮）

本轮只在本档记录证据来源与待归档位置，未创建 `evidence/` 目录与证据文件；正式归档待后续轮次按 9.1 约定执行。

| 证据 | 当前来源 | 待归档位置 |
|---|---|---|
| L1-01/L1-02 固定样本复验 stdout（2026-08-18 本机） | 本机命令输出（记录于第 3.3 节用例） | `evidence/26/l1-fixture/L1-01/`、`evidence/26/l1-fixture/L1-02/` |
| 全量基线独立核对（2026-08-18） | 本机命令 stdout（未提交原始文件） | `evidence/26/l1-full/L1-03/` |
| 真实全量两次复跑、服务结果工件、MySQL `--apply`、提交后逐行查询、1264 回滚保留旧批次、真实 HTTP 200 | Issue #31 评论与 Resolution、PR #32/#33（已合并至 main）、[04 第 7.1 节](04-development-and-runbook.md) | `evidence/26/l2-data/DT-01~DT-10/`、`evidence/26/l2-mysql/DT-11~DT-17/`、`evidence/26/l3-api/API-01/` |
| 后端自动化测试（2026-08-18，12 passed） | 本机 pytest 输出（`backend/tests/test_disease_top10_api.py`） | `evidence/26/l3-api/api-pytest-stdout.txt` |
| API 空/非法/依赖失败真实 HTTP 证据 | 尚未采集（API-02~API-04 为 `PENDING_HTTP_EVIDENCE`） | `evidence/26/l3-api/API-02/`、`API-03/`、`API-04/` |

## 10. 问题记录与复验模板

发现任何不一致或失败时，按以下字段登记；修复后按同一模板复验并更新状态。

| 字段 | 说明 |
|---|---|
| Issue/问题编号 | 新建的 GitHub Issue 或 `QA-<seq>` 内部编号（内部编号最终必须落到 Issue） |
| 所属层 | L1 数据与固定样本 / L2 数据任务与服务结果 / L3 API / L4 页面 / L5 端到端 |
| 严重程度 | `BLOCKER`（阻塞下游）/ `MAJOR`（口径或契约错误）/ `MINOR`（展示或提示问题）；分级以组内确认为准 |
| 复现步骤 | 逐条可执行命令/操作 |
| 预期结果 | 引用冻结文档的具体条目（[01](01-data-and-feasibility.md)/[02](02-metrics-and-data-contract.md)/[03](03-architecture-and-env.md)） |
| 实际结果 | 命令输出/截图摘要 |
| 证据 | 按第 9 章归档的证据路径 |
| 负责人 | 按 [00 第 7 节](00-project-overview.md) 的主责方向 |
| 修复版本/commit | 修复后的 Git commit 或新 `data_version` |
| 复验结果 | 复验记录与证据 |
| 状态 | `PASS`（复验通过）/ `FAIL`（修复后仍不通过）/ `BLOCKED`（缺少前置，无法复验） |

登记表：

| Issue/问题编号 | 所属层 | 严重程度 | 复现步骤 | 预期结果 | 实际结果 | 证据 | 负责人 | 修复版本/commit | 复验结果 | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| （待登记） | | | | | | | | | | |

## 11. 等待 Issue #10 补充清单

#10 冻结后，本章各空位直接回填到第 5 章 API 用例与第 8 章 checklist 对应条目，不需要重写本文其他部分。2026-08-18 更新：第 5 章已按 #10 `CONFIRMED` 回填（来源：Issue #10 `CONFIRMED`；FROZEN 尚待 #10 最终关闭/冻结），本章保留为冻结状态追踪。

| 编号 | 待 #10 冻结内容 | 影响位置 | 当前引用依据 |
|---|---|---|---|
| A-01 | API 路径/URL：`GET /api/v1/diseases/top10`（已按 #10 CONFIRMED 回填） | API-01—API-04、第 8 章“页面访问” | [05-api.md](05-api.md) 第 2 节（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-02 | HTTP 方法与只读约束：`GET` 只读，不接受查询参数与请求体（已按 #10 CONFIRMED 回填） | API-01—API-04 | [05-api.md](05-api.md) 第 2、8 节（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-03 | 请求参数：无；携带任意参数 → `400 INVALID_QUERY_PARAMETER`（已按 #10 CONFIRMED 回填） | API-01、API-03 | [05-api.md](05-api.md) 第 2、7 节（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-04 | 正常响应状态码：`200 OK`（已按 #10 CONFIRMED 回填） | API-01 | [05-api.md](05-api.md) 第 4 节（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-05 | 合法空结果：`200` + `items:[]`，批次元数据保留；生产空表 → `503 RESULT_NOT_READY`（已按 #10 CONFIRMED 回填） | API-02、UI-03 | [05-api.md](05-api.md) 第 6、7 节（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-06 | 非法参数错误语义：`400 INVALID_QUERY_PARAMETER` / `INVALID_REQUEST_FORMAT`、`404 RESOURCE_NOT_FOUND`、`405 METHOD_NOT_ALLOWED`，统一 JSON 结构（已按 #10 CONFIRMED 回填） | API-03 | [05-api.md](05-api.md) 第 7 节（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-07 | 依赖失败语义：`503 DATABASE_UNAVAILABLE` / `RESULT_NOT_READY`、`500 SERVER_MISCONFIGURED` / `SERVICE_RESULT_INVALID` / `INTERNAL_ERROR`（已按 #10 CONFIRMED 回填） | API-04、UI-04 | [05-api.md](05-api.md) 第 7 节（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-08 | API 端口/地址：`127.0.0.1:5000`（已按 #10 CONFIRMED 提供启动与调用命令） | 第 8 章“后端启动”“页面访问” | [05-api.md](05-api.md) 第 10 节、[04 第 2.3 节](04-development-and-runbook.md)（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-09 | 后端启动命令与 `backend/requirements.txt`、`backend/.env.example`：已随 PR #29 合并，启动步骤见 [05-api.md](05-api.md) 第 10 节；停止命令待补 | 第 8 章“后端启动”“配置检查” | [05-api.md](05-api.md) 第 10 节（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-10 | API 健康检查：`GET /api/v1/health`（已提供，仅表示进程存活，不代替 TOP10 数据依赖检查） | 第 8 章“后端启动” | [05-api.md](05-api.md) 第 10、12 节（#10 `CONFIRMED`，FROZEN 待 #10） |
| A-11 | 与页面联调的 API 地址：后端默认 `127.0.0.1:5000`；前端实际联调地址待 #25 与页面一起确认 | UI-01—UI-12、第 8 章“前端启动”“页面访问” | [05-api.md](05-api.md) 第 10 节；#25 联调时确认 |

## 12. Issue #13 完成检查表

提交 PR 前逐项确认：

- [ ] `docs/05-test-and-acceptance.md` 已创建，成为岗位5后续 M1 验收的单一正式入口，未创建其他重复验收文档
- [ ] 验收执行顺序覆盖五层：数据与固定样本 → 数据任务与服务结果 → Flask API → Vue/ECharts 页面 → 端到端集成与组长电脑复现
- [ ] 固定样本核对章节引用真实仓库文件，写明输入、执行命令、预期结果、实际结果填写位置与证据保存位置；样本行数、非空诊断数、期望 TOP10 均来自现有文件/正式文档
- [ ] 数据任务/服务结果验收模板覆盖：统计口径、清洗规则、排序与并列、严格 TOP10、重复执行一致性、服务结果字段契约、`data_version`、`unit`、`generated_at`、患者数与记录数不混淆
- [ ] API 验收模板覆盖四类：正常结果、合法空结果、非法参数、依赖失败；未冻结内容全部标记 `TBD - 待 Issue #10 冻结`，未自行创造 URL、参数名、状态码、error code、JSON 错误结构
- [ ] 页面验收模板覆盖四态与附加检查项（排名、名称、病例量、单位、长名称、并列、窗口变化、重试入口、不重算 TOP10、不用 Mock 冒充），触发方法未实现的标记“待补”
- [ ] 端到端一致性比较链与矩阵已预留，覆盖名称、排名、病例量、单位和数据版本
- [ ] 组长电脑复现清单为可勾选 checklist，命令优先引用 [04-development-and-runbook.md](04-development-and-runbook.md)，缺失命令标记 `TBD`
- [ ] 证据记录规范明确应保存的内容与不得进入 Git 的内容
- [ ] 问题记录与复验模板字段完整，状态限定 `PASS` / `FAIL` / `BLOCKED`
- [ ] 等待 #10 的内容集中在单一章节，冻结后只需补空位
- [ ] 未宣称 API 已通过、页面已通过、M1 全链路已通过
- [ ] 除 `docs/05-test-and-acceptance.md` 外未修改任何其他正式文件；`verify_sparcs_mvp.py` 仅只读运行，未修改上游脚本或 fixture

## 13. Issue #26 执行状态（2026-08-18 第一轮回填）

本轮只回填已有可靠证据、且不依赖前端完成的验收内容。**不宣布 #10 FROZEN、不宣布 #26 第 1 项最终完成、不宣布 API 四类全部通过、不宣布页面四态 PASS、不宣布 M1 全链路 PASS。**

- 已回填为 `PASS`：L1-01/L1-02（2026-08-18 本轮复验）、DT-01~DT-17（#31 真实全量两次复跑、MySQL 实表发布、逐行查询、1264 回滚保留旧批次）、API-01（#31/#26 真实 HTTP GET 200、10 项、data_version 与 MySQL 一致）。
- 已回填为 `VERIFIED`：1.4 事实表“MySQL 业务结果实际装载”“Flask API”两行；第 2 章 L2 状态。
- 已按契约回填但非最终 PASS：API-02~API-04（`PENDING_HTTP_EVIDENCE`——契约来源 Issue #10 `CONFIRMED` + 后端 pytest 12 passed；真实 HTTP 请求/响应/状态码证据尚未采集，#26 第 4 项未完成）。
- 已回填契约来源：第 5 章请求构造/预期响应、第 11 章 A-01~A-10。所有回填内容均标注“来源：Issue #10 `CONFIRMED`；FROZEN 尚待 #10 最终关闭/冻结”。
- 仍 BLOCKED：UI-01~UI-12 与页面四态（待 #11/#25）、第 7 章端到端一致性（页面显示列与 E2E-01/E2E-02）、第 8 章组长电脑完整复现（前端启动/页面访问）、M1 整体 PASS。
- #26 最终 Resolution：`BLOCKED`（待 #10 FROZEN、#25 页面落位并完成页面四态与端到端验收后统一编写）。
- 本轮仅修改本文件；未创建 `evidence/` 目录；未修改 `docs/02`、`docs/03`、`docs/04`、`docs/05-api.md`、`backend/**`、`data/**`；未执行 `git add`/`commit`/`push`。
