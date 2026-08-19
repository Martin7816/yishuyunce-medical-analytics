# 疾病病例量 TOP10 API 契约

> 终局更新（2026-08-18）：本文件原有 TOP10 契约保持兼容。完整产品接口共享相同响应信封，详细冻结边界见 [07-terminal-product-contract.md](07-terminal-product-contract.md)。

## 终局接口索引

| 方法 | 路径 | 成功数据 |
|---|---|---|
| GET | `/api/v1/dashboard/overview` | 总览指标与年龄、支付、疾病、医院、严重程度分区 |
| GET | `/api/v1/hospitals` | 医院排行，可选双院比较 |
| GET | `/api/v1/hospitals/{facility_id}` | 单院画像 |
| GET | `/api/v1/diseases` | 疾病 TOP10 与疾病枚举 |
| GET | `/api/v1/diseases/{diagnosis_code}` | 疾病画像 |
| GET | `/api/v1/cohorts/summary` | 有限白名单群体汇总 |
| GET | `/api/v1/costs/overview` | 费用成本与分位数 |
| GET | `/api/v1/risks/overview` | 严重程度与风险结构 |
| GET | `/api/v1/payments/overview` | 支付方式分析 |
| GET | `/api/v1/data-quality/summary` | 批次、缺失异常与管道状态 |
| GET | `/api/v1/models/high-cost/metrics` | 模型阈值、评估指标与混淆矩阵 |
| POST | `/api/v1/models/high-cost/predict` | 概率、分类、模型和数据版本 |
| POST | `/api/v1/ai/chat` | 回答、工具轨迹、来源指标、版本、预定义图表 |

预测请求只接受 `age_group`、`gender`、`race`、`ethnicity`、`hospital_service_area`、`facility_id`、`admission_type`、`emergency_indicator`。AI 请求只接受 `{"message":"..."}`。两者均拒绝额外字段；预测接口专门返回 `LEAKAGE_FIELD_FORBIDDEN` 拦截目标或出院后字段。

## 1.0 疾病画像接口（Issue #52）

疾病模块只读取统一快照服务，不在路由中读取 CSV、执行 SQL、重新聚合、排序、截断、换单位或修补空值。对应的快照实体键固定为：

| 请求 | 快照读取 | 请求约束 |
|---|---|---|
| `GET /api/v1/diseases` | `diseases/index` | 不接受查询参数或请求体 |
| `GET /api/v1/diseases/{diagnosis_code}` | 先读取 `diseases/index` 校验枚举，再读取 `diseases/profile:{diagnosis_code}` | `diagnosis_code` 必须来自 `index.options.diagnoses`，不接受查询参数或请求体 |
| `GET /api/v1/diseases/top10` | 历史 TOP10 服务结果 | 保持第 2—12 节的 M1 兼容契约 |

疾病索引的 `data` 是快照 payload 加上 `data_version`、`generated_at`，其中 `options.diagnoses` 是唯一允许的画像选择来源，`sections.top10` 保留上游已发布顺序。画像 payload 的指标至少覆盖住院出院记录数、平均住院时长、平均收费、平均成本和急诊率；分区覆盖年龄、性别、严重程度、死亡风险、常见操作和主要医院。具体指标键、单位、顺序和数值均以快照为准，API 不做二次解释。

合法枚举已发布但对应 `profile:{diagnosis_code}` 尚未发布时，返回 `200 OK`，保留索引的标题、描述、版本和生成时间，并返回 `filters: {"diagnosis_code": "..."}`、空 `metrics` 和空 `sections`。索引本身未发布、MySQL 不可用或快照契约校验失败时，不降级为空结果，分别返回 `503 RESULT_NOT_READY`、`503 DATABASE_UNAVAILABLE` 或 `500 SERVICE_RESULT_INVALID`；未知路径参数/查询字段返回 `400 INVALID_QUERY_PARAMETER`，details 只列安全字段名。

## 医院运营分析 API（Issue #48）

