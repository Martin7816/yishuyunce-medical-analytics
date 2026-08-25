# SPARCS 数据与分析可行性

> 状态：`VERIFIED`
> 核验日期：2026-08-17
> 核验脚本：`data/src/inspect_sparcs_mvp.py`、`data/src/verify_sparcs_mvp.py`

## 1. 核验对象

核验对象是老师提供的 2021 年 SPARCS 住院出院数据文件：

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
| 疾病统计可用非空记录（排除 `LIVEBORN`/`活产儿`） | 1,900,940 |
| 疾病统计可用类别（排除 `LIVEBORN`/`活产儿`） | 476 |

数据中的一行按项目术语解释为一条住院出院记录，不等于唯一患者。项目不根据重复行删除记录；每一行按一次住院出院事件计数，具体规则见指标契约。

## 3. 关键字段核验

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

上表的诊断非空数量仍是原始输入质量口径；疾病分析在此基础上再排除 `LIVEBORN`/`活产儿`，因此疾病统计可用数量为 1,900,940 条、476 个类别。

`Length of Stay`、`Zip Code - 3 digits` 和 `Birth Weight` 不能直接对全部非空值强转整数。它们不参与疾病病例量 TOP10 分组；进入住院时长或费用分析时遵守对应模块的转换规则。

## 4. 排除非疾病标签后的疾病病例量 TOP10 全量侦察结果

按 `CCSR Diagnosis Description` 去除首尾空格、排除空值和非疾病标签 `LIVEBORN`（中文展示名为“活产儿”），逐条记录计数，并按病例量降序、疾病名称升序稳定排序后，独立核对与侦察脚本得到相同结果：

| 排名 | 主诊断描述 | 病例量 |
|---:|---|---:|
| 1 | SEPTICEMIA | 138,035 |
| 2 | CORONAVIRUS DISEASE 2019 (COVID-19) | 82,597 |
| 3 | HEART FAILURE | 58,562 |
| 4 | COMPLICATIONS SPECIFIED DURING CHILDBIRTH | 40,711 |
| 5 | DIABETES MELLITUS WITH COMPLICATION | 40,529 |
| 6 | ALCOHOL-RELATED DISORDERS | 39,326 |
| 7 | SCHIZOPHRENIA SPECTRUM AND OTHER PSYCHOTIC DISORDERS | 37,204 |
| 8 | OSTEOARTHRITIS | 35,562 |
| 9 | CARDIAC DYSRHYTHMIAS | 33,849 |
| 10 | CEREBRAL INFARCTION | 28,841 |

这里的“病例量”是满足统计条件的住院出院记录数量，不是患者人数。原始文件中的 199,014 条 `LIVEBORN` 记录仍保留在原始输入和数据质量统计中，但不进入疾病排行、疾病选项或疾病画像；以上结果构成排除非疾病标签后的侦察和独立复核基线。

## 5. 数据处理规则

下列规则用于疾病病例量 TOP10，完整字段、版本和边界说明见 [疾病病例量 TOP10 指标与数据契约](02-metrics-and-data-contract.md)。

1. 输入是一条住院出院记录一行的 CSV，正式范围为 `Discharge Year=2021`；
2. 疾病分组字段为 `CCSR Diagnosis Description`，代码字段只用于追溯；
3. 分组前去除首尾空白，缺失、空字符串和清洗后空白不参与 TOP10；
4. 清洗后名称为 `LIVEBORN` 或 `活产儿` 的非疾病标签不参与疾病统计，但原始行仍计入输入质量统计；
5. 每条符合条件的记录计数一次，不删除重复记录；
6. 按病例量降序排序，并列时使用清洗后疾病名称升序作为稳定次序；
7. 稳定排序后严格返回前 10 项，少于 10 项时返回全部；
8. `Length of Stay`、费用和其他字段不参与疾病病例量 TOP10 分组，字段异常不改变该指标的计数规则。

## 6. 固定脱敏样本与期望结果

`data/fixtures/sparcs_mvp_sample.csv` 是从同一份真实 CSV 选取的 16 条记录，仅保留 MVP 核验所需的 12 个字段，不包含完整原始列集或大文件。样本包含 1 条空诊断、2 条 `LIVEBORN` 非疾病标签、`Length of Stay=120 +`、`Zip Code - 3 digits=OOS` 和 `Birth Weight=UNKN`，用于复查缺失、排除和特殊值处理。

独立期望结果保存在 `data/fixtures/sparcs_mvp_expected_top10.json`。固定样本应有 13 条疾病统计可用非空诊断、11 个疾病统计可用诊断值，TOP10 如下：

| 排名 | 主诊断描述 | 病例量 |
|---:|---|---:|
| 1 | COMPLICATION OF OTHER SURGICAL OR MEDICAL CARE, INJURY, INITIAL ENCOUNTER | 2 |
| 2 | TRAUMATIC BRAIN INJURY (TBI); CONCUSSION, INITIAL ENCOUNTER | 2 |
| 3 | ACUTE MYOCARDIAL INFARCTION | 1 |
| 4 | ASTHMA | 1 |
| 5 | CORONAVIRUS DISEASE 2019 (COVID-19) | 1 |
| 6 | DIABETES MELLITUS WITH COMPLICATION | 1 |
| 7 | MULTIPLE SCLEROSIS | 1 |
| 8 | NONINFECTIOUS GASTROENTERITIS | 1 |
| 9 | PARALYSIS (OTHER THAN CEREBRAL PALSY) | 1 |
| 10 | PREVIOUS C-SECTION | 1 |

## 7. 可复查命令与结果

在仓库根目录执行固定样本和侦察脚本的独立核对：

```powershell
python data/src/verify_sparcs_mvp.py
```

预期输出顶层字段为 `"status": "PASS"`，并报告样本 `rows=16`、`malformed_rows=0`、`diagnosis_nonempty_rows=13`、`diagnosis_nonempty_distinct=11`。

在拥有本地完整 CSV 时，执行全量独立核对：

```powershell
python data/src/verify_sparcs_mvp.py --full-source "<本地 SPARCS CSV 路径>"
```

该命令使用独立计数逻辑读取样本或全量文件，再调用 `inspect_sparcs_mvp.py` 对同一输入进行比较；全量基线要求 2,101,588 行、0 条解析异常、原始非空诊断 2,099,954 条/477 个值，排除非疾病标签后为 1,900,940 条/476 个值，并与第 4 节 TOP10 完全一致。它不会修改原始文件，也不会把完整数据写入仓库。

## 8. 实现约束与数据风险

- 疾病病例量 TOP10 使用主诊断描述、2021 年范围、首尾空白清洗、排除 `LIVEBORN`/`活产儿`、不去重、稳定排序和严格十项截断；
- 年龄、性别和入院方式可用于住院记录群体筛选；
- 收费、成本和住院时长进入对应分析模块时遵守公共产品契约；
- 数据没有患者唯一 ID，一行只能解释为一次住院出院记录，不能用于患者跨次住院追踪；
- 固定样例用于逻辑验收，不代表全量分布；
- 完整原始 CSV、个人绝对路径、密钥和大型中间工件不得提交 Git；
- 全量基线只适用于文件名、大小和 SHA-256 都一致的原始文件。
