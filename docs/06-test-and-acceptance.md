# M1 疾病病例量 TOP10 测试与验收

> 终局更新（2026-08-18）：M1 表格保留为历史证据。完整产品新增以下十模块共同关闭门槛；fixture 和 Mock 只证明开发契约，不能替代真实验收。

## 终局十模块共同门槛

- 固定样例与独立脚本一致；PySpark 快照与 MySQL 逐键一致；MySQL、API、页面的字段、单位、排序、`data_version` 一致；
- API 覆盖正常、非法参数、合法空结果、模块未发布、数据库失败；页面可复现 loading、success、empty、error、retry；
- 金额分位数明确 accuracy，住院时长 `120 +` 截断可计数，原始记录不按患者去重；
- 模型固定种子可复现，请求和训练特征均无目标泄漏，页面不作诊断或治疗结论；
- AI 的工具名、参数、来源指标、数据版本可追踪；缺少密钥、超时、模型错误和断网时返回真实错误，不生成答案；
- 在组长电脑从干净 `main` 执行数据生成、事务发布、后端测试、前端构建与十页演示；
- 每个父 Issue 独立填写数据/API/UI 一致性矩阵和 Resolution。最终集成 #83 仅在十个父 Issue、文档、答辩材料、演示脚本均完成后关闭。

当前自动化基线命令为 `python -m pytest backend/tests data/tests -q` 与 `npm run build`。自动化通过不等于真实 CSV、MySQL、DeepSeek 或组长电脑复现已经通过；后者必须附命令输出、API 响应、页面截图、commit、数据版本和执行时间。

> 文档版本：V0.2
> 更新日期：2026-08-18
> 状态：`EXECUTED`（Issue #26 已执行 M1 最终验收，记录见文末“Issue #26 M1 最终验收执行记录”；M1 整体结论 `BLOCKED`：本机可复现层全部 PASS，组长电脑本轮复现为 HANDOFF，无 FAIL）
> 关联 Issue：#13（准备 M1 TOP10 验收方案与证据框架，先于 #10 的并行任务）
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

### 1.2 当前阶段：PRE-API / 验收准备

| 层 | 上游状态 | 本 Issue 可做 | 本 Issue 不可做 |
|---|---|---|---|
| 口径与契约 | `FROZEN`（#7、#9） | 引用为用例预期 | 修改或另写一套口径 |
| 固定样本与独立核对 | `VERIFIED` | 复验、填写证据 | 修改 fixture 或核对脚本 |
| 数据任务与服务结果 | PySpark 全量工件已通；MySQL 装载 `HANDOFF` | 预置验收用例 | 宣称 MySQL/API 全链路完成 |
| Flask API | `HANDOFF`（代码已合并，待真实 MySQL 批次） | 预置四类用例模板 | 填写真实 URL、参数、状态码、错误码 |
| Vue/ECharts 页面 | `HANDOFF`（待 #11） | 预置四态与检查项模板 | 填写页面触发方式 |
| 全链路与组长电脑复现 | `HANDOFF`（待相关实现落位后由 Issue #26 执行） | 预置比较链与 checklist | 宣称 M1 PASS |

### 1.3 当前禁止宣布的结论

- 不宣布“API 已通过”——Issue #10 正式 API 契约尚未完成；
- 不宣布“页面已通过”——Issue #11 页面实现尚未完成；
- 不宣布“M1 全链路已通过”——最终全链路验收在后续 Issue #26 执行；
- 固定样本 `PASS` 不等于真实全链路通过证据；Mock 结果不等于正式验收证据；
- RAW/侦察结果不是另一套正式业务口径，只作为与正式任务对比的基线（[01 第 4、8 节](01-data-and-feasibility.md)）。

### 1.4 当前已确认的事实（截至 2026-08-18，含 #26 执行轮）

| 项目 | 状态 | 依据 |
|---|---|---|
| 固定样本独立核对脚本 | `PASS`（#26 本机复验，退出码 0） | 本文第 3 章、`evidence/26/l1-fixture/` |
| 服务结果契约检查脚本 | `PASS`（#26 本机复验，退出码 0） | 本文第 4 章、`evidence/26/l1-fixture/` |
| 本机 PySpark 固定样例 | `PASS`（#26 本机两次运行一致） | `evidence/26/l2-data-task/DT-sample/` |
| 本机 PySpark 全量任务 | `PASS`（#31 记录级，两次一致） | [04 第 4.1 节](04-development-and-runbook.md)、#31 Resolution |
| MySQL 业务结果实际装载 | `PASS`（#31 记录级：10 行事务装载 + 回滚演练） | #31 Resolution、本文 DT-16/DT-17 |
| Flask API | `PASS`（#26 本机 pytest 12 passed + 实际 HTTP 四类语义；真实批次记录级） | 本文第 5 章、`evidence/26/l3-api/` |
| Vue/ECharts 页面 | `PASS`（#25 记录级四态与展示复核；#26 本机源码静态核对） | 文末 #25 记录、`evidence/26/l4-page/` |
| M1 全链路一致性 | `BLOCKED`（本机可复现层 PASS；组长电脑本轮复现 HANDOFF） | 文末“Issue #26 M1 最终验收执行记录” |

## 2. 验收执行顺序

验收按以下五层顺序推进；上层被阻断时不宣布其上游层“对下游已生效”，但已独立完成的层可以单独记录结果。