医院接口只读取统一快照服务，不读取 CSV/HDFS，不在路由中重新聚合、排序、换算单位或修补空值。`FixtureAnalyticsSnapshotRepository` 和 `MySQLAnalyticsSnapshotRepository` 均通过同一个 `AnalyticsSnapshotService.get(module_key, entity_key)` seam 读取：

| 方法 | 路径 | 参数/实体键 |
|---|---|---|
| `GET` | `/api/v1/hospitals` | `facility_a`、`facility_b`、`metric`；无筛选读取 `hospitals/index` |
| `GET` | `/api/v1/hospitals/{facility_id}` | `facility_id` 来自 `hospitals/index.options.facilities[].value`；读取 `hospitals/profile:{facility_id}` |

`facility_a`、`facility_b` 只能使用快照枚举中的字符串机构编码；`metric` 只能是 `case_count`、`avg_los`、`avg_charges`、`avg_costs`、`emergency_rate` 或 `severe_rate`。未知参数、重复参数、非法枚举和相同的 A/B 机构返回 `400 INVALID_QUERY_PARAMETER`；所有医院读取接口严格 GET-only，携带请求体返回 `400 INVALID_REQUEST_FORMAT`，`HEAD`、`OPTIONS`、其他方法返回 `405 METHOD_NOT_ALLOWED`。

成功响应继续使用统一信封。无筛选时 `data` 就是索引快照；存在筛选时，`data.filters` 回显已接受的白名单字符串，并在选择机构后增加 `comparison` 数组。`comparison` 是 API 响应层对完整 profile 快照的稳定顺序组合，不是数据库 payload 的新增字段，profile 内的指标顺序、单位和数值原样保留。

