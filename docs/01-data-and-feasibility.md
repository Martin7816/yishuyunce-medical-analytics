# SPARCS 数据与 MVP 可行性

> 状态：`VERIFIED`
> 核验日期：2026-08-17
> 核验脚本：`data/src/inspect_sparcs_mvp.py`、`data/src/verify_sparcs_mvp.py`

## 1. 核验对象

本次读取的是老师提供的 2021 年 SPARCS 住院出院数据文件：

`Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv`

完整原始 CSV 保留在本地课件目录，不进入 Git。脚本通过命令行参数接收本地路径，因此不会依赖个人绝对路径。

## 2. 全量读取结果

| 项目 | 结果 |
|---|---:|
| 文件大小 | 832,373,138 bytes |
| 数据列数 | 33 |
| 数据记录数 | 2,101,588 |
| CSV 解析异常行 | 0 |
| 编码读取 | UTF-8，可正常读取 |
| `Discharge Year` | 全部为 2021 |
| `CCSR Diagnosis Description` 非空记录 | 2,099,954 |
| `CCSR Diagnosis Description` 非空去重值 | 477 |

数据中的一行按项目术语解释为一条住院出院记录，不等于唯一患者。当前未根据重复行擅自删除任何记录；重复处理规则需要在指标契约中另行固定。

## 3. MVP 字段核验

下表的“读取类型”是对原始文本读取后的实际值形态总结，不代表已经完成最终业务转换；“典型值/异常”来自全量扫描和固定样本。

| 原始列名 | 读取类型 | 非空数量 | 缺失数量 | 典型值/异常 |
|---|---|---:|---:|---|
| `CCSR Diagnosis Description` | 文本 | 2,099,954 | 1,634 | `CORONAVIRUS DISEASE 2019 (COVID-19)` 等；空值不参与排行 |
| `CCSR Diagnosis Code` | 文本 | 2,099,954 | 1,634 | `INF012`、`NVS005` 等 |
| `Discharge Year` | 整数 | 2,101,588 | 0 | `2021` |
| `Age Group` | 文本 | 2,101,588 | 0 | `70 or Older`、`50 to 69` |
| `Gender` | 文本 | 2,101,588 | 0 | `M`、`F` |
| `Type of Admission` | 文本 | 2,101,588 | 0 | `Emergency`、`Newborn`、`Trauma` |
| `Length of Stay` | 混合 | 2,101,588 | 0 | 大多数为整数；`120 +` 有 1,561 条 |
| `Total Charges` | 数值文本 | 2,101,588 | 0 | 含千位逗号，清洗后可转金额数值 |
| `Total Costs` | 数值文本 | 2,101,588 | 0 | 含千位逗号，清洗后可转金额数值 |
| `Emergency Department Indicator` | 文本 | 2,101,588 | 0 | `Y`、`N` |
| `Zip Code - 3 digits` | 混合 | 2,056,526 | 45,062 | 数值文本；`OOS` 有 59,741 条 |
| `Birth Weight` | 混合 | 206,857 | 1,894,731 | 数值文本；`UNKN` 有 119 条 |
| `Permanent Facility Id` | 整数 | 2,090,946 | 10,642 | 整数文本 |

`Length of Stay`、`Zip Code - 3 digits` 和 `Birth Weight` 不能直接对全部非空值强转整数。它们不进入第一轮疾病 TOP10 分组逻辑，后续使用时需要单独制定转换规则。

## 4. 疾病病例量 TOP10 全量侦察结果

按 `CCSR Diagnosis Description` 去除首尾空格、排除空值、逐条记录计数，并按病例量降序、疾病名称升序稳定排序后，独立核对与侦察脚本得到相同结果：