| 层 | 名称 | 内容 | 主要依据 | 当前状态 |
|---|---|---|---|---|
| L1 | 数据与固定样本 | 固定样本独立核对、全量基线核对 | [01](01-data-and-feasibility.md) 第 6、7 节 | `PASS`（#26 本机复验；全量基线为 #31 记录级） |
| L2 | 数据任务与服务结果 | PySpark 清洗聚合、服务结果契约、MySQL 事务装载 | [02](02-metrics-and-data-contract.md) | `PASS`（#26 本机固定样例两次一致；MySQL 实表为 #31 记录级） |
| L3 | Flask API | 只读查询服务结果、四类响应语义 | [05](05-api.md)（#10 冻结） | `PASS`（#26 本机 pytest 12 passed + 实际 HTTP 全覆盖；真实批次记录级） |
| L4 | Vue/ECharts 页面 | 四态、展示一致性与交互检查 | 文末 #25 记录 | `PASS`（#25 记录级四态与展示复核；#26 本机源码静态核对） |
| L5 | 端到端集成与组长电脑复现 | 全链路一致性比较、组长电脑 checklist | 本文第 7、8 章 | `BLOCKED/HANDOFF`（组长电脑本轮复现待执行；#31/#25 记录级证据已覆盖各环节） |

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
| L1-01 | 固定样本独立核对 | 仓库默认 fixture 路径；Python 标准库可用 | 仓库根目录执行 `python data/src/verify_sparcs_mvp.py` | 退出码 0，`status=PASS`，计数摘要与期望一致 | 2026-08-17 复验：退出码 0，`status=PASS`，`rows=16`、`malformed_rows=0`、`out_of_scope_rows=0`、`diagnosis_nonempty_rows=15`、`diagnosis_nonempty_distinct=12`，TOP10 与期望一致 | 脚本 stdout（JSON）；待正式归档至 `evidence/`（见第 9 章） | `PASS` |
| L1-02 | 服务结果契约检查 | 同上 | 仓库根目录执行 `python data/src/verify_service_result_contract.py` | 退出码 0，`status=PASS`，`rows=10`、`unit=discharge_records` | 2026-08-17 复验：退出码 0，`status=PASS`，`data_version=fixture:sparcs_mvp_sample:v1`、`rows=10`、`unit=discharge_records` | 脚本 stdout（JSON） | `PASS` |
| L1-03 | 全量基线核对（有完整 CSV 时） | 本地完整 2021 SPARCS CSV（路径只作命令行参数，不写入仓库） | 执行 `python data/src/verify_sparcs_mvp.py --full-source "<本地 SPARCS CSV 路径>"` | 2,101,588 行、0 解析异常、2,099,954 条非空诊断记录、477 个非空诊断值，TOP10 与 [01 第 4 节](01-data-and-feasibility.md) 基线一致 | 2026-08-18：完整文件 SHA-256 与 [02 第 1.1 节](02-metrics-and-data-contract.md) 一致，独立核对 `PASS` | 本地命令 stdout（未提交原始文件） | `PASS` |

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
| DT-01 | 统计口径一致 | 任务实际输入 CSV | 核对数据任务是否按“`Discharge Year` 去首尾空白后等于 `2021`”筛选 | 非 2021 记录不计入本指标，并计入质量统计（`out_of_scope_rows`） | 固定样例：PySpark 任务 `out_of_scope_rows=0` 且与独立核对一致；实现按 `F.trim(Discharge Year)=2021` 筛选（`run_sparcs_top10_pyspark.py`）。真实全量 `out_of_scope_rows=0` 为 #31 记录级 | `evidence/26/l2-data-task/DT-sample/pyspark-sample-run1.json`；#31 Resolution | 固定样例 `PASS`（本机）；真实任务 `PASS`（记录级，#31） |
| DT-02 | 分组字段一致 | 任务实现与日志 | 核对只按 `CCSR Diagnosis Description` 分组；`CCSR Diagnosis Code` 只用于追溯 | 分组维度唯一；代码字段不参与分组、合并与展示 | 源码核对：任务只 `groupBy("diagnosis")`，诊断代码字段未参与分组/合并/展示（`run_sparcs_top10_pyspark.py:58-63`） | 源码核对记录（`evidence/26/execution-record.md`） | 固定样例 `PASS`（本机） |
| DT-03 | 清洗规则一致 | 任务实现 | 核对只清理诊断名称首尾空白 | 保留大小写、内部空白、标点、括号；不做大小写折叠、同义词合并或代码映射（对照 [02 第 3 节](02-metrics-and-data-contract.md) 示例） | 契约边界样例 `PASS`（`LIVEBORN`/`liveborn` 区分、` LIVEBORN ` 合并，`verify_sparcs_mvp.py` 内置样例）；PySpark 侧用统一 `EDGE_WHITESPACE` 正则仅去首尾 Unicode 空白 | `evidence/26/l1-fixture/L1-01/verify-sparcs-mvp-stdout.json`（contract_examples） | 固定样例 `PASS`（本机） |
| DT-04 | 空诊断排除 | 任务实现与输出 | 核对缺失、空字符串、全空白诊断的处置 | 清洗后为空的不进入排行；原始行仍计入输入质量统计 | 样本 16 行含 1 条空诊断：`diagnosis_nonempty_rows=15`，与期望一致；独立核对与 PySpark 结果一致 | `evidence/26/l1-fixture/`、`evidence/26/l2-data-task/DT-sample/` | 固定样例 `PASS`（本机） |
| DT-05 | 不去重 | 任务实现 | 用含重复诊断（样例中 `COMPLICATION …`、`LIVEBORN` 各 2 条）核对计数 | 相同诊断自然合并计数；即使整行重复也按两条住院出院记录计数 | `COMPLICATION …`、`LIVEBORN` 各计 2（TOP10 前 3 名 case_count=2），与期望完全一致 | `evidence/26/l1-fixture/L1-01/verify-sparcs-mvp-stdout.json` | 固定样例 `PASS`（本机）；真实任务 `PASS`（记录级，#31） |
| DT-06 | 排序与并列一致 | 任务输出 | 核对复合键 `(-case_count, diagnosis_name)` | `case_count` 降序；并列时 `diagnosis_name` 按 UTF-8/Unicode 二进制字典序升序 | 并列三项（case_count=2）按名称升序：`COMPLICATION…`→`LIVEBORN`→`TRAUMATIC…`；独立核对、PySpark、服务结果契约检查三方一致 | `evidence/26/l1-fixture/`、`evidence/26/l2-data-task/DT-sample/` | 固定样例 `PASS`（本机） |
| DT-07 | 严格 TOP10 | 任务输出 | 核对截断发生在全量稳定排序之后 | 严格返回前 10 项；少于 10 项返回全部；第 10 名并列不扩展（对照 [02 第 4 节](02-metrics-and-data-contract.md)） | 样本 12 个非空诊断值严格取前 10，`PREVIOUS C-SECTION`/`URINARY TRACT INFECTIONS` 被截断，与期望一致 | `evidence/26/l1-fixture/L1-01/verify-sparcs-mvp-stdout.json` | 固定样例 `PASS`（本机） |
| DT-08 | 结构异常行处理 | 任务输入 | 构造或检查无法按表头解析的 CSV 行场景 | 任务失败且不发布部分结果；正式数据基线为 0 行 | 固定样例与正式数据 `malformed_rows=0`（本机复验 + #31 记录级）；任务读取模式为 `FAILFAST`（`run_sparcs_top10_pyspark.py:41`），异常行会令任务失败 | 源码核对 + `evidence/26/l1-fixture/`；#31 Resolution | 基线为 0 行 `PASS`；人为构造场景未执行（本机不额外构造） |
| DT-09 | 超长/不可编码诊断名 | 任务实现 | 检查对超过 `VARCHAR(255)` 或无法编码名称的处理 | 不截断、不替换，任务失败，不刷新服务表 | 发布程序与 API Service 均显式拒绝 `>255` 名称（`publish_top10_mysql.py`、`disease_top10.py` 校验）；DDL 为 `VARCHAR(255)`，超长写入会被 MySQL 拒绝 | 源码核对记录 | 规则存在性 `PASS`（本机源码核对）；场景未构造 |
| DT-10 | 重复执行结果一致 | 同一输入文件 | 同一输入重复运行任务两次以上 | 每次得到相同 TOP10 与计数摘要；刷新幂等（重复发布同一 `data_version` 结果一致） | 本机 PySpark 两次运行（不同 `generated_at`）：TOP10 与全部计数摘要完全一致、`data_version` 相同；真实全量两次一致为 #31 记录级；回滚演练为 #31 记录级 | `evidence/26/l2-data-task/DT-sample/pyspark-sample-run1.json`、`pyspark-sample-run2.json`；#31 Resolution | 固定样例 `PASS`（本机）；真实任务 `PASS`（记录级，#31） |

