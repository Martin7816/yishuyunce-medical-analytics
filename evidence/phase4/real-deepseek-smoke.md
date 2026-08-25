# Phase 4 Real DeepSeek Smoke Test

Date: 2026-08-25

## Environment

- DeepSeek request: authorized real request; API key value not recorded
- Model: `deepseek-v4-flash`
- Aggregate source: MySQL through the existing SSH tunnel
- Active batch: `agg_11bb8c5caa79132304785ca2245c8a68cb1812687f2417f6`
- Database access: read-only during this test

## Transport compatibility fix

DeepSeek Chat Completions rejected `response_format.type=json_schema` with
`This response_format type is unavailable now`. The transport now sends the
provider-supported `json_object` mode while retaining the internal frozen
QueryPlan/Answer schemas and server-side validation.

## SSE cases

| Case | Result | Route/query | Evidence/provenance | Safety |
|---|---|---|---|---|
| Disease case-count ranking | PASS | Analytics Agent; `diagnosis` + `case_count` | `query_analytics`; complete provenance; bar chart | No SQL or internal reasoning exposed |
| Medicare average charges | PASS | Analytics Agent; `payment=Medicare` + `avg_charges` | `query_analytics`; complete provenance; bar chart | Cohort aggregate allowed |
| Individual patient charges | PASS (safe refusal) | Query not executed | No evidence attached | Patient-level request rejected |

All successful SSE responses returned HTTP 200 with the expected `stage`,
`delta`, and `done` events. Successful provenance included `batch_id`,
`data_version`, `formula_version`, and `registry_version`.

## Regression

- `314 passed`
- `1` pytest cache-permission warning; no test failure
- No database writes
- No commit
