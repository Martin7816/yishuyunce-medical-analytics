# `/overview` 页面覆盖

## Purpose

运营驾驶舱回答整体病例量、机构数、住院时长、收费/成本和结构分布问题。它是标准模式和大屏模式的同一入口。

## Standard layout

```text
页面标题 + “住院出院记录群体统计”边界 + data_version
└─ 4 KPI：病例量 / 医疗机构 / 平均住院时长 / 平均收费或成本
   ├─ 年龄结构 bar          ├─ 支付方式 bar
   ├─ 医院病例量 TOP10 bar  └─ 病情严重程度 bar
   └─ 数据质量 status + 确定性摘要 + 版本/生成时间
```

## Stage layout

同一组 KPI 和 section 以 12 列栅格重排：KPI 四列、主结构图两列、状态和摘要一列；不增加趋势、地图、关系图或大屏专属指标。`display=stage` 只是待 #107 实现的展示状态建议。

## Interaction and states

- 图表标题写清病例量/比例和单位；没有时间字段，不显示“增长”“趋势”；
- 从医院、疾病或风险相关 section 下钻时使用显式链接，并保留来源版本；
- fixture 快照显示“仅联调，不代表真实数据结论”；loading 不保留上一轮图；empty/error 保留边界和重试/清空动作；
- 1440px stage 与 390px mobile 都优先保留 KPI、主结论摘要和 table fallback。