服务结果与发布用例：

| 用例编号 | 检查目标 | 输入/前置条件 | 操作步骤 | 预期结果 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|
| DT-11 | 服务结果字段契约 | 结果工件或 MySQL 表 | 核对字段集合与类型：`rank` TINYINT UNSIGNED 1—10 连续、`diagnosis_name` VARCHAR(255) utf8mb4_bin 非空且批内唯一、`case_count` BIGINT UNSIGNED 大于 0、`unit` 固定 `discharge_records`、`data_version`/`generated_at` 见 DT-12/DT-14（DDL 见 `data/sql/001-mvp-disease-top10-service.sql`） | 与 [02 第 2.2 节](02-metrics-and-data-contract.md) 完全一致；不包含患者 ID、诊断代码、明细等字段 | 固定样例契约检查 PASS（L1-02，本机）；PySpark 工件契约核对 PASS（本机）；API 响应仅含 `rank`/`diagnosis_name`/`case_count`（本机实测）；MySQL 实表 10 行为 #31 记录级 | `evidence/26/l1-fixture/L1-02/`、`evidence/26/l2-data-task/DT-contract/artifact-contract-check-stdout.json`；#31 Resolution | 固定样例 `PASS`（本机）；MySQL 实表 `PASS`（记录级，#31） |
| DT-12 | `data_version` 一致 | 任务输入指纹 | 核对任务运行前记录的实际 `data_version` 与输入文件指纹（文件名+大小+SHA-256）对应；批内所有行同一值 | 同批行 `data_version` 唯一；版本变化时不混插新旧行、不沿用旧结果 | 固定样本 `fixture:sparcs_mvp_sample:v1` PASS（L1-02）；PySpark 工件指纹与 `data_version` 自洽（`sparcs_mvp_sample_sha256_…`）；真实批次 `sparcs_2021_20231012_sha256_…` 为 #31 记录级 | `evidence/26/l1-fixture/L1-02/`、`evidence/26/l2-data-task/DT-sample/`；#31 Resolution | 固定样例 `PASS`（本机）；真实任务 `PASS`（记录级，#31） |
| DT-13 | `unit` 一致 | 服务结果所有行 | 逐行核对 | 所有行 `unit=discharge_records` | 固定样本 PASS（L1-02，本机）；API 响应 `unit=discharge_records`（本机实测） | `evidence/26/l3-api/API-01/api-200-success.json` | 固定样例 `PASS`（本机） |
| DT-14 | `generated_at` 一致 | 服务结果所有行 | 核对批内所有行同一 `generated_at`（UTC、DATETIME(6)）；真实任务必须生成新时间 | 同批唯一；不得沿用 fixture 的 `2026-08-17T00:00:00Z` | 固定样本 PASS（L1-02）；真实批次 `2026-08-18T01:36:42.446058Z`（#31 记录级，非 fixture 时间） | `evidence/26/l1-fixture/L1-02/`；#31 评论 02:05:51Z | 固定样例 `PASS`（本机）；真实任务 `PASS`（记录级，#31） |
| DT-15 | 术语一致：不混淆患者数与记录数 | 任务、服务结果、API、页面文案 | 检查任何层是否出现“患者数/患病人数”表述 | `case_count` 一律表述为住院出院记录数；`unit=discharge_records` 明示单位（术语见 [CONTEXT.md](../CONTEXT.md)） | 本机全仓检索：`backend/app`、`frontend/src`、`data/src`、`docs/05-api.md` 无违规“患者数”表述；页面文案为“有效住院出院记录数量，不表示患者人数” | 检索记录（`evidence/26/execution-record.md` 正文） | `PASS`（本机检索） |
| DT-16 | 事务刷新与失败保护 | MySQL 8.0.30（hadoop001）已启动；DDL 已执行 | 按 `data/sql/001-mvp-disease-top10-service.sql` 事务模板执行装载，并核对事务内 COUNT/版本/排名检查 | 全部通过才 COMMIT；异常 ROLLBACK 且旧批次继续可读；不发布空批次（0 个有效诊断时任务失败） | #31 实机证据：`--apply` 事务提交 10 行；故意超 `BIGINT UNSIGNED` 触发 MySQL 1264 → 回滚 → 旧批次 10 行仍可读（记录级）。本机 dry-run 校验路径 PASS | `evidence/26/l2-data-task/DT-contract/publish-dry-run-stdout.json`；#31 评论 02:05:51Z、Resolution | `PASS`（记录级，#31 + 本机 dry-run） |
| DT-17 | 服务结果可用性 | MySQL 表内容 | 按 [02 第 2.2 节](02-metrics-and-data-contract.md) 只读查询检查：1—10 行、`rank` 连续、名称唯一、单一 `data_version`、单一 `generated_at`、`unit` 正确 | 满足全部条件才视为“可用”，API 才允许返回 | #31 实机证据：提交后 TCP 查询核对 10 行、连续排名、名称/数量/单位/版本/时间与工件一致；API Service 的同一套校验在本机 pytest 覆盖（`SERVICE_RESULT_INVALID` 拒绝损坏结果） | #31 Resolution；`evidence/26/l3-api/pytest-output.txt` | `PASS`（记录级，#31 + 本机 pytest） |