下面以“机构已在索引枚举中、profile 尚未发布”的合法空结果为例；profile 已发布时 `metrics`、`sections` 和 `comparison` 会携带快照原值。

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "title": "医院运营分析",
    "description": "比较医疗机构病例量、住院时长、费用与重症结构。",
    "options": {"facilities": [{"value": "001456", "label": "Mount Sinai Hospital"}]},
    "filters": {"facility_a": "001456", "metric": "avg_charges"},
    "metrics": [],
    "sections": [],
    "comparison": [],
    "data_version": "sparcs_2021_20231012_sha256_<input-sha256>",
    "generated_at": "2026-08-18T12:00:00.000000Z"
  },
  "trace_id": "<uuid>"
}
```

合法机构已在 `index` 枚举中发布、但对应 profile 尚未发布时，返回 `200 OK` 并保留 `title`、`description`、`filters`、`data_version`、`generated_at`，同时令 `metrics`、`sections`、`comparison` 为空；索引本身未发布仍返回 `503 RESULT_NOT_READY`。MySQL 连接/查询失败返回 `503 DATABASE_UNAVAILABLE`；配置缺失返回 `500 SERVER_MISCONFIGURED`；快照 JSON 或结构校验失败返回 `500 SERVICE_RESULT_INVALID`。错误响应不包含 SQL、连接地址、密码、绝对路径或堆栈。

最小调用示例：

```powershell
curl.exe 'http://127.0.0.1:5000/api/v1/hospitals'
curl.exe 'http://127.0.0.1:5000/api/v1/hospitals/001456'
curl.exe 'http://127.0.0.1:5000/api/v1/hospitals?facility_a=001456&facility_b=000541&metric=avg_charges'
```

固定 fixture 验证：`python -m pytest backend/tests/test_analytics_api.py -q`；完整回归：`python -m pytest backend/tests data/tests -q`。真实验收时将 `ANALYTICS_DATA_SOURCE` 切换为 `mysql`，使用已发布的医院 `index/profile` 快照重复无筛选、单院、双院、指标和错误路径，并对照 [Issue #47 医院快照证据](../evidence/47/README.md) 的 `data_version`、`generated_at`、206 条医院记录和 payload 一致性结果。

> 文档版本：V1.0  
> 更新日期：2026-08-17  
> 当前状态：`FROZEN`
> 冻结记录：2026-08-18，Issue #10 的字段、四态和边界语义已按 Resolution、真实服务结果和 `backend/tests/test_disease_top10_api.py` 复核；后续公共字段变更必须先说明上下游影响。
> 上游依据：`02-metrics-and-data-contract.md` V1.1（Issue #7、#9，`FROZEN`）

## 0. Issue #40 统一分析快照读取基础

终局分析页面通过一个只读 Service interface 获取已发布快照，不在路由中连接数据库、解析 JSON 或重新计算指标：

```python
AnalyticsSnapshotService.get(module_key, entity_key) -> dict
```

返回值是冻结 `payload` 加上同一批次的 `data_version` 和 `generated_at`。`FixtureAnalyticsSnapshotRepository` 与 `MySQLAnalyticsSnapshotRepository` 是这个 interface 的两个 adapter；MySQL adapter 只读取 `analysis_snapshot_result`，查询参数使用绑定变量，不读取 CSV/HDFS。

### 0.1 数据源和配置

`ANALYTICS_DATA_SOURCE` 必须显式设置为 `fixture` 或 `mysql`，未知、缺失值不会悄悄回退到 fixture，而是在请求时返回 `500 SERVER_MISCONFIGURED`。fixture 只用于联调和契约测试；真实模式还必须提供 `MYSQL_HOST`、`MYSQL_USER`、`MYSQL_DATABASE`，密码只放在未提交的 `backend/.env` 中。

公共快照的结构校验位于 `shared/analytics_snapshot_contract.py`，Repository 负责读取和依赖错误映射，`AnalyticsSnapshotService` 负责统一验证和时间格式化。MySQL 已发布快照的 JSON 损坏、字段未知、版本/时间或 payload 不符合结构时返回 `500 SERVICE_RESULT_INVALID`；fixture 文件无法读取或配置错误时返回 `500 SERVER_MISCONFIGURED`，两者都不会降级为空答案。

### 0.2 分析路由的参数和实体键

所有分析 GET 路由严格拒绝 `HEAD`、`OPTIONS`、其他 HTTP 方法和请求体。查询参数先经过 `backend/app/routes/parameters.py` 的白名单检查，再按索引快照的 `options` 校验枚举值；重复参数也会返回 `400 INVALID_QUERY_PARAMETER`。费用路由的 `diagnosis_code` 与 `facility_id` 互斥。

实体键只能由服务端按以下顺序拼接，调用方不得自行改顺序：

| 场景 | entity_key |
|---|---|
| 总览、索引、汇总 | `overview`、`index` 或固定 `summary` |
| 医院画像 | `profile:{facility_id}` |
| 疾病画像 | `profile:{diagnosis_code}` |
| 群体 | `age={age_group}\|gender={gender}\|admission={admission_type}` |
| 费用 | `diagnosis={diagnosis_code}\|facility={facility_id}\|severity={severity}` |
| 风险 | `age={age_group}\|diagnosis={diagnosis_code}` |
| 支付 | `payment={payment_type}\|age={age_group}` |

合法枚举值对应的具体快照尚未发布时，接口返回 `200`，保留标题、描述、版本和时间，并将 `metrics`、`sections` 置为空；整个模块的基础快照未发布时仍返回 `503 RESULT_NOT_READY`。数据库连接/查询失败返回 `503 DATABASE_UNAVAILABLE`。

### 0.3 Issue #60 费用与成本分析接口

`GET /api/v1/costs/overview` 只读取 `costs` 模块的已发布快照。路由只负责白名单、枚举校验、固定实体键和统一响应，不在 API 层重新计算收费、成本、住院时长或分位数。

| 参数 | 是否必填 | 枚举来源 | 约束 |
|---|---|---|---|
| `diagnosis_code` | 否 | `diseases/index.options.diagnoses[].value` | 与 `facility_id` 互斥 |
| `facility_id` | 否 | `hospitals/index.options.facilities[].value` | 与 `diagnosis_code` 互斥 |
| `severity` | 否 | `costs` 基础快照 `options.severity` | 可与任一单维度筛选组合 |

无筛选读取 `diagnosis=*|facility=*|severity=*`。存在筛选时，服务端始终按 `diagnosis`、`facility`、`severity` 的顺序构造实体键；例如：

```text
GET /api/v1/costs/overview?diagnosis_code=NVS005&severity=Major
diagnosis=NVS005|facility=*|severity=Major
```

快照发布器提供的费用指标和分区原样返回，当前字段包括平均收费/成本、收费中位数与 P90、收费成本差、单日收费/成本，以及 P25/P50/P75/P90 收费分位数和严重程度分布。单日指标只使用 `los > 0` 的记录；分位数口径为 `percentile_approx(accuracy=10000)`。API 不排序、换单位、补空值或改写这些值。

成功响应仍为 `code/message/data/trace_id`，并在 `X-Trace-ID` 返回同一 UUID。合法枚举但对应实体尚未发布时返回 `200`，保留基础快照的标题、描述、选项、`data_version` 和 `generated_at`，并令 `filters` 回显已接受的筛选、`metrics=[]`、`sections=[]`。基础 `costs` 快照未发布返回 `503 RESULT_NOT_READY`。

未知/重复参数、非法枚举或同时提供 `diagnosis_code` 与 `facility_id` 返回 `400 INVALID_QUERY_PARAMETER`；GET 请求体返回 `400 INVALID_REQUEST_FORMAT`；`HEAD`、`OPTIONS`、POST 等方法返回 `405 METHOD_NOT_ALLOWED`；MySQL 连接/查询失败返回 `503 DATABASE_UNAVAILABLE`；配置缺失或快照结构损坏分别返回 `500 SERVER_MISCONFIGURED` 或 `500 SERVICE_RESULT_INVALID`。错误响应不暴露 SQL、连接信息、绝对路径、堆栈或密钥。

固定 fixture 验证：

```powershell
python -m pytest -q backend/tests/test_analytics_api.py
```

真实验收时设置 `ANALYTICS_DATA_SOURCE=mysql`，对同一批 `data_version` 重复无筛选、单筛选、允许组合、空结果和依赖失败请求，并逐项对照 MySQL `analysis_snapshot_result` 中 `costs` 的 payload；不得把 fixture 结果当作真实验收结论。

### 0.4 住院记录群体分析接口

`GET /api/v1/cohorts/summary` 只读取 `cohorts` 快照，允许的查询参数为 `age_group`、`gender`、`admission_type`。每个值都必须来自基础快照 `options` 中对应的有限枚举；参数可以单独使用或组合使用，未知参数、重复参数和非法枚举返回 `400 INVALID_QUERY_PARAMETER`。

服务端始终按固定顺序组成实体键：

```text
age={age_group}|gender={gender}|admission={admission_type}
```

未选择筛选时读取 `age=*|gender=*|admission=*`。合法枚举但尚未发布对应聚合时返回 `200`，保留基础快照的标题、描述、筛选选项、`data_version` 和 `generated_at`，并将 `metrics`、`sections` 置为空；不会在 API 层重新聚合或排序。成功和错误响应均使用统一 `code/message/data/trace_id` 信封，并在 `X-Trace-ID` 返回同一追踪编号。

### 0.5 Issue #40 验证命令

```powershell
python -m pip install -r backend/requirements.txt
python -m pytest -q backend/tests/test_analytics_api.py backend/tests/test_disease_top10_api.py
```

测试覆盖统一响应信封和 `X-Trace-ID`、未知/重复参数、枚举校验、费用互斥、实体键顺序、合法空结果、方法/请求体错误、配置缺失、数据库依赖错误和损坏快照。完整的终局字段和模块清单见 [07-terminal-product-contract.md](07-terminal-product-contract.md)。

## 1. 范围和基本原则

本接口只返回已经清洗、聚合、校验并发布到 MySQL 表 `disease_case_count_top10_result` 的疾病病例量 TOP10。病例量单位固定为 `discharge_records`，中文含义是“有效住院出院记录数”，不是患者人数。

接口不读取原始 CSV 或 HDFS，不在 Route、Service 或 Repository 中重新清洗、分组或生成排名；不提供自由 SQL、任意筛选、患者级数据、个人诊断或治疗建议。

## 2. 请求契约

| 项目 | 决策 |
|---|---|
| HTTP 方法 | `GET` |
| 方法策略 | 严格 GET-only；`HEAD`、`OPTIONS` 不属于本接口契约 |
| URL | `/api/v1/diseases/top10` |
| API 版本 | 路径版本 `v1`；不使用请求头协商版本 |
| 命名 | URL 使用小写复数名词；JSON 字段使用 `snake_case`，与服务结果字段保持一致 |
| 查询参数 | 无 |
| 请求体 | 无 |
| 认证 | M1 不建设登录或复杂权限 |

不设置 `limit`、年份、医院或疾病筛选参数。TOP10、2021 年数据范围和排序均已由上游指标契约冻结。

以下请求属于非法请求：

- 携带任意查询参数，例如 `?limit=5`；
- 给 GET 请求发送请求体；
- 使用 `HEAD`、`OPTIONS`、`POST`、`PUT` 或 `DELETE`。

TOP10 路由显式关闭 Flask 自动提供的 `OPTIONS`，并拒绝 Flask 对 GET 自动放行的 `HEAD`；上述方法统一返回 `405 METHOD_NOT_ALLOWED`。

## 3. 统一响应结构

所有响应使用 JSON。正常和错误响应都包含：

| 字段 | 类型 | 含义 |
|---|---|---|
| `code` | string | 稳定的机器可读状态码 |
| `message` | string | 可直接用于通用提示的简短英文信息 |
| `data` | object/null | 成功时为业务数据；失败时为 `null` |
| `trace_id` | string(UUID) | 本次请求追踪标识，同时写入 `X-Trace-ID` 响应头 |

错误响应在确有安全、稳定的补充内容时可以增加 `details`。前端业务判断应使用 HTTP 状态和 `code`，不能依赖 `message` 文案。

## 4. 正常响应

状态码：`200 OK`

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "metric": "disease_case_count_top10",
    "unit": "discharge_records",
    "data_version": "fixture:sparcs_mvp_sample:v1",
    "generated_at": "2026-08-17T00:00:00.000000Z",
    "items": [
      {
        "rank": 1,
        "diagnosis_name": "COMPLICATION OF OTHER SURGICAL OR MEDICAL CARE, INJURY, INITIAL ENCOUNTER",
        "case_count": 2
      }
    ]
  },
  "trace_id": "00000000-0000-4000-8000-000000000001"
}
```

