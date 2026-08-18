# 疾病病例量 TOP10 API 契约

> 文档版本：V1.0  
> 更新日期：2026-08-17  
> 当前状态：`FROZEN`
> 冻结记录：2026-08-18，Issue #10 的字段、四态和边界语义已按 Resolution、真实服务结果和 `backend/tests/test_disease_top10_api.py` 复核；后续公共字段变更必须先说明上下游影响。
> 上游依据：`02-metrics-and-data-contract.md` V1.1（Issue #7、#9，`FROZEN`）

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
