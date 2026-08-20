# Issue #67 支付方式分析数据快照证据

## 结论

Issue #67 的支付方式快照已完成实现、固定样例验收、真实全量独立核对和
`analysis_snapshot_result` 事务发布。真实发布使用完整快照文件，因此保留了已验收的
其他模块，并将 `payments` 从单一 wildcard 记录扩展为 wildcard 与全部有限组合。

## 实现与契约

- 生产聚合：`data/src/run_full_analytics_pyspark.py`
  - 复用 #39 的统一清洗帧，不重新读取或去重患者。
  - 使用 `Payment Typology 1` 和 `Age Group`；金额只接受可解析、非负的 `Total Charges`。
  - 输出 `payment=*|age=*` 与所有 `payment_type × age_group` 组合；合法空组合保留空
    `metrics`/`sections`。
  - 支付结构、支付方式平均收费、年龄结构、主要疾病四个 section 使用稳定排序；疾病严格
    TOP10，空支付值计入 wildcard 分母但不进入支付方式排行。
  - 中位数固定使用 `percentile_approx(charges, 0.5, 10000)`。
- 独立校验：`data/src/verify_payment_snapshot.py`
  - 只用 Python 标准库流式读取 CSV，独立重算完整键矩阵、计数、均值、排行和金额中位数秩误差。
- MySQL 核对：`data/src/verify_payment_mysql.py`
  - 核对 payment 行、完整快照总行数、payload、`data_version` 和 `generated_at`。
- 产品契约：`docs/07-terminal-product-contract.md`。
- 测试：`data/tests/test_payment_snapshot.py`；事务发布回滚覆盖在
  `data/tests/test_snapshot_publisher.py`。

## 固定样例

输入为 `data/fixtures/dashboard_edge_sample.csv`：4 行原始数据，3 行纳入统一清洗范围。

- `pytest -q data/tests/test_payment_snapshot.py`：`2 passed`
- 支付键：16；非空组合：10；空组合：6
- 独立支付快照核对：`PASS`
- 独立 dashboard 核对：`PASS`，`record_count=3`、`avg_charges=150.0`、`avg_los=42.0`
- 发布器 dry-run：`PASS`，该固定样例完整快照 62 行
- 发布器事务/回滚测试：`pytest -q data/tests/test_snapshot_publisher.py`，`8 passed`

## 真实全量

输入文件：`Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv`

- SHA-256：
  `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`
- 原始行数：`2,101,588`
- `data_version`：
  `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`
- 生成时间：`2026-08-19T00:00:00.000000Z`
- payment 选项：`payment_type=9`、`age_group=5`
- payment 键数：`60`；非空组合：`60`；空组合：`0`
- wildcard：`record_count=2,101,588`、`avg_charges=73,305.42`
- 独立全量核对：`data/src/verify_payment_snapshot.py` 返回 `PASS`；原始行数、SHA、版本、
  全部 60 个键、计数/均值/排行和 percentile approximate 中位数秩误差均通过。

全量临时快照位于本机 `D:\HuaDi\.codex_tmp\issue67-artifacts\issue67-final-snapshot.json`，
未把真实 CSV 或全量 JSON 提交到仓库。

## MySQL 发布与独立核对

发布命令：

```powershell
python data/src/publish_analytics_snapshot_mysql.py `
  --input D:\HuaDi\.codex_tmp\issue67-artifacts\issue67-final-snapshot.json --apply
```

发布结果：`PASS`，完整 `analysis_snapshot_result` 为 750 行；其中 `payments` 为 60 行。

独立核对命令：

```powershell
python data/src/verify_payment_mysql.py `
  --snapshot D:\HuaDi\.codex_tmp\issue67-artifacts\issue67-final-snapshot.json
```

核对结果：`PASS`，`total_rows=750`、`payment_rows=60`、`missing=0`、`extra=0`、
`payload_mismatch=0`、`distinct_data_versions=1`、`distinct_generated_at=1`。

核对使用的核心 SQL：

```sql
SELECT COUNT(*) AS n,
       COUNT(DISTINCT data_version) AS versions,
       COUNT(DISTINCT generated_at) AS timestamps
FROM analysis_snapshot_result;

SELECT module_key, entity_key, payload_json, data_version, generated_at
FROM analysis_snapshot_result
WHERE module_key = 'payments'
ORDER BY entity_key;
```

发布器先在一个事务中删除旧快照、插入完整快照并校验总行数/版本/时间戳；异常路径执行
rollback。固定测试中的 `8 passed` 覆盖该事务失败回滚行为。

## 下游交接

- #68 后端使用既有 `GET /api/v1/payments/overview`；允许查询参数
  `payment_type`、`age_group`，wildcard 请求对应 `payment=*|age=*`。
- #69 前端可直接消费固定的 `metrics` 与 `sections`：`payment`、`charges`、`age`、
  `diseases`；通过 `options.payment_type` 和 `options.age_group` 构造筛选器，并处理合法空
  组合的空 payload。
- 所有结果共享本证据中的 `data_version` 与 `generated_at`，不新增支付专用快照表或前端计算口径。