### 4.1 业务字段

| JSON 路径 | 类型 | 约束/含义 |
|---|---|---|
| `data.metric` | string | 固定为 `disease_case_count_top10` |
| `data.unit` | string | 固定为 `discharge_records` |
| `data.data_version` | string | 本批服务结果的数据版本，非空 |
| `data.generated_at` | string | ISO 8601 UTC 时间，固定以 `Z` 结尾并保留 6 位微秒 |
| `data.items` | array | 0—10 项；生产已发布批次为 1—10 项 |
| `data.items[].rank` | integer | 从 1 连续递增，最大 10 |
| `data.items[].diagnosis_name` | string | 非空，原服务结果名称，不由 API 改写 |
| `data.items[].case_count` | integer | 大于 0，单位见 `data.unit` |

`unit`、`data_version` 和 `generated_at` 是同一批全部项目共享的元数据，因此在 `data` 层返回一次；疾病名称、数量和排名逐项返回。API 不输出诊断代码、患者 ID 或原始住院明细。

## 5. 排序与 TOP10 边界

- API 保证 `items` 按 `rank` 升序返回。
- 排名来源于上游已验证服务结果，API 不重新计算。
- 上游排名规则为 `case_count` 降序；数量并列时按 `diagnosis_name` 的 UTF-8/Unicode 二进制字典序升序。
- 严格最多返回 10 项；第 10 名并列时不扩展返回所有并列项。
- 可用批次不足 10 种疾病时返回全部已有项目。
- Service 会验证行数、连续排名、名称唯一、数量、单位、单一数据版本、单一生成时间和冻结排序；验证失败返回 `SERVICE_RESULT_INVALID`，不会静默修正数据。

