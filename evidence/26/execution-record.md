# #26 本机实际执行命令与结果（可复现）

> 执行时间：2026-08-18T06:34Z—06:49Z（UTC）
> 环境：Windows 11 家庭中文版、Python 3.11.15（conda `csupy311`）、git HEAD `3ca67c9`
> 说明：PySpark 运行需 `JAVA_HOME` 指向 JDK 17（本机 `JAVA_HOME` 默认指向 JDK 21，与 Spark 3.4 不兼容；PATH 中 `java` 已是 Temurin JDK 17）。

## L1 固定样本与独立核对

```powershell
# L1-01
python data/src/verify_sparcs_mvp.py
# exit=0；status=PASS；contract_examples PASS；rows=16、malformed_rows=0、
# out_of_scope_rows=0、diagnosis_nonempty_rows=15、diagnosis_nonempty_distinct=12，
# sample.top10 与期望 JSON 完全一致
# 证据：evidence/26/l1-fixture/L1-01/verify-sparcs-mvp-stdout.json

# L1-02
python data/src/verify_service_result_contract.py
# exit=0；status=PASS；data_version=fixture:sparcs_mvp_sample:v1；rows=10；unit=discharge_records
# 证据：evidence/26/l1-fixture/L1-02/verify-service-result-contract-stdout.json
```

## L2 数据任务（本机 PySpark 固定样例）

```powershell
$env:JAVA_HOME = "E:\Program Files\Eclipse Adoptium\jdk-17.0.20.8-hotspot"
$env:PYTHONIOENCODING = "utf-8"

# DT-01—DT-09 固定样例路径（正式任务口径在固定样例上核对）
python data/src/run_sparcs_top10_pyspark.py --input data/fixtures/sparcs_mvp_sample.csv `
  --expected data/fixtures/sparcs_mvp_expected_top10.json `
  --generated-at 2026-08-17T00:00:00Z `
  --output <tmp>\sample_service_result_artifact.json
# exit=0；status=PASS；engine=pyspark-local；pyspark_version=3.4.0；
# rows=16、malformed_rows=0、out_of_scope_rows=0、diagnosis_nonempty_rows=15、
# diagnosis_nonempty_distinct=12；TOP10 与期望一致
# stderr 仅含 winutils/native-hadoop 警告（docs/04 认可：退出码 0 且结果一致即可）
# 证据：evidence/26/l2-data-task/DT-sample/pyspark-sample-run1.json

# DT-10 重复执行一致性：同上命令，--generated-at 2026-08-17T01:00:00Z
# exit=0；两次运行 TOP10 与全部计数摘要完全一致（generated_at 按参数不同、data_version 相同）
# 证据：evidence/26/l2-data-task/DT-sample/pyspark-sample-run2.json

# 服务结果工件契约核对（模拟真实链路的产物检查）
python data/src/verify_service_result_contract.py --result <tmp>\sample_service_result_artifact.json --expected-scope sample
# exit=0；status=PASS；result_rows=10
# 证据：evidence/26/l2-data-task/DT-contract/artifact-contract-check-stdout.json

# 发布脚本 dry-run（不连接 MySQL 的完整契约校验路径）
python data/src/publish_top10_mysql.py --input <tmp>\sample_service_result_artifact.json
# exit=0；status=PASS；mode=dry-run；rows=10
# 证据：evidence/26/l2-data-task/DT-contract/publish-dry-run-stdout.json
```

本机未执行（标记 NOT RUN，记录级证据见 evidence/26/l5-e2e/real-mysql-handoff.md）：

- `--full-source <完整 CSV>`（本机无完整 CSV）
- `publish_top10_mysql.py --apply`（hadoop001:3306 不可达，且无 MySQL 凭证）

## L3 Flask API（实际 HTTP）

```powershell
cd backend
python -m pytest -q
# exit=0；12 passed in 0.08s
# 证据：evidence/26/l3-api/pytest-output.txt

python run.py   # 默认 fixture:success
```

| 用例 | 请求 | 实测 | 证据 |
|---|---|---|---|
| API-01 正常 | `GET /api/v1/diseases/top10` | 200；`code=OK`；10 项；`unit=discharge_records`；`fixture:sparcs_mvp_sample:v1`；`X-Trace-ID` 头与 `trace_id` 一致 | evidence/26/l3-api/API-01/api-200-success.json |
| API-02 合法空 | `TOP10_FIXTURE_STATE=empty` 启动 | 200；`items=[]`；`data_version`/`generated_at`/`unit` 仍在 | evidence/26/l3-api/API-02/api-200-empty.json |
| API-03 非法参数 | `GET ...?limit=5` | 400；`INVALID_QUERY_PARAMETER`；`details.parameters=["limit"]`；`data=null` | API-03/api_400_queryparam.json |
| API-03 请求体 | GET + JSON body | 400；`INVALID_REQUEST_FORMAT` | API-03/api_400_body.json |
| API-03 方法 | POST / PUT / DELETE | 405；`METHOD_NOT_ALLOWED` | API-03/api_405_*.json |
| API-03 路径 | `GET /api/v1/nonexistent` | 404；`RESOURCE_NOT_FOUND` | API-03/api_404.json |
| API-04 配置缺失 | `TOP10_DATA_SOURCE=mysql` 且无 MYSQL_HOST/USER/DATABASE | 500；`SERVER_MISCONFIGURED` | API-04/api_mysql_missing_config.json |
| API-04 配置损坏 | `TOP10_FIXTURE_STATE=bogus` | 500；`SERVER_MISCONFIGURED` | API-04/api_invalid_fixture_state.json |
| API-04 数据源非法 | `TOP10_DATA_SOURCE=bogus` | 500；`SERVER_MISCONFIGURED` | API-04/api_invalid_data_source.json |
| API-04 数据库不可用 | mysql 模式指向不可达实例（127.0.0.1:3306 probe 账号，连接失败） | 503；`DATABASE_UNAVAILABLE` | API-04/api_mysql_unreachable.json |
| 健康检查 | `GET /api/v1/health` | 200；`data.status=UP` | 本文件正文记录 |

仅由 pytest 覆盖、本机无法构造真实 HTTP 的语义（详见 pytest-output.txt）：

- `RESULT_NOT_READY`（503，需真实 MySQL 空表）→ `test_unpublished_result_is_not_misreported_as_empty`
- `SERVICE_RESULT_INVALID`（500，已发布结果违反契约）→ `test_invalid_published_result_is_rejected`
- `INTERNAL_ERROR`（500，异常不泄漏细节）→ `test_unexpected_exception_does_not_leak_details`

真实 MySQL 模式（真实批次 HTTP 200）本机 BLOCKED，记录级证据：#31 Resolution、#10 评论 02:59:05Z、#25 Resolution。

## L4 页面

本机无 Node.js/npm：运行时验收 BLOCKED/HANDOFF，静态源码核对 PASS。见 evidence/26/l4-page/frontend-runtime-handoff.md。

## L5 端到端 / 组长电脑

hadoop001 不可达、无完整 CSV、无 MySQL 凭证：BLOCKED/HANDOFF。见 evidence/26/l5-e2e/real-mysql-handoff.md。