| 排名 | 主诊断描述候选 | 病例量 |
|---:|---|---:|
| 1 | LIVEBORN | 199,014 |
| 2 | SEPTICEMIA | 138,035 |
| 3 | CORONAVIRUS DISEASE 2019 (COVID-19) | 82,597 |
| 4 | HEART FAILURE | 58,562 |
| 5 | COMPLICATIONS SPECIFIED DURING CHILDBIRTH | 40,711 |
| 6 | DIABETES MELLITUS WITH COMPLICATION | 40,529 |
| 7 | ALCOHOL-RELATED DISORDERS | 39,326 |
| 8 | SCHIZOPHRENIA SPECTRUM AND OTHER PSYCHOTIC DISORDERS | 37,204 |
| 9 | OSTEOARTHRITIS | 35,562 |
| 10 | CARDIAC DYSRHYTHMIAS | 33,849 |

这里的“病例量”是满足统计条件的住院出院记录数量，不是患者人数。以上是当前这份原始文件的侦察和独立复核基线，正式服务结果仍需在后续数据任务中按同一契约生成。

## 5. 当前可供下游确认的规则草案

1. 输入是一条住院出院记录一行的 CSV；
2. 疾病分组字段为 `CCSR Diagnosis Description`；
3. 分组前去除首尾空格，空值和空字符串暂不参与 TOP10；
4. 每条有效记录计数一次，不在规则确定前删除重复记录；
5. 按病例量降序排序；并列时使用疾病名称升序作为稳定次序；
6. 仅返回前 10 项，字段和 API 具体名称在指标契约中固定；
7. `Length of Stay`、费用和其他字段先不进入第一轮分组逻辑。

## 6. 固定脱敏样本与期望结果

`data/fixtures/sparcs_mvp_sample.csv` 是从同一份真实 CSV 选取的 16 条记录，仅保留 MVP 核验所需的 12 个字段，不包含完整原始列集或大文件。样本包含 1 条空诊断、`Length of Stay=120 +`、`Zip Code - 3 digits=OOS` 和 `Birth Weight=UNKN`，用于复查缺失和特殊值处理。

独立期望结果保存在 `data/fixtures/sparcs_mvp_expected_top10.json`。固定样本应有 15 条非空诊断、12 个非空诊断值，TOP10 如下：

| 排名 | 主诊断描述 | 病例量 |
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

## 7. 可复查命令与结果

在仓库根目录执行固定样本和侦察脚本的独立核对：

```powershell
python data/src/verify_sparcs_mvp.py
```

预期输出顶层字段为 `"status": "PASS"`，并报告样本 `rows=16`、`malformed_rows=0`、`diagnosis_nonempty_rows=15`、`diagnosis_nonempty_distinct=12`。

在拥有本地完整 CSV 时，执行全量独立核对：

```powershell
python data/src/verify_sparcs_mvp.py --full-source "<本地 SPARCS CSV 路径>"
```

该命令使用独立计数逻辑读取样本或全量文件，再调用 `inspect_sparcs_mvp.py` 对同一输入进行比较；全量基线要求 2,101,588 行、0 条解析异常、477 个非空诊断值，并与第 4 节 TOP10 完全一致。它不会修改原始文件，也不会把完整数据写入仓库。

## 8. 对后续 Issue 的影响与仍存风险

- 对 #7：全量 TOP10 已有可复查的候选基线；空值排除、首尾空格清洗、重复记录和并列排序仍需在指标契约中正式确认，不能把本次侦察直接当作最终业务口径。
- 对 #9：`CCSR Diagnosis Description`、`CCSR Diagnosis Code`、`Discharge Year` 以及年龄、性别、入院方式等字段的真实列名、缺失数量和读取形态已可供数据表与接口契约使用；费用、成本和住院时长的转换规则仍需单独固定。
- 数据没有患者唯一 ID，一行只能解释为一次住院出院记录，不做患者跨次住院追踪。
- 本次不擅自删除重复、缺失或异常记录；完整原始 CSV、个人绝对路径、密钥和大型中间结果不提交 Git。
- 固定样本用于逻辑验收，不代表全量分布；全量基线只适用于文件名和文件大小均与本次核验一致的原始文件。