## 6. 空数据与前端四态

合法空快照返回 `200`，保留明确的 `data_version`、`generated_at` 和 `unit`，并令：

```json
"items": []
```

前端四态映射固定如下：

| 页面状态 | 判断方式 |
|---|---|
| 加载中 | 请求尚未结束，由前端控制 |
| 正常数据 | HTTP 200 且 `data.items.length > 0` |
| 空数据 | HTTP 200 且 `data.items.length === 0` |
| 接口错误 | HTTP 非 2xx；按 `code` 显示通用错误或重试入口 |

重要边界：Issue #9 规定真实 MySQL 服务表不发布空批次。因此生产 MySQL 表为空表示“正式结果尚未发布”，返回 `503 RESULT_NOT_READY`，不能被解释为空数据。`200 + []` 当前主要用于固定 Mock 和前端空态验收；若未来增加会自然产生空结果的合法查询条件，仍沿用该结构。

## 7. 错误语义

| HTTP | `code` | 场景 | 用户可见信息 |
|---:|---|---|---|
| 400 | `INVALID_QUERY_PARAMETER` | 携带任何查询参数 | 请求参数不受支持 |
| 400 | `INVALID_REQUEST_FORMAT` | GET 携带请求体或格式错误 | 请求格式无效 |
| 404 | `RESOURCE_NOT_FOUND` | URL 不存在 | 请求的资源不存在 |
| 405 | `METHOD_NOT_ALLOWED` | 使用 `HEAD`、`OPTIONS`、`POST`、`PUT` 或 `DELETE` | 请求方法不支持 |
| 500 | `SERVER_MISCONFIGURED` | MySQL 必要配置缺失、fixture 配置错误 | 服务配置不完整 |
| 500 | `SERVICE_RESULT_INVALID` | 已发布数据不满足 #9 契约 | 服务结果校验失败 |
| 500 | `INTERNAL_ERROR` | 未预期程序异常 | 服务内部异常 |
| 503 | `DATABASE_UNAVAILABLE` | MySQL 连接、查询或超时失败 | 数据服务暂时不可用 |
| 503 | `RESULT_NOT_READY` | 生产结果表为空，尚未首次发布 | TOP10 结果尚未发布 |

