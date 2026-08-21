# Issue #102：按业务总体修正指标分母

验收日期：2026-08-20（Asia/Shanghai）。本目录只保存摘要和复现命令；完整 CSV、完整快照 JSON、数据库凭证和密钥不进入 Git。

## 输入与统一版本

| 项目 | 真实全量结果 |
|---|---:|
| 原始记录数 | 2,101,588 |
| 基础记录总体 | 2,101,588 |
| 严重程度指标有效总体 | 2,099,038 |
| 严重程度缺失/不可判定 | 2,550 |
| `Major/Extreme` 分子 | 700,276 |
| 重症率 | `700276 / 2099038 = 0.3336` |
| 急诊率分子/分母 | `1,316,237 / 2,101,588 = 0.6263` |
| 外科率分子/分母 | `493,449 / 2,101,588 = 0.2348` |
| 机构编号有效/缺失 | `2,090,946 / 10,642` |
| 主诊断有效/缺失 | `2,099,954 / 1,634` |
| 主要操作有效/缺失 | `1,525,567 / 576,021` |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-20T00:00:00.000000Z` |
| 公式版本 | `analytics-denominator-v1` |

## 复现命令与结果

以下命令在仓库根目录执行，`<完整 CSV>` 指本地老师数据路径，`<临时目录>` 不属于仓库：

```powershell
.\.venv\Scripts\python.exe data\src\run_full_analytics_pyspark.py `
  --input "<完整 CSV>" --output "<临时目录>\issue102-real-full.json" `
  --module all --generated-at 2026-08-20T00:00:00Z --master local[1]

.\.venv\Scripts\python.exe data\src\verify_dashboard_snapshot.py `
  --input "<完整 CSV>" --snapshot "<临时目录>\issue102-real-full.json"
.\.venv\Scripts\python.exe data\src\verify_hospital_snapshot.py `
  --input "<完整 CSV>" --snapshot "<临时目录>\issue102-real-full.json"
.\.venv\Scripts\python.exe data\src\verify_disease_snapshot.py `
  --input "<完整 CSV>" --snapshot "<临时目录>\issue102-real-full.json"
.\.venv\Scripts\python.exe data\src\verify_cohort_snapshot.py `
  --input "<完整 CSV>" --snapshot "<临时目录>\issue102-real-full.json"
.\.venv\Scripts\python.exe data\src\verify_risk_snapshot.py `
  --input "<完整 CSV>" --snapshot "<临时目录>\issue102-real-full.json"
```

实际结果：

- 快照生成：`PASS`，7197 条统一快照记录，`data_version` 与输入一致；
- dashboard 独立核对：`PASS`，记录数 2,101,588，严重程度 4 项；
- hospitals 独立核对：`PASS`，205 个机构、205 个画像、0 个空画像，有机构编号记录 2,090,946；
- diseases 独立核对：`PASS`，477 个有效诊断类别、477 个画像；
- cohorts 独立核对：`PASS`，168 个合法筛选键，其中 14 个合法空组合；
- risks 独立核对：`PASS`，2868 个合法筛选键，其中 254 个合法空组合，wildcard 有效严重程度 2,099,038、Major/Extreme 700,276。

独立核对脚本均使用标准库重新读取 CSV，不导入生产聚合函数；快照、分母、排序、分布 section、筛选键、版本和时间戳逐项比较。

## 分层交接与边界

- `data_quality/summary.options.audit` 集中提供公式版本、基础总体、筛选条件、字段适用/有效/缺失数及比例分子/分母；API 继续使用原有响应信封和 `data_version`/`generated_at`。
- 医院与疾病业务选项只使用有效机构编号、有效主诊断；群体和风险页面保留当前筛选的基础记录数，严重程度比例不把未知值计入分母。
- fixture、后端 API、数据测试和前端共享渲染器仍使用同一 Payload 契约。真实 MySQL 发布、浏览器截图和五名成员 Issue 确认需在具备相应环境和权限后继续执行，不能用本次本地 fixture 结果替代。
