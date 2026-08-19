# Issue #52 执行证据：疾病画像分析后端接口

执行日期：2026-08-19（Asia/Shanghai）。本证据只记录接口契约、确定性测试和真实链路边界；真实数据库密码、未提交 `.env` 和原始住院明细不进入 Git。

## 交付内容

- `backend/app/routes/analytics.py` 通过 `AnalyticsSnapshotService` 读取 `diseases/index` 与 `diseases/profile:{diagnosis_code}`，不在路由中重新聚合、排序、截断、换单位或修补 payload。
- 合法诊断枚举但 profile 尚未发布时返回 `200 OK` 的版本化空结果；疾病索引未发布、数据库不可用、快照损坏分别映射到 `RESULT_NOT_READY`、`DATABASE_UNAVAILABLE`、`SERVICE_RESULT_INVALID`。
- fixture 的疾病索引保留 10 项 TOP10；画像样例覆盖记录数、住院时长、收费、成本、急诊率，以及年龄、性别、严重程度、死亡风险、常见操作和医院分区。
- `docs/05-api.md` 已同步实体键、参数来源、成功/空/错误语义和调用约束。

## 验收矩阵

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| A-01 | 索引、画像正常响应与批次元数据 | PASS | `backend/tests/test_disease_analytics_api.py`；TOP10 10 项、`data_version/generated_at` 存在且 profile 与 index 一致 |
| A-02 | 画像实体键与必需分区 | PASS | 专项测试确认调用顺序为 `diseases/index`、`diseases/profile:NVS005`，并确认六个分区顺序 |
| A-03 | 合法空结果 | PASS | 合法 `INF012` profile 缺失时返回 200，保留 filters、标题/描述、版本和时间，metrics/sections 为空 |
| A-04 | 非法请求与安全错误 | PASS | 专项测试及 `backend/tests/test_analytics_api.py` 覆盖未知参数、非法枚举、重复参数、请求体、HEAD/OPTIONS/POST/PUT/DELETE、依赖失败和损坏 payload |
| A-05 | 快照契约与后端回归 | PASS | fixture contract PASS；`backend/tests` 49 passed；`compileall` 和 `git diff --check` PASS |
| A-06 | 真实 MySQL/API 联调 | PASS | `ANALYTICS_DATA_SOURCE=mysql` 下索引、全部 477 个合法画像、兼容 TOP10 和 MySQL payload 对照均通过；未使用 fixture 冒充真实成功 |

## 自动化结果

```text
python -m pytest backend/tests/test_analytics_api.py -q
24 passed in 0.50s

python -m pytest backend/tests/test_disease_analytics_api.py -q
7 passed in 0.17s

python -m pytest backend/tests -q
49 passed in 0.61s

python -m pytest data/tests -q -k not pyspark_disease_snapshot_matches_independent_verifier
11 passed, 2 skipped, 1 deselected in 0.18s

fixture contract PASS records=13

真实 MySQL/API 验证：

```text
GET /api/v1/diseases                         200 OK
diagnosis options                            477
GET /api/v1/diseases/{each legal code}       477/477 PASS
GET /api/v1/diseases/BLD001                  200 OK
GET /api/v1/diseases/top10                   200 OK
MySQL payload vs API payload                 PASS
invalid/query/body/method contract           PASS
```

合并 #55 后的完整 `backend/tests data/tests` 还会触发一个与 #52 无关的 PySpark 子进程测试；当前 bundled Python 环境没有 `pyspark`，该测试返回 `ModuleNotFoundError`。疾病后端专项和真实 MySQL/API 验收不依赖该环境，已分别通过；未修改数据测试来掩盖该限制。

## 真实快照边界

真实快照与 MySQL/API 使用同一 `data_version`：`sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`；生成时间为 `2026-08-18T11:11:56.038631Z`。真实数据库索引包含 477 个诊断选项，全部 477 个合法 profile 均返回 200，画像分区顺序为 age、gender、severity、mortality、procedures、hospitals；直接读取的 MySQL payload 与 API data 逐项一致。合法未发布空结果仍由 fixture 专项测试覆盖，真实批次没有缺失 profile。

## 下游交接

- 疾病列表：`GET /api/v1/diseases`。
- 疾病画像：`GET /api/v1/diseases/{diagnosis_code}`，编码只能来自 `diseases/index.options.diagnoses`。
- 历史兼容 TOP10：`GET /api/v1/diseases/top10`，继续遵守原有 M1 契约。
- 下游按 HTTP 状态和 `code` 判断错误；可使用 `trace_id` 反馈问题，不得重算、排序、截断、换单位或执行快照中的配置。

## 关闭状态

代码已合入 `main`，fixture/真实 MySQL 测试、文档和安全边界均完成。关闭前还需在 #50 发布独立 Resolution，记录本证据、主干提交和真实 `data_version`，再关闭 #52。