错误响应不返回数据库地址、SQL、密码、堆栈或原始异常信息。示例：

```json
{
  "code": "DATABASE_UNAVAILABLE",
  "message": "The data service is temporarily unavailable.",
  "data": null,
  "trace_id": "00000000-0000-4000-8000-000000000004"
}
```

## 8. 数据访问限制

Repository 只执行以下有限查询：

```sql
SELECT `rank`, `diagnosis_name`, `case_count`, `unit`,
       `data_version`, `generated_at`
FROM `disease_case_count_top10_result`
ORDER BY `rank` ASC
LIMIT 11;
```

`LIMIT 11` 是内部溢出哨兵：Repository 最多读取 11 行，Service 发现超过 10 行时返回 `500 SERVICE_RESULT_INVALID`，避免数据库查询提前截断后误把异常结果当作合法 TOP10。对外响应仍最多返回 10 条。

Route 只校验请求和返回统一结构；Service 只验证已发布服务结果；Repository 只读取 MySQL。任何清洗、聚合、同义词合并、排名生成或长 SQL 都不进入 API。

## 9. 固定 Mock

可复查 Mock：

- `docs/mocks/disease-top10-success.json`
- `docs/mocks/disease-top10-empty.json`
- `docs/mocks/disease-top10-invalid-parameter.json`
- `docs/mocks/disease-top10-dependency-failure.json`

成功 Mock 使用 `fixture:sparcs_mvp_sample:v1`，只验证契约和界面，不代表全量 210 万条数据的真实分布。

## 10. 启动、调用与测试

### 10.1 Windows PowerShell

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