## 5. API 验收模板

> 前置：Issue #10 正式 API 契约已冻结（[05-api.md](05-api.md) `FROZEN`）。URL、HTTP 方法、请求参数、状态码、error code、JSON 错误结构以 #10 冻结值为准，本章不自行创造。
>
> 已冻结的边界：API 只查询已校验的 MySQL 服务结果（`disease_case_count_top10_result`），Route 不重新清洗、分组、排序或回读 HDFS（[02 第 2.2 节](02-metrics-and-data-contract.md)）；MySQL 不可用时返回明确依赖失败、不现场计算（[03 第 7 节](03-architecture-and-env.md)）；响应内容必须与服务结果语义一致（沿用**服务结果字段** `rank`、`diagnosis_name`、`case_count`、`unit`、`data_version` 和必要的批次元数据，见 [02 第 2.2 节](02-metrics-and-data-contract.md)）。API JSON 顶层结构、字段名与类型已由 #10 冻结（`code`/`message`/`data`/`trace_id`，见 [05 第 3、4 节](05-api.md)）。

| 用例编号 | 类别 | 检查目标 | 前置条件 | 输入/请求构造 | 预期响应 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|---|
| API-01 | 正常结果 | 返回已发布服务结果批次，内容与数值与服务结果一致 | MySQL 已有可用批次（DT-17 通过） | `GET /api/v1/diseases/top10`（无参数、无请求体，[05 第 2 节](05-api.md)） | `200`；`code=OK`；`data` 含 `metric`、`unit`、`data_version`、`generated_at`、`items`（0—10 项，按 `rank` 升序），逐项与服务结果一致（[05 第 4 节](05-api.md)） | 2026-08-18 本机 fixture 模式：`200`、`code=OK`、10 项、`unit=discharge_records`、`data_version=fixture:sparcs_mvp_sample:v1`、`generated_at=2026-08-17T00:00:00.000000Z`，`X-Trace-ID` 与 `trace_id` 一致；真实 MySQL 批次 HTTP 200/10 项/真实 `data_version` 见 #31 Resolution（记录级） | `evidence/26/l3-api/API-01/api-200-success.json`；#31 Resolution | fixture `PASS`；真实批次 `PASS`（记录级） |
| API-02 | 合法空结果 | 合法请求但无可展示结果的语义 | 空快照 fixture（`TOP10_FIXTURE_STATE=empty`） | `GET /api/v1/diseases/top10` | `200`；`items=[]`；`data_version`、`generated_at`、`unit` 等批次元数据仍存在（[05 第 6 节](05-api.md)）；生产 MySQL 空表返回 `503 RESULT_NOT_READY`，不误判为空数据 | 2026-08-18 本机：`200`、`items=[]`、`data_version=fixture:sparcs_mvp_empty:v1`、`unit=discharge_records`；`RESULT_NOT_READY` 语义由 pytest 覆盖（`test_unpublished_result_is_not_misreported_as_empty`） | `evidence/26/l3-api/API-02/api-200-empty.json`、`evidence/26/l3-api/pytest-output.txt` | `PASS` |
| API-03 | 非法参数 | 参数缺失、类型错误、越界等的统一错误语义 | fixture 模式即可 | `GET ...?limit=5`；GET 携带 JSON 请求体；`POST/PUT/DELETE`；不存在的 URL | `400 INVALID_QUERY_PARAMETER`（附 `details.parameters`）；`400 INVALID_REQUEST_FORMAT`；`405 METHOD_NOT_ALLOWED`；`404 RESOURCE_NOT_FOUND`（[05 第 7 节](05-api.md)） | 2026-08-18 本机实测逐一命中：400（参数/请求体）、405（POST/PUT/DELETE）、404；`data=null`，均含 `trace_id` | `evidence/26/l3-api/API-03/api_400_queryparam.json`、`api_400_body.json`、`api_405_post.json`、`api_405_put.json`、`api_405_delete.json`、`api_404.json` | `PASS` |
| API-04 | 依赖失败 | MySQL 不可用等依赖故障的响应 | 可控构造：mysql 模式缺配置；mysql 模式指向不可达实例；非法 fixture 状态/数据源 | `GET /api/v1/diseases/top10`（对应环境变量下启动 Flask） | 配置缺失/损坏 `500 SERVER_MISCONFIGURED`；数据库不可用 `503 DATABASE_UNAVAILABLE`；结果契约损坏 `500 SERVICE_RESULT_INVALID`；不现场计算、不返回假数据（[05 第 7 节](05-api.md)） | 2026-08-18 本机实测：缺配置/非法 fixture 状态/非法数据源均 `500 SERVER_MISCONFIGURED`；不可达 MySQL `503 DATABASE_UNAVAILABLE`；`SERVICE_RESULT_INVALID`、`INTERNAL_ERROR` 由 pytest 覆盖 | `evidence/26/l3-api/API-04/api_mysql_missing_config.json`、`api_invalid_fixture_state.json`、`api_invalid_data_source.json`、`api_mysql_unreachable.json`、`evidence/26/l3-api/pytest-output.txt` | `PASS` |

