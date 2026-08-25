# Phase 4 Analytics Agent E2E Record

Date: 2026-08-25

## Execution boundary

- Python: 3.11.15 (`csupy311`)
- Aggregate source: `MySQLAggregateQueryRepository`
- MySQL endpoint: SSH tunnel `127.0.0.1:3307`
- Read timeout: 30 seconds; connect timeout remains 3 seconds
- Planner: static test planner
- Answer client: deterministic structured mock
- DeepSeek: not called
- Database writes: none
- Runner: `backend/phase4_analytics_e2e.py`

Active aggregate provenance:

```text
batch_id        = agg_11bb8c5caa79132304785ca2245c8a68cb1812687f2417f6
data_version    = sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219
formula_version = aggregate-additive-v1
registry_version= aggregate-registry-v1
```

## Case results

### 1. Disease ranking

Question: `哪些疾病病例数量最多？`

Result: PASS. Route: `analytics_agent`. Capability: `aggregate_diagnosis`.

```text
PNL001 — LIVEBORN                                      199014
INF002 — SEPTICEMIA                                    138035
INF012 — CORONAVIRUS DISEASE 2019 (COVID-19)             82597
CIR019 — HEART FAILURE                                  58562
PRG023 — COMPLICATIONS SPECIFIED DURING CHILDBIRTH       40711
END003 — DIABETES MELLITUS WITH COMPLICATION             40529
MBD017 — ALCOHOL-RELATED DISORDERS                       39326
MBD001 — SCHIZOPHRENIA SPECTRUM AND OTHER PSYCHOTIC      37204
MUS006 — OSTEOARTHRITIS                                  35562
CIR017 — CARDIAC DYSRHYTHMIAS                             33849
```

Chart: `bar`. Evidence and answer retained the active provenance.

### 2. Age-group average length of stay

Question: `不同年龄段的平均住院时间是多少？`

Result: PASS. Route: `analytics_agent`. Capability: `aggregate_age_group`.

```text
70 or Older   6.7162
50 to 69      6.5518
30 to 49      4.8845
18 to 29      4.5702
0 to 17       4.0319
```

The Safe Evidence section preserved the whitelisted measure label `Average
length of stay`, allowing the grounded answer validator to verify the metric.
Chart: `bar`.

### 3. Medicare cohort average charges

Question: `Medicare 患者平均费用是多少？`

Result: PASS. This is a cohort aggregate query, not a patient-level query.

```text
plan dimensions = []
measure         = avg_charges
filter          = payment eq Medicare
average charges = 87975.991408
```

Chart: `bar`. The answer generator returned a grounded structured answer with
the same active provenance.

### 4. Gender × diagnosis distribution

Question: `不同性别疾病分布情况？`

Result: PASS as a safety refusal. The classifier routed the question to
`analytics_agent`, but the compiler rejected the unsupported
`gender + diagnosis` capability before repository execution.

```text
compiled_query = null
query_result   = null
chart          = null
answer         = safe refusal
```

## SSE verification

Successful cases and the safety-refusal case emitted the stable public stages:

```text
preparing → understanding → querying → analyzing → completed
```

Each stream ended with one `done` event and included `delta` output. No SQL,
planner reasoning, physical fields, or internal validation details were exposed.