请先显式配置 `TOP10_DATA_SOURCE`。开发环境可在 `backend/.env` 中设置为 `fixture`，生产环境应设置为 `mysql`；缺失或未知值不会回退到 fixture，而会返回 `500 SERVER_MISCONFIGURED`。另开终端调用：

```powershell
curl.exe -i http://127.0.0.1:5000/api/v1/diseases/top10
curl.exe -i "http://127.0.0.1:5000/api/v1/diseases/top10?limit=5"
curl.exe -i -X POST http://127.0.0.1:5000/api/v1/diseases/top10
curl.exe -i -X HEAD http://127.0.0.1:5000/api/v1/diseases/top10
curl.exe -i -X OPTIONS http://127.0.0.1:5000/api/v1/diseases/top10
curl.exe -i http://127.0.0.1:5000/api/v1/health
```

空态 Mock：

```powershell
$env:TOP10_FIXTURE_STATE="empty"
python run.py
```

接入真实 MySQL 时，在本地 `backend/.env` 中设置：

```dotenv
TOP10_DATA_SOURCE=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=medical_api
MYSQL_PASSWORD=本地密码
MYSQL_DATABASE=medical_analytics
```

真实 `.env` 不提交 Git。测试命令：

```powershell
python -m pytest -q
```

## 11. 代表性验收清单

| 类型 | 请求/条件 | 期望 |
|---|---|---|
| 正常 | `GET /api/v1/diseases/top10` + success fixture | 200、10 项、字段类型正确、顺序不变 |
| 合法空结果 | GET + empty fixture | 200、`items=[]`、批次元数据仍存在 |
| 非法参数 | `GET ...?limit=5` | 400、`INVALID_QUERY_PARAMETER` |
| 请求体错误 | GET 携带 JSON body | 400、`INVALID_REQUEST_FORMAT` |
| 方法错误 | `HEAD`、`OPTIONS`、`POST`、`PUT` 或 `DELETE /api/v1/diseases/top10` | 405、`METHOD_NOT_ALLOWED` |
| 依赖失败 | Repository 抛出数据库不可用 | 503、`DATABASE_UNAVAILABLE` |
| 配置缺失 | MySQL 模式缺少必要配置 | 500、`SERVER_MISCONFIGURED` |
| 未发布 | MySQL 查询返回 0 行 | 503、`RESULT_NOT_READY` |
| 结果损坏 | 排名不连续、版本混合等 | 500、`SERVICE_RESULT_INVALID` |

## 12. 已知限制

- 只支持固定 2021 年疾病病例量 TOP10。
- 没有查询参数、分页、自由 SQL、患者级数据或其他指标。
- fixture 只用于开发和验收；生产结果必须来自已验证 MySQL 服务表。
- M1 服务表只保存当前批次，不提供历史版本查询。
- `/api/v1/health` 只表示 Flask 进程存活，不代替 TOP10 数据依赖检查。
- 当前 TOP10 接口不提供 HEAD/OPTIONS 探测契约；需要探活时使用 `/api/v1/health`。

## 13. Issue #10 Resolution（可直接粘贴）

```text
Resolution: FROZEN

- GET /api/v1/diseases/top10；v1 路径版本；严格 GET-only，不接受 HEAD/OPTIONS、查询参数或请求体。
- 成功响应固定返回 code、message、data、trace_id；业务字段为 metric、unit、data_version、generated_at、items，以及每项的 rank、diagnosis_name、case_count。
- items 按已发布 rank 升序，最多 10 项；并列和截断完全沿用 Issue #7/#9，不在 API 重新计算。
- 合法空快照返回 200 + items=[]；生产 MySQL 空表属于尚未发布，返回 503 RESULT_NOT_READY。
- 非法参数 400；方法错误 405；配置或结果契约错误 500；数据库不可用/结果未发布 503。
- Route 不复制清洗、聚合、排序或长 SQL，只通过 Service/Repository 查询已验证服务结果。
- 固定 success/empty/error Mock 和代表性测试已提供。

当前契约已冻结。真实服务结果、Flask API 和 Vue 页面必须继续使用本节字段、状态码和错误语义；发现冲突时先记录影响并回写对应 Issue。
```
