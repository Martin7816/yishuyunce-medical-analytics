# SPARCS 数据与 MVP 可行性

> 状态：`DRAFT-INSPECTED`
> 核验日期：2026-08-15
> 核验脚本：`data/src/inspect_sparcs_mvp.py`

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
| `Discharge Year` | 2021 |
| `CCSR Diagnosis Description` 非空去重值 | 477 |

数据中的一行按项目术语解释为一条住院出院记录，不等于唯一患者。当前未根据重复行擅自删除任何记录；重复处理规则需要在指标契约中另行固定。

## 3. MVP 关键字段

| 原始列名 | 读取类型 | 缺失记录数 | 当前判断 |
|---|---|---:|---|
| `CCSR Diagnosis Description` | 文本 | 1,634 | 可作为疾病病例量 TOP10 的分组候选；空值暂不计入排行 |
| `CCSR Diagnosis Code` | 文本 | 1,634 | 与诊断描述缺失数一致，可用于结果追溯 |
| `Discharge Year` | 整数 | 0 | 全部为 2021 |
| `Age Group` | 文本 | 0 | 后续群体分析可用 |
| `Gender` | 文本 | 0 | 后续群体分析可用 |
| `Race` | 文本 | 0 | 后续群体分析可用 |
| `Ethnicity` | 文本 | 0 | 后续群体分析可用 |
| `Type of Admission` | 文本 | 0 | 后续入院方式分析可用 |
| `Length of Stay` | 混合 | 0 | 大多数为整数，另有 `120 +`，不能直接强转整数 |
| `Total Charges` | 数值文本 | 0 | 含千位逗号，清洗后可转金额数值 |
| `Total Costs` | 数值文本 | 0 | 含千位逗号，清洗后可转金额数值 |
| `Emergency Department Indicator` | 文本 | 0 | 可用于后续急诊比例统计 |

补充风险：`Zip Code - 3 digits` 有 45,062 个空值和 59,741 个 `OOS`；`Birth Weight` 有 1,894,731 个空值和 119 个 `UNKN`；`Permanent Facility Id` 有 10,642 个空值。这些字段不进入第一轮 TOP10 闭环。

## 4. 疾病病例量 TOP10 侦察结果

按 `CCSR Diagnosis Description` 去除首尾空格、排除空值、逐条记录计数后，当前全量侦察结果为：

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

这里的“病例量”是满足统计条件的住院出院记录数量，不是患者人数。以上结果是数据侦察结果，正式服务结果仍需经过固定小样本和独立方法核对。

## 5. 当前可采用的 M1 数据规则草案

1. 输入是一条住院出院记录一行的 CSV；
2. 疾病分组候选字段为 `CCSR Diagnosis Description`；
3. 分组前去除首尾空格，空值和空字符串暂不参与 TOP10；
4. 每条有效记录计数一次，不在规则确定前删除重复记录；
5. 按病例量降序排序；并列时使用疾病名称升序作为稳定次序；
6. 仅返回前 10 项，字段和 API 具体名称在指标契约中再固定；
7. `Length of Stay`、费用和其他字段先不进入第一轮分组逻辑。

## 6. 可复查命令

在仓库根目录执行：

```powershell
python data/src/inspect_sparcs_mvp.py "<本地 SPARCS CSV 路径>"
```

该脚本只读取原始文件并输出 JSON 摘要，不修改原始数据。下一步需要从真实文件制作可提交的小样本，并用独立脚本或 SQL 生成期望 TOP10，完成 #6 的最终验收证据。