## 6. 页面验收模板

> 前置：Issue #11 页面实现已落位（#25 正式接口适配完成）。页面触发方法以 #11/#25 实现为准（启动命令、Mock 四态复现步骤见文末“Issue #25 页面正式接口适配记录”）。
>
> 已冻结的边界：页面只消费 Flask API，不直连数据库、不重新计算 TOP10、不得写死正式结果（[03 第 2、3 节](03-architecture-and-env.md)）；Mock 只服务并行开发，不能作为真实链路的替代证据。

四态用例：

| 用例编号 | 检查目标 | 前置条件 | 触发方法 | 预期表现 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|
| UI-01 | loading 态 | 前端按 `cd frontend; npm ci; npm run dev` 启动（#25 固定） | 正式模式请求未返回期间；Mock 模式点 loading 按钮 | 数据未返回时显示可辨识的加载状态，不显示空白或陈旧数据 | 显示“数据加载中……”，清空旧结果（#25 浏览器 DOM 复核） | #25 Resolution、文末“Issue #25 页面正式接口适配记录” | `PASS`（记录级，#25） |
| UI-02 | success 态 | MySQL 已有可用批次且 API 正常返回（前置用例：DT-17、API-01） | 正式模式 `npm run dev`（后端 MySQL 模式启动） | 展示 API 返回的 TOP10：排名、名称、病例量与单位完整且与服务结果一致 | 真实 API HTTP 200/10 项，页面显示真实名称、数量、单位和真实批次（#25 浏览器 DOM/截图） | #25 Resolution、#31 Resolution | `PASS`（记录级，#25） |
| UI-03 | empty 态 | API 合法空结果语义已由 #10 冻结（前置用例：API-02） | Mock 模式 `VITE_TOP10_MODE=mock`、`VITE_TOP10_MOCK_STATE=empty` 启动，点 empty 按钮 | 合法空结果时显示明确空状态，不与加载或错误混淆；空结果语义与 API-02 一致 | 显示“暂无可展示数据”，不显示空坐标轴（#25 浏览器 DOM） | #25 Resolution、文末 #25 记录 | `PASS`（记录级，#25） |
| UI-04 | error 态 | 可构造 API 依赖失败场景（前置用例：API-04） | Mock 模式点 error 按钮 | 依赖失败或请求失败时显示明确错误提示，并提供可触发的重试路径 | 显示 `DATABASE_UNAVAILABLE` 安全提示与“重新加载”，重试后恢复 success（#25 浏览器 DOM） | #25 Resolution、文末 #25 记录 | `PASS`（记录级，#25） |

展示与一致性用例：

| 用例编号 | 检查目标 | 前置条件 | 操作步骤 | 预期结果 | 实际结果 | 证据 | 状态 |
|---|---|---|---|---|---|---|---|
| UI-05 | 排名与顺序 | success 态已通过（UI-02），页面展示真实 API 数据 | 对比页面渲染与服务结果/API 响应 | 排名 1—10 与服务结果完全一致，顺序不重排 | 页面只消费 `data.items` 原始顺序（源码无排序逻辑；#25 浏览器复核一致） | #25 Resolution、`evidence/26/l4-page/frontend-runtime-handoff.md` 源码核对 | `PASS`（记录级，#25 + 本机源码核对） |
| UI-06 | 主诊断描述 | success 态已通过（UI-02），页面展示真实 API 数据 | 逐项对比页面名称与 API 返回的 `diagnosis_name` | 名称逐字符一致（含大小写、标点、括号），不截断改写；坐标轴可省略、Tooltip 保留全文 | 名称逐字符一致，Tooltip 显示完整名称（#25 Tooltip DOM） | #25 Resolution、文末 #25 记录 | `PASS`（记录级，#25） |
| UI-07 | 病例量与单位 | success 态已通过（UI-02），页面展示真实 API 数据 | 逐项对比页面数值与 API 返回的 `case_count` | 数值一致；单位信息与服务结果 `unit=discharge_records` 一致；文案不写成“患者数/患病人数” | 数值与响应一致；文案为“有效住院出院记录数量，不表示患者人数”（#25 DOM + 本机源码核对） | #25 Resolution、`evidence/26/l4-page/frontend-runtime-handoff.md` | `PASS`（记录级，#25 + 本机源码核对） |
| UI-08 | 长疾病名称 | success 态已通过（UI-02） | 使用全量基线 TOP10 中最长名称 `SCHIZOPHRENIA SPECTRUM AND OTHER PSYCHOTIC DISORDERS` 核对展示 | 名称完整可辨识，不丢字、不截断（具体呈现方式以 #11 实现为准，验收时逐字符比对） | Tooltip 保留完整长名称（#25 Tooltip DOM） | #25 Resolution、文末 #25 记录 | `PASS`（记录级，#25） |
| UI-09 | 并列结果 | success 态已通过（UI-02） | 使用固定样本并列项（病例量同为 2 的三项）核对 | 并列项按名称升序展示，顺序与服务结果一致，不出现重名次 | Mock 并列项顺序保持 API 顺序（#25 浏览器复核） | #25 Resolution、文末 #25 记录 | `PASS`（记录级，#25） |
| UI-10 | 浏览器窗口变化 | success 态已通过（UI-02） | 调整窗口宽度/缩放 | 排名、名称、数量仍可辨识，数据不丢失不重算（具体响应式标准由 #11 实现时补充） | 390px/1280px 无横向溢出，图表 resize 不改变 API 顺序（#25 尺寸复核） | #25 Resolution、文末 #25 记录 | `PASS`（记录级，#25） |
| UI-11 | 页面不重新计算 TOP10 | 前端源码已随 #11 提交到仓库 | 检查前端源码与网络行为 | 页面只请求 API 并渲染返回结果，无本地分组/排序/截断逻辑，无直连 MySQL | 本机源码静态核对：无排序/聚合/截断逻辑、无数据库引用、请求层只发 GET 无 body（`evidence/26/l4-page/`）；#25 浏览器控制台无 error/warning | `evidence/26/l4-page/frontend-runtime-handoff.md`、#25 Resolution | `PASS`（本机源码核对 + 记录级） |
| UI-12 | 页面不用 Mock 冒充正式验收 | 页面处于 success 态；验收环境可访问真实 API | 核对页面请求目标与数据来源 | 正式验收必须指向真实 API 与真实服务结果；Mock 仅验证界面结构，不得作为 UI-05—UI-09 的证据 | 正式模式默认请求 API；Mock 仅在显式 `VITE_TOP10_MODE=mock` 启用（`App.vue`）；#25 正式 success 与 Mock 批次明确区分 | `evidence/26/l4-page/frontend-runtime-handoff.md`、#25 Resolution | `PASS`（本机源码核对 + 记录级） |

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
  - [ ] 后端连接配置：`backend/.env.example`（`TOP10_DATA_SOURCE=fixture` 默认；真实 MySQL 模式需本机 `backend/.env`，不提交 Git；#10 落位）
  - [ ] 前端地址配置：`frontend/.env.example`（`VITE_API_BASE_URL` 默认走 Vite 代理 `/api → 127.0.0.1:5000`；`VITE_TOP10_MODE=api` 默认正式模式；#10/#11 落位）
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
- [ ] **后端启动**：`cd backend; python -m pip install -r requirements.txt; python run.py`（默认 fixture；MySQL 模式需本机 `backend/.env` 设 `TOP10_DATA_SOURCE=mysql`）；健康检查 `curl.exe -i http://127.0.0.1:5000/api/v1/health` → 200（#10 固定）
- [ ] **前端启动**：`cd frontend; npm ci; npm run dev`（#11/#25 固定）；构建检查 `npm run build`
- [ ] **页面访问**：页面 `http://localhost:5173`（Vite 默认端口），API 经开发代理指向 `http://127.0.0.1:5000`（#10/#11/#25 固定）
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

