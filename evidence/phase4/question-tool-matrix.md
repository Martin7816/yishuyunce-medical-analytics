# Phase 4 Question / Capability Matrix

| Question | Classifier route | QueryPlan | Capability / outcome | Chart |
|---|---|---|---|---|
| 哪些疾病病例数量最多？ | `analytics_agent` | `diagnosis` + `case_count`, desc, limit 10 | `aggregate_diagnosis`, executed | `bar` |
| 不同年龄段的平均住院时间是多少？ | `analytics_agent` | `age_group` + `avg_los`, desc, limit 10 | `aggregate_age_group`, executed | `bar` |
| Medicare 患者平均费用是多少？ | `analytics_agent` | `avg_charges`, `payment=Medicare`, limit 1 | `aggregate_overall`, executed | `bar` |
| 不同性别疾病分布情况？ | `analytics_agent` | `gender + diagnosis` + `case_count` | unsupported capability, rejected before DB | `null` |

All successful QueryResults used the same active batch and carried:

```text
batch_id         agg_11bb8c5caa79132304785ca2245c8a68cb1812687f2417f6
data_version     sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219
formula_version  aggregate-additive-v1
registry_version aggregate-registry-v1
```
