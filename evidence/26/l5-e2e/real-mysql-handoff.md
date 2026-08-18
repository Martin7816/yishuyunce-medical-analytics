# 真实 MySQL / 组长电脑端到端交接（L5）

> 记录时间：2026-08-18T06:49Z（UTC）
> 本机状态：**BLOCKED / HANDOFF**——本机无法访问真实 MySQL 与完整 CSV，不伪造本机复现，引用 #31/#10/#25 记录级证据。

## 本机实测边界

| 检查 | 实测结果 |
|---|---|
| `hadoop001`（192.168.219.128）TCP 22 | 不可达（closed） |
| `hadoop001`（192.168.219.128）TCP 3306 | 不可达（closed） |
| 本机 127.0.0.1:3306 | 有本地 MySQL 8.0 实例在运行，但仓库无其访问凭证，且不属于 M1 已发布批次（真实批次在 hadoop001），**未使用、未猜测密码、未写入** |
| 完整 SPARCS 2021 CSV（文件名/大小/SHA-256 见 docs/02 1.1 节） | 本机不存在（常见目录搜索无结果），全量复跑不执行 |
| `backend/.env` | 本机不存在 |

因此以下内容在本机标记 `NOT RUN（本机）`，证据以 #31/#10/#25 的 Issue 评论与 Resolution 为记录级证据：

## RECORD_LEVEL_EVIDENCE 引用表

| 内容 | 状态 | 记录级证据位置 |
|---|---|---|
| 真实 CSV 全量 PySpark 任务（2,101,588 行、477 分组、10 行服务结果） | 组长电脑已执行两次、结果一致 | #31 评论 2026-08-18T01:42:29Z、02:05:51Z、Resolution 02:10:40Z；docs/04 第 4.1、7.1 节 |
| `publish_top10_mysql.py --apply` 真实装载（10 行，事务提交） | 已通过 | #31 Resolution；`generated_at=2026-08-18T01:36:42.446058Z` |
| 提交后逐行查询核对（10 行、连续排名、名称/数量/单位/版本/时间一致） | 已通过 | #31 评论 02:05:51Z |
| 回滚演练（故意超 BIGINT UNSIGNED → MySQL 1264 → ROLLBACK → 旧批次 10 行仍可读） | 已通过 | #31 评论 02:05:51Z、Resolution |
| 真实 API HTTP 200 / 10 项 / `data_version` 与 MySQL 一致 | 已通过 | #31 Resolution、#10 评论 02:59:05Z（字段与刷新语义复核 PASS） |
| 正式页面真实 success（DOM/截图、字段/单位/批次一致、Tooltip、窗口 390px/1280px、控制台无 error/warning） | 已通过 | #25 Resolution 2026-08-18T04:00:21Z、docs/06 “Issue #25 页面正式接口适配记录” |
| 后端 `12 passed` | 已通过（组长电脑 + 本机各一次） | #25/#10 记录；本机复验见 evidence/26/l3-api/pytest-output.txt |

## 组长电脑 HANDOFF 复现命令（供王敬博执行）

```powershell
# 0. 基线
git switch main && git pull --ff-only
git rev-parse HEAD   # 预期 3ca67c978453ea40cda4cfcffa931e9f88c4a753

# 1. VM/MySQL（hadoop001）
sudo systemctl start mysql8
sudo systemctl --no-pager status mysql8
/opt/module/mysql/bin/mysql --socket=/opt/module/mysql/mysql.sock -uroot -p \
  -e "SELECT VERSION(); SELECT COUNT(*) FROM medical_analytics.disease_case_count_top10_result;"

# 2. 数据任务（有完整 CSV 时）
conda activate csupy311
python data/src/run_sparcs_top10_pyspark.py --input "<本地完整 SPARCS CSV 路径>" --expected data/fixtures/sparcs_mvp_expected_top10.json --output "<临时目录>\service-result.json"
python data/src/verify_service_result_contract.py --result "<临时目录>\service-result.json" --expected-scope full_scan

# 3. 后端（本机 backend/.env 已为 MySQL 模式）
cd backend
python -m pytest -q
python run.py
curl.exe -i http://127.0.0.1:5000/api/v1/diseases/top10

# 4. 前端
cd frontend
npm ci
npm run build
npm run dev
# 记录同刻 API 响应、页面截图（含浏览器尺寸）与 data_version 对比
```

预期：API 200、10 项、`data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219`，页面显示与 API 逐项一致。

证据保存：截图与同刻响应按 `evidence/26/l5-e2e/` 命名归档；密码、Token、个人绝对路径、完整 CSV 不进入 Git（docs/06 第 9.2 节）。
