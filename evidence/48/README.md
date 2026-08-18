# Issue #48 执行证据：医院运营分析后端接口

执行日期：2026-08-19（Asia/Shanghai）。本证据只记录接口、校验、故障语义和下游交接；真实 CSV、数据库密码和本地 `.env` 不进入 Git。

## 交付内容

- `backend/app/services/analytics_snapshot.py` 继续作为统一 `AnalyticsSnapshotService.get(module_key, entity_key)` seam；fixture 与 MySQL adapter 不在路由层分叉。
- `backend/app/routes/analytics.py` 为医院接口增加严格 GET-only/无请求体边界、重复参数拒绝、机构字段的安全错误详情、固定 metric 白名单、A/B 冲突拒绝，以及合法但未发布 profile 的 `200` 空结果语义。
- `backend/app/repositories/analytics_snapshot.py` 将已建立连接后读取到的损坏 `payload_json` 映射为 `SERVICE_RESULT_INVALID`，不误报配置缺失。
- `docs/05-api.md` 补充医院请求、实体键、响应扩展、空/错误语义、示例和真实切换命令。

## 验收矩阵

| 编号 | 状态 | 证据 |
|---|---|---|
| A-01 请求白名单 | PASS | `backend/tests/test_analytics_api.py` 覆盖未知、重复、非法枚举、相同 A/B 和六个合法 metric |
| A-02 正常与空 | PASS | [`fixture-smoke.json`](l3-api/fixture-smoke.json)；单院/双院顺序与完整 profile 原值对照；未发布 profile 的 `metrics/sections/comparison=[]` 测试 |
| A-03 失败映射 | PASS | 测试覆盖 GET body、HEAD/OPTIONS/POST、模块未发布、数据库不可用、损坏 payload、MySQL 配置缺失；响应不含内部异常文本 |
| A-04 读取 seam | PASS | 路由只使用 `AnalyticsSnapshotService`，MySQL 查询为绑定参数的 `analysis_snapshot_result` 只读查询；`compileall` 与 `git diff --check` 通过 |
| A-05 真实联调 | PASS | 上游真实 MySQL/API 记录见 [`evidence/39`](../39/README.md)；医院 206 行发布与逐项一致性见 [`evidence/47`](../47/README.md)；医院索引、单院、双院真实页面请求摘要见 [`real-api-summary.json`](l3-api/real-api-summary.json) |
| A-06 下游交接 | PASS | `docs/05-api.md` 与 `docs/07-terminal-product-contract.md` 对齐；#49 使用 `comparison`、字符串 `facility_id`、原顺序和原单位 |

## 自动化结果

```text
python -m pytest backend/tests data/tests -q
45 passed, 1 skipped in 0.70s
```

完整输出见 [`pytest-output.txt`](l3-api/pytest-output.txt)。`skipped` 是数据依赖环境相关测试，不是医院接口失败。

## 真实数据边界

真实医院快照的 `data_version` 为
`sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，医院索引 1 条、画像 205 条，共 206 条医院快照；MySQL 发布后医院 payload 不一致数为 0。接口证据沿用已完成的真实数据/API运行记录，fixture 仅用于确定性边界和故障测试。

## 下游交接

前端调用：

- 无筛选：`GET /api/v1/hospitals`；
- 单院：`GET /api/v1/hospitals/{facility_id}`；
- 比较：`GET /api/v1/hospitals?facility_a=<string>&facility_b=<string>&metric=<allowed-key>`。

前端不得重算、排序、截断、换单位或执行快照中的配置；错误按 HTTP 状态和 `code` 判断，并可使用 `trace_id` 反馈重试。
