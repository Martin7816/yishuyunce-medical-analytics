# Issue #60 执行证据：医疗费用与成本分析后端接口

执行日期：2026-08-19（Asia/Shanghai）。本证据只记录接口契约、确定性测试和脱敏的真实 MySQL/API 结果；数据库密码、未提交 `.env` 和原始住院明细不进入 Git。

## 交付内容

- `GET /api/v1/costs/overview` 仅负责参数白名单、枚举校验、固定实体键拼接和响应包装；快照读取统一经过 `AnalyticsSnapshotService`。
- `diagnosis_code` 与 `facility_id` 互斥，`severity` 可分别与任一维度组合；实体键固定为 `diagnosis={value}|facility={value}|severity={value}`。
- 已同步 `docs/05-api.md`，明确参数来源、空结果、错误映射、版本化响应和下游调用约束。

## 验收矩阵

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| A-01 | 请求白名单、枚举与固定实体键 | PASS | `backend/tests/test_analytics_api.py` 覆盖未知、重复、非法枚举、互斥参数、四类合法筛选和实体键顺序；`COST_FILTER_PARAMETERS` 与 `COST_ENTITY_DIMENSIONS` 为服务端固定定义 |
| A-02 | 正常结果与合法空结果 | PASS | fixture 覆盖无筛选、单维度、诊断+严重程度以及合法但未发布结果的 `200` 空 payload；真实库无筛选、诊断、机构、严重程度和诊断+严重程度均返回 `200 OK` |
| A-03 | 失败映射与安全边界 | PASS | fixture 覆盖 `RESULT_NOT_READY`、`DATABASE_UNAVAILABLE`、`SERVICE_RESULT_INVALID`、GET 请求体、HEAD/OPTIONS/POST 和未知/非法/重复参数；真实 API 的未知参数、非法枚举、互斥参数为 `400`，请求体为 `400`，POST 为 `405` |
| A-04 | 统一读取 seam | PASS | 路由通过 `AnalyticsSnapshotService` 读取；MySQL adapter 使用 `analysis_snapshot_result` 绑定参数只读查询；`compileall` 和 `git diff --check` 通过 |
| A-05 | 真实 MySQL/API 联调 | PASS | `192.168.57.138:3306/medical_analytics` TCP 可达，`SELECT 1` 成功；快照共 `4271` 行、单一版本、单一生成时间，costs 发布行 `3415`；基础 payload、`data_version` 和规范化 `generated_at` 与 MySQL 行一致 |
| A-06 | 下游交接 | PASS | `docs/05-api.md` 已同步；下游只调用 GET、消费原始 `metrics/sections` 和批次元数据，不重算、排序、截断或换单位 |

## 自动化结果

```text
python -m pytest -q backend/tests
68 passed in 0.57s

python -m pytest -q data/tests
11 passed, 3 skipped in 0.18s

python -m compileall -q backend/app backend/tests
PASS
```

## 真实 MySQL/API 摘要

真实批次：

- `data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`
- MySQL `generated_at=2026-08-19 00:00:00`；API 规范化为 `2026-08-19T00:00:00.000000Z`
- API 基础结果：`200 OK`，14 个 metrics，9 个 sections
- `diagnosis_code=BLD001`：`200 OK`，14 个 metrics，7 个 sections
- `facility_id=000001`：`200 OK`，14 个 metrics，7 个 sections
- `severity=Extreme`：`200 OK`，14 个 metrics，9 个 sections
- `diagnosis_code=BLD001&severity=Extreme`：`200 OK`，14 个 metrics，7 个 sections

当前真实快照的 477 个诊断、205 个机构和 4 个严重程度对应的诊断+严重程度、机构+严重程度组合均已发布，未发现真实库中的合法空组合；合法空响应由 fixture 专项测试确定性覆盖。用户提供的 `DB_*` 信息仅在本次进程内映射为应用所需的 `MYSQL_*` 配置，未写入或提交本地 `.env`。

## 下游交接

- 无筛选：`GET /api/v1/costs/overview`
- 诊断：`GET /api/v1/costs/overview?diagnosis_code=<diagnoses.value>`
- 机构：`GET /api/v1/costs/overview?facility_id=<facilities.value>`
- 严重程度：`GET /api/v1/costs/overview?severity=<severity>`
- 组合：诊断或机构与 `severity` 组合；`diagnosis_code` 和 `facility_id` 不可同时传入。

下游按 HTTP 状态和 `code` 判断错误，可使用 `trace_id` 反馈问题；不得将空结果当作数据库故障，也不得在前端重算或改写快照指标。