#10 冻结后，本章各空位直接回填到第 5 章 API 用例与第 8 章 checklist 对应条目，不需要重写本文其他部分。

| 编号 | 待 #10 冻结内容 | 影响位置 | 当前引用依据 |
|---|---|---|---|
| A-01 | API 路径/URL | API-01—API-04、第 8 章“页面访问” | 无（[04 第 2.3 节](04-development-and-runbook.md) 标记 Flask 未固定） |
| A-02 | HTTP 方法与只读约束的最终表述 | API-01—API-04 | 只读 API 边界已冻结（[03 第 3 节](03-architecture-and-env.md)）；方法未冻结 |
| A-03 | 请求参数名称、类型与校验规则 | API-01、API-03 | 无 |
| A-04 | 正常响应状态码 | API-01 | 无 |
| A-05 | 合法空结果的语义与响应结构 | API-02、UI-03 | M1 不发布零有效诊断空批次（[02 第 2.2 节](02-metrics-and-data-contract.md)）；空数据状态由 #10 定义 |
| A-06 | 非法参数的状态码、error code、JSON 错误结构 | API-03 | 无 |
| A-07 | 依赖失败（MySQL 不可用）的状态码与 JSON 错误结构 | API-04、UI-04 | 返回明确依赖失败、不现场计算（[03 第 7 节](03-architecture-and-env.md)）；结构未冻结 |
| A-08 | API 端口/地址 | 第 8 章“后端启动”“页面访问” | 无（[04 第 2.3 节](04-development-and-runbook.md)） |
| A-09 | 后端启动/停止命令、`backend/requirements.txt`、`backend/.env.example` | 第 8 章“后端启动”“配置检查” | 归属 #10（[04 第 3.2 节](04-development-and-runbook.md)） |
| A-10 | API 健康检查 | 第 8 章“后端启动” | 归属 #10（[04 第 8 节](04-development-and-runbook.md) 交接清单） |
| A-11 | 与页面联调的 API 地址（与 #11 共同确定） | UI-01—UI-12、第 8 章“前端启动”“页面访问” | 归属 #10/#11（[04 第 3.2 节](04-development-and-runbook.md)） |

## 12. Issue #13 完成检查表

提交 PR 前逐项确认：

- [ ] `docs/06-test-and-acceptance.md` 已创建，成为岗位5后续 M1 验收的单一正式入口，未创建其他重复验收文档
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
- [ ] 除 `docs/06-test-and-acceptance.md` 外未修改任何其他正式文件；`verify_sparcs_mvp.py` 仅只读运行，未修改上游脚本或 fixture

## Issue #25 页面正式接口适配记录

本节记录 #25 的正式接口适配、浏览器复核和下游交接结果。#25 使用 #10 已冻结的契约；Mock 证据只证明状态触发，不替代真实 API 证据。

### 已实现的正式边界

- 默认模式请求 `GET /api/v1/diseases/top10`，不附加查询参数和请求体；
- 页面只消费 `data.items` 的原始顺序，不重新聚合、排序、截断 TOP10，也不连接 MySQL/HDFS；
- 成功态逐项展示 `rank`、`diagnosis_name`、`case_count`，并展示 `unit`、`data_version`、`generated_at`；
- `200 + data.items=[]` 显示 empty；非 2xx 按稳定 `code` 显示安全错误和重试入口；请求未结束时显示 loading 且清空旧结果；
- 长诊断名称坐标轴可省略，悬浮提示保留完整名称；窗口变化只触发图表 resize，不改变 API 顺序；
- Mock 只有显式设置 `VITE_TOP10_MODE=mock` 才启用，不能作为真实 API 或全链路证据。

### 实际联调结果

