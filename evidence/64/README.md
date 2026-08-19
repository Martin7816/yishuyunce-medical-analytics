# Issue #64 API 验收证据：病情严重程度与风险分析

执行日期：2026-08-19（Asia/Shanghai）。本目录只保存接口摘要；真实 CSV、快照 JSON、数据库凭证和密码不进入 Git。

## 实现范围

- 路由：GET /api/v1/risks/overview
- 白名单：age_group、diagnosis_code
- entity_key：age={值或*}|diagnosis={值或*}
- 读取 seam：AnalyticsSnapshotService.get(module_key, entity_key)
- 空组合：合法枚举但未发布时返回 200，metrics 和 sections 为空
- 错误：未知/重复/非法参数 400，GET 请求体 400，非 GET 方法 405，依赖/配置/契约错误分别映射为 503/500

## Fixture 验证

命令：

~~~powershell
python -m pytest -q backend/tests/test_analytics_api.py
~~~

结果：定向测试 56 passed；完整后端与数据回归 python -m pytest -q backend/tests data/tests 为 94 passed、5 skipped。跳过项是本机未启用的 PySpark 运行时测试。

独立测试覆盖无筛选响应、age_group 单筛选、diagnosis_code 单筛选、组合筛选、参数白名单、重复参数、Service seam、固定实体键顺序、合法空组合、RESULT_NOT_READY、DATABASE_UNAVAILABLE 和 SERVICE_RESULT_INVALID。

## 真实 MySQL API 验证

执行环境使用未提交的 backend/.env，ANALYTICS_DATA_SOURCE=mysql；只记录响应摘要，不输出凭据和住院明细。

| 场景 | 请求值 | HTTP/code | 结果 |
|---|---|---|---|
| 无筛选 | — | 200/OK | 5 个指标；section 顺序 severity、mortality、disposition、age、diseases；疾病 10 项 |
| 年龄筛选 | 0 to 17 | 200/OK | 版本保持一致，age section 1 项 |
| 诊断筛选 | BLD001 | 200/OK | 版本保持一致，diseases section 1 项 |
| 组合筛选 | 0 to 17 + BLD001 | 200/OK | 固定键 age=0 to 17|diagnosis=BLD001 |
| 合法空组合 | 0 to 17 + BLD009 | 200/OK | filters 保留，metrics=[]、sections=[] |
| 未知参数 | sql | 400/INVALID_QUERY_PARAMETER | details 仅含安全字段名 |
| 错误方法 | POST | 405/METHOD_NOT_ALLOWED | 非 GET 被拒绝 |
| GET 请求体 | JSON body | 400/INVALID_REQUEST_FORMAT | 请求体被拒绝 |

真实 API 的统一版本为 sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219，generated_at 为 2026-08-19T00:00:00.000000Z；options 为 5 个年龄枚举、477 个诊断编码。

## 与 #63 数据交接对照

风险快照已发布 2,868 个键，其中 2,614 个非空组合、254 个合法空组合；wildcard 记录数为 2,101,588，高风险 Major/Extreme 记录数为 700,276。底层独立核对、MySQL 逐键一致性和回滚证据见 ../63/README.md。

## 验收矩阵

| 编号 | 检查项 | 状态 | 证据 |
|---|---|---|---|
| A-01 | 请求白名单和枚举 | PASS | backend/tests/test_analytics_api.py；真实 unknown_query |
| A-02 | 无筛选、单筛选、组合和空结果 | PASS | fixture 测试；本文件真实 MySQL 表 |
| A-03 | 400/503/500 稳定错误且不泄密 | PASS | fixture 故障测试；真实错误方法/请求体 |
| A-04 | 路由只调用统一 Service | PASS | backend/app/routes/analytics.py；Service seam 测试 |
| A-05 | 真实快照版本、字段和 section 顺序 | PASS | 本文件真实 API 摘要；../63/README.md |
| A-06 | 下游交接 | PASS | docs/05-api.md；Issue #65 评论 |

## 下游交接

前端 #65 可调用 GET /api/v1/risks/overview；使用 data.filters 判断当前筛选，使用 data.data_version 和 data.generated_at 展示批次，按 data.metrics 与 data.sections 原顺序渲染。高风险数据只描述住院记录群体，不作个人诊断、治疗或因果判断。
