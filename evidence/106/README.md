# Issue #106 verification record

本目录记录 #106 的关系快照契约、生成和独立核对证据。完整全量快照保存在工作区外的 `D:\HuaDi\analytics-output\issue106-real-full.json`，没有复制进仓库。

## Contract and fixture

- `backend/app/fixtures/analytics_snapshot_success.json` 已包含 `facility_relation`、`facility_metric_comparison`、`cost_los_relation`、`age_severity_matrix` 和确定性 `insights`。
- `data/src/publish_analytics_snapshot_mysql.py --input backend/app/fixtures/analytics_snapshot_success.json` 通过契约校验。
- 契约拒绝未知 section 类型、任意 visual 字段、NaN/无穷大和嵌套版本漂移；API fixture tests 覆盖关系 section、版本和合法空结果。

## Edge sample

Input: `data/fixtures/dashboard_edge_sample.csv`

```text
run_full_analytics_pyspark.py -> PASS, 87 records
verify_relationships_snapshot.py -> PASS
raw_rows=4, scoped_rows=3, facility_points=1, cost_points=2, risk_matrices=8
```

The edge sample covers invalid money, invalid length of stay, `120 +`, missing severity, missing diagnosis, and legal empty combinations.

## Full source

Input:
`D:\HuaDi\课件\第二阶段\day09\Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv\Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv`

```text
run_full_analytics_pyspark.py -> PASS
raw_rows=2101588
records=7197
data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219
generated_at=2026-08-20T00:00:00.000000Z

verify_relationships_snapshot.py -> PASS
facility_points=50
cost_points=40
risk_matrices=2614
```

The independent verifier streams the source CSV with the standard library and recomputes the three relation outputs without importing the PySpark aggregation functions. It also checks the input SHA-256, raw row count, data version, P75 threshold, and snapshot contract.

The Flask fixture read path covered dashboard, hospitals, costs, risks, and a two-facility `avg_charges` comparison; the real MySQL read path is recorded below.

A full-snapshot legal-empty check also returned `200` with empty `metrics`, `sections`, and `insights` for `diagnosis=EAR004|facility=*|severity=Extreme`.

## Regression

```text
python -m pytest backend/tests data/tests -q
181 passed, 12 skipped
```

The tested run used the bundled pytest/PySpark environment with the existing data runtime's NumPy path. The skips are existing environment-dependent checks; the full generator and independent verifier were run explicitly with `D:\HuaDi\project\yishuyunce-medical-analytics\data\.venv\Scripts\python.exe`.

## MySQL/API gate

The full snapshot was published transactionally with `--apply` and passed the publisher's post-commit check:

```text
rows=7197
data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219
generated_at=2026-08-20T00:00:00.000000Z
```

The real MySQL readback reported `7197` rows, one `data_version`, and one `generated_at`. The published module counts were `hospitals=206`, `costs=3415`, and `risks=2868`; relationship payloads included the expected grouped-bar, scatter, and heatmap structures.

The Flask application was exercised with the MySQL repository using the full snapshot. `/api/v1/dashboard/overview`, `/api/v1/hospitals`, a two-facility `avg_charges` comparison, `/api/v1/costs/overview`, the legal-empty cost filter, and `/api/v1/risks/overview` all returned `200/OK`. Every response carried the same `data_version` and `generated_at`; hospitals returned two comparison profiles, costs exposed `scatter`, risks exposed `heatmap`, and the legal-empty response returned empty `metrics`, `sections`, and `insights`.