- 后端 `python -m pytest -q backend/tests`：`12 passed`；
- 使用本机 `backend/.env` 的 MySQL 模式启动 Flask 后，`GET http://127.0.0.1:5000/api/v1/diseases/top10` 返回 `HTTP 200`、`code=OK`、10 项，`unit=discharge_records`；
- 真实批次为 `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，页面展示的 `data_version` 与 API 响应一致；
- 前端执行 `npm ci` 后 `npm run build` 通过；正式模式页面截图和 DOM 复核均显示“正常”、10 项图表、病例量单位和真实批次；控制台无 error/warning；
- 页面源码检查确认请求层只发 GET、无 body，`App.vue` 没有本地聚合、排序、截断或数据库连接。

### 可复查命令

后端：

```powershell
cd backend
python -m pytest -q
python run.py
```

前端正式模式：

```powershell
cd frontend
npm ci
npm run build
npm run dev
```

前端 Mock 状态复现：

```powershell
$env:VITE_TOP10_MODE='mock'
$env:VITE_TOP10_MOCK_STATE='success'
npm run dev
```

页面上的状态按钮可以复现 `loading`、`success`、`empty`、`error`；错误态点击“重新加载”后恢复 success。正式 success 证据必须同时核对 API 响应、页面截图和 `data_version`，并与 Mock 批次区分。

### #25 验收矩阵执行结果

| 编号 | 检查项 | 实际动作与结果 | 证据 | 状态 |
|---|---|---|---|---|
| UI-01 | loading | Mock 点击 loading，显示加载提示且不保留旧图表 | 浏览器 DOM：`数据加载中……` | PASS |
| UI-02 | 真实 success | MySQL API 返回 200/10 项，页面显示真实名称、数量、单位和版本 | API 响应 + 正式页面 DOM/截图 | PASS |
| UI-03 | 合法 empty | Mock 点击 empty，显示“暂无可展示数据”，不显示空坐标轴 | 浏览器 DOM + Mock 状态 | PASS |
| UI-04 | error 与 retry | Mock 点击 error 显示 `DATABASE_UNAVAILABLE`，点击重试恢复 success | 浏览器 DOM + 重试后的 success 状态 | PASS |
| UI-05 | 字段与单位 | `rank`、名称、`case_count`、`unit`、`data_version` 和 `generated_at` 与响应一致；病例量文案为有效住院出院记录 | API 响应 + 页面 DOM | PASS |
| UI-06 | 长名称、并列与窗口 | Tooltip 显示完整长名称；Mock 并列项顺序保持 API 顺序；390px/1280px 均无横向溢出，图表正常 resize | Tooltip DOM + 窗口尺寸复核：`scrollWidth` 等于 `clientWidth` | PASS |
| UI-07 | 前端边界 | 检查请求层、页面源码和浏览器控制台；未发现重算、直连、假数据冒充或控制台错误 | `frontend/src/api/diseaseTop10.js`、`frontend/src/App.vue`、浏览器日志 | PASS |
| UI-08 | 文档与交接 | 启动命令、Mock 步骤、真实批次和已知限制已记录，结果交给 #26 做 M1 最终验收 | 本节、`frontend/README.md`、#26 交接评论 | PASS |

### #25 交接检查

| 检查项 | 证据位置 | 结论 |
|---|---|---|
| 请求方法和 URL | `frontend/src/api/diseaseTop10.js`、真实 API 请求 | PASS |
| 四态与重试 | `frontend/src/App.vue`、浏览器 Mock 状态步骤 | PASS（Mock 状态触发）；真实 success 已单独复核 |
| 字段、单位和批次 | 真实 API 响应、正式页面 DOM/截图 | PASS |
| 长名称、并列和窗口 | Tooltip DOM、Mock 顺序、390px/1280px 尺寸复核 | PASS |
| 不重算、不直连、不冒充 Mock | 前端源码、正式模式页面和控制台日志 | PASS |
| 下游 #26 交接 | Issue #26 评论 | PASS（#26 继续负责 M1 最终全链路验收） |

### 已知限制与下游边界

- Mock 状态按钮只用于可控复现 loading/empty/error，不代表真实数据链路；
- #25 不宣称 M1 全链路通过，真实数据与页面的一致性还由 #26 在其验收范围内复验；
- 本 Issue 不增加筛选、登录、AI、自由查询或其他指标页面。

## Issue #26 M1 最终验收执行记录

本节是 #26（补全并执行 M1 TOP10 全链路验收）的执行结论。执行时间 2026-08-18T06:34Z—06:49Z（UTC），git HEAD `3ca67c978453ea40cda4cfcffa931e9f88c4a753`，分支 `test/26-m1-final-acceptance`（与 main 同提交）。

### 验收基线

- 本机：Windows 11、Python 3.11.15（conda `csupy311`）、PySpark 3.4.0、pytest 9.1.1、Flask 3.1.3、PyMySQL 2.2.8；**无 Node.js/npm**；
- 真实数据版本：`sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`（#31 记录级）；
- 上游状态：#10 closed（契约 `FROZEN`）、#25 closed、#31 closed（GitHub API 快照 2026-08-18T06:31Z）；
- 完整基线见 `evidence/26/baseline/baseline.md`。

### 逐层执行结果

| 层 | 用例范围 | 本机执行 | 结论 |
|---|---|---|---|
| L1 固定样本 | L1-01、L1-02（DT 口径规则样例随 L1-01 覆盖） | `verify_sparcs_mvp.py` 与 `verify_service_result_contract.py` 均退出码 0、`status=PASS`；计数摘要、TOP10、契约边界样例与期望完全一致 | `PASS`（本机复现） |
| L2 数据任务 | DT-01—DT-09（固定样例路径）、DT-10 重复执行 | 本机 PySpark 3.4.0 两次运行固定样例：`status=PASS`、计数摘要一致、TOP10 完全一致；服务结果工件契约核对与 `publish_top10_mysql.py` dry-run 均 `PASS`；winutils/native-hadoop 警告为 docs/04 认可的预期边界 | `PASS`（本机复现） |
| L2 真实全量 | 真实 CSV 全量任务、MySQL `--apply`、回滚演练 | 本机无完整 CSV、hadoop001:3306 不可达、无 MySQL 凭证 → `NOT RUN（本机）`；#31 Resolution 与评论为记录级证据（两次复跑一致、10 行装载、1264 回滚后旧批次保留） | `PASS`（记录级，#31）；本机 `BLOCKED` |
| L3 Flask API | API-01—API-04、健康检查 | `python -m pytest -q` → `12 passed in 0.08s`；实际 HTTP 逐项命中：200/10 项、200 合法空、400 参数、400 请求体、405 POST/PUT/DELETE、404、500 配置缺失（3 种构造）、503 数据库不可用；`RESULT_NOT_READY`/`SERVICE_RESULT_INVALID`/`INTERNAL_ERROR` 由 pytest 覆盖（本机无法构造真实 MySQL 空表） | `PASS`（本机复现） |
| L3 真实 MySQL 模式 | 真实批次 HTTP 200 | 本机 `BLOCKED`（hadoop001 不可达）；#31 Resolution、#10 评论 02:59:05Z 为记录级证据 | `PASS`（记录级） |
| L4 页面 | UI-01—UI-12 | 本机无 Node.js：运行时四态 `BLOCKED`（#25 Resolution 为记录级证据：四态、重试、长名称 Tooltip、并列、390px/1280px、控制台无 error/warning 全部 PASS）；本机完成源码静态核对：不重算、不直连、只发 GET 无 body、Mock 显式开关、单位文案正确 | `PASS`（本机源码核对 + 记录级）；运行时 `BLOCKED（本机）` |
| L5 端到端/组长电脑 | 一致性矩阵、docs/06 第 8 章 checklist | 本机无法访问组长环境 → `BLOCKED/HANDOFF`；#31/#25 已记录组长电脑全链路实机结果（数据→MySQL→API→页面一致）；复现命令与证据位置见 `evidence/26/l5-e2e/real-mysql-handoff.md` | `PASS`（记录级，#31/#25）；本轮组长复现 `HANDOFF` |

### Issue #26 验收标准逐项结论

| # | 验收标准 | 结论 | 依据 |
|---|---|---|---|
| 1 | 固定样本有明确期望结果，独立核对可以复现 | `PASS` | 本机 L1-01/L1-02 复现（evidence/26/l1-fixture/） |
| 2 | 数据任务可以重复执行并得到一致结果，清洗和排序符合 #7 | `PASS` | 本机 PySpark 固定样例两次一致（evidence/26/l2-data-task/DT-sample/）；真实全量两次一致为 #31 记录级 |
| 3 | 服务结果、API 响应和页面展示的名称、数量、排名和单位一致 | `PASS` | 本机：mock/backend fixture/期望 JSON/实际 API 响应逐项一致（evidence/26/l3-api/）；真实批次一致性为 #31/#25 记录级 |
| 4 | API 四类情况全部有实际请求、响应、状态码和证据 | `PASS` | 本机实际 HTTP 全覆盖（evidence/26/l3-api/API-01—API-04）；真实 MySQL 模式记录级 |
| 5 | 页面四态全部验证，正式页面没有使用固定数据冒充真实 API | `PASS` | 四态为 #25 记录级；本机源码核对确认 Mock 仅显式启用、正式模式只请求 API |
| 6 | 组长电脑能够按文档重新运行完整链路 | `HANDOFF` | #31/#25 已记录组长电脑实机全链路结果（记录级）；#26 本轮在组长电脑的重新运行与证据归档待执行（evidence/26/l5-e2e/real-mysql-handoff.md） |
| 7 | 所有阻塞问题已修复并复验，或明确记录为未通过 | `PASS` | 本轮未发现 FAIL 项；无未修复阻塞问题 |
| 8 | 验收文档、问题记录、截图和运行证据已进入 Git 或在 Issue 中可复查 | `PASS`（部分 `HANDOFF`） | 本文件与 `evidence/26/**` 进入 Git；页面截图位于 #25 记录（Issue 可复查）；组长电脑本轮截图待归档 |
| 9 | 完成 Resolution 后才能关闭本 Issue，并向 #3 回写一句话结论 | `HANDOFF` | 本轮不关闭 Issue（按 #26 执行要求）；Resolution 与关闭动作待组长电脑复现归档后进行 |

### 本轮发现的环境事实（非缺陷）

- 本机 `JAVA_HOME` 默认指向 JDK 21，与 PySpark 3.4.0 不兼容；改用 PATH 中的 Temurin JDK 17 后固定样例任务正常。组长电脑按 docs/04 使用 Java 1.8 基线，不受影响；如需在本机复跑 PySpark，需先切换 JDK（已写入 evidence/26/execution-record.md）。
- PySpark Windows 下输出 `winutils.exe`/native-hadoop 警告，退出码 0 且结果一致，属 docs/04 认可的预期边界。

### M1 最终结论

**`BLOCKED`（无 FAIL；本机可复现层全部 PASS）**。

- L1 数据与固定样本、L2 数据任务（固定样例路径）、L3 Flask API 四类语义已在本机独立复现并通过；
- L4 页面运行时与 L5 真实 MySQL/组长电脑全链路在本机不可复现（无 Node.js、hadoop001 不可达、无完整 CSV 与 MySQL 凭证），其证据引用 #31/#10/#25 记录级证据，各环节均已 PASS；
- 剩余动作：由王敬博在组长电脑按 `evidence/26/l5-e2e/real-mysql-handoff.md` 重新运行完整链路并归档截图与同刻 API 响应，完成后 M1 可宣布 `PASS`，并写 Resolution、关闭本 Issue、向 #3 回写一句话结论。

### 证据索引

- 基线：`evidence/26/baseline/baseline.md`
- 执行命令与结果全文：`evidence/26/execution-record.md`
- L1：`evidence/26/l1-fixture/L1-01/`、`evidence/26/l1-fixture/L1-02/`
- L2：`evidence/26/l2-data-task/DT-sample/`、`evidence/26/l2-data-task/DT-contract/`
- L3：`evidence/26/l3-api/API-01/`、`API-02/`、`API-03/`、`API-04/`、`pytest-output.txt`
- L4：`evidence/26/l4-page/frontend-runtime-handoff.md`
- L5：`evidence/26/l5-e2e/real-mysql-handoff.md`
- Issue 状态快照与评论索引：`evidence/26/issue-references.md`
