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
| A-05 | 快照契约与回归 | PASS | fixture contract PASS；`57 passed, 1 skipped`；`compileall` PASS；`git diff --check` PASS |
| A-06 | 真实 MySQL/API 联调 | BLOCKED | 当前配置的数据库端口不可达，API 返回 `503 DATABASE_UNAVAILABLE`；未将 fixture 或本地生成快照冒充真实 MySQL 通过 |

## 自动化结果

```text
python -m pytest backend/tests/test_analytics_api.py -q
24 passed in 0.50s

python -m pytest backend/tests/test_disease_analytics_api.py -q
7 passed in 0.17s

python -m pytest backend/tests data/tests -q
57 passed, 1 skipped in 1.07s

fixture contract PASS records=13
```

## 真实快照边界

本机已有真实数据生成的未提交快照工件，契约校验结果为 PASS：`data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`、`generated_at=2026-08-18T11:11:56.038631Z`、疾病索引 478 条、疾病画像 477 条、样例画像六个分区。该工件证明生成结果可通过快照契约，不等于 MySQL/API 已完成真实联调。

解除数据库阻塞后，需要在 `ANALYTICS_DATA_SOURCE=mysql` 下重复疾病索引、合法诊断画像、合法空画像、非法诊断、请求体/方法错误和数据库故障场景，并逐项对照同一 `data_version`、`generated_at` 与 MySQL payload。

## 下游交接

- 疾病列表：`GET /api/v1/diseases`。
- 疾病画像：`GET /api/v1/diseases/{diagnosis_code}`，编码只能来自 `diseases/index.options.diagnoses`。
- 历史兼容 TOP10：`GET /api/v1/diseases/top10`，继续遵守原有 M1 契约。
- 下游按 HTTP 状态和 `code` 判断错误；可使用 `trace_id` 反馈问题，不得重算、排序、截断、换单位或执行快照中的配置。

## 关闭状态

代码、fixture 测试、文档和安全边界已完成；真实 MySQL 联调仍是关闭前唯一未完成项。数据库恢复后复跑 A-06，并由主责在 #50 发布独立 Resolution 后关闭 #52。
