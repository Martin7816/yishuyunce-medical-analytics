# Phase 4 Security Boundary

## Aggregate-only access

- The planner output contains only semantic dimensions, measures, filters,
  sort, and limit.
- The compiler emits a repository-neutral semantic object; it does not emit
  SQL, table names, joins, raw fields, or expressions.
- The repository generates SQL from server allowlists and reads only
  `analytics_aggregate_fact` for the fact query.
- QueryResult rows contain grouped dimensions and measures only.
- The public AI/SSE source removes the internal QueryPlan and keeps only Safe
  Evidence, chart metadata, and provenance.

## Patient privacy

Allowed:

- `Medicare 患者平均费用是多少？`
- cohort-level patient counts, distributions, and other supported aggregates

Rejected:

- individual patient cost or details
- patient IDs, MRN, SSN, names, or raw records
- diagnosis or treatment conclusions for an individual

The privacy boundary remains `aggregate_only`.

## Capability boundary

`gender + diagnosis` exists as semantic dimensions but is not an active
aggregate capability. It is rejected during compilation and produces no
repository call or fabricated evidence.

## Grounding boundary

- Numeric facts are copied from QueryResult rows.
- Diagnosis names are display metadata resolved only when its published
  `data_version` matches the QueryResult version; otherwise the code remains.
- Provenance is copied from the server result, never from the answer model.
- Unsupported, empty, unsafe, or insufficient-evidence paths fail closed.
