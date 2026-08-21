# Issue #71 最终收口交接说明

> 交给具备仓库 PR 和 Issue 写权限的维护者执行。

## 当前状态

- 仓库：`Martin7816/yishuyunce-medical-analytics`
- 工作流分支：`data/full-analytics-snapshot`
- 最新提交：`ed965b0`
- 验收文档：`issue-71-data-quality-metrics.md`
- #71、#70：Open；#72、#73：Closed
- 共享分支已推送，但 `ed965b0` 尚未合入 `main`
- 当前没有 #71 的 PR
- `.tmp/` 是本地运行产物，不要提交

## 已完成内容

- 七项数据质量指标、固定样例、真实 CSV 全量 PySpark 和标准库独立核对均已完成
- MySQL 事务发布、重复发布和失败回滚均已验证
- D-01 至 D-07 已在 `issue-71-data-quality-metrics.md` 中记录为 PASS
- #72 后端和 #73 前端已收到字段、状态、版本和 fixture 交接评论，并已关闭
- 与 #102 的字段分母审计冲突已解决
- 数据回归结果：`27 passed`

## 一、准备权限

接手人必须能创建/合并 PR，并能评论和关闭 Issue。先检查：

```powershell
gh auth status
gh repo view Martin7816/yishuyunce-medical-analytics
```

没有权限时不要关闭 Issue，请转交仓库维护者。

## 二、检查共享分支

```powershell
git fetch origin --prune
git switch data/full-analytics-snapshot
git pull --ff-only origin data/full-analytics-snapshot
git log -1 --oneline origin/data/full-analytics-snapshot
git status --short
```

确认最新提交为 `ed965b0`（或后续收口提交），除 `.tmp/` 外没有未提交文件。

## 三、合并前复核

```powershell
.\.venv\Scripts\python.exe -m pytest `
  data/tests/test_data_quality_snapshot.py `
  data/tests/test_snapshot_publisher.py `
  data/tests/test_hospital_snapshot.py `
  data/tests/test_disease_snapshot.py `
  data/tests/test_cohort_snapshot.py `
  data/tests/test_risk_snapshot.py -q
```

预期：`27 passed`。另执行：

```powershell
git diff origin/main...origin/data/full-analytics-snapshot --check
```

当前工作区没有 Flask；不要把未运行的后端测试伪报为通过。若环境有依赖，可补跑：

```powershell
python -m pytest backend/tests/test_data_quality_api.py backend/tests/test_analytics_api.py -q
```

## 四、创建并合并 PR

```powershell
gh pr create `
  --base main `
  --head data/full-analytics-snapshot `
  --title "feat(data)(#71): publish data quality snapshot" `
  --body "Refs #71`n`n七项指标、固定样例、真实全量 PySpark、独立核对和 MySQL 发布均已完成；D-01 至 D-07 全部 PASS。详见 issue-71-data-quality-metrics.md。"
```

记录输出的 PR 编号，检查后合并：

```powershell
gh pr checks <PR编号>
gh pr view <PR编号>
gh pr merge <PR编号> --merge --delete-branch=false
```

不要新建 `feature/#71-*` 分支，也不要删除共享分支。

## 五、确认进入 main

```powershell
git fetch origin --prune
git merge-base --is-ancestor ed965b0 origin/main
if ($LASTEXITCODE -eq 0) { "PASS: ed965b0 is in main" } else { "FAIL: not merged" }
```

只有 `PASS` 才能继续。

## 六、在 #70 发布 Resolution handoff

将 `<PR编号>` 和实际 merge commit 替换后，在 #70 评论：

```markdown
## #71 Resolution handoff

#71 数据质量快照已完成并合入 `main`。

- PR：#<PR编号>
- 最终数据提交：`ed965b0`
- 合入验证：`ed965b0` 已包含在 `origin/main`
- 验收文档：`issue-71-data-quality-metrics.md`
- 数据回归：`27 passed`
- 固定样例、真实全量 PySpark、标准库独立核对：PASS
- MySQL 事务发布：857 条；重复发布和失败回滚：PASS
- D-01 至 D-07：全部 PASS
- #72、#73 已完成下游交接并关闭

HDFS/Hive 没有独立环境证据，继续显示 `CHECK_REQUIRED`；fixture 不替代真实全量结果。
```

## 七、在 #71 发布最终 Resolution

```markdown
## Resolution

### 已完成

- 七项数据质量指标、固定样例和真实全量 CSV 验收通过
- 标准库独立核对通过
- MySQL 事务发布、重复发布和失败回滚通过
- D-01 至 D-07 全部 PASS
- #72、#73 下游交接完成并关闭
- 共享分支已合入 `main`

### 证据

- PR：#<PR编号>
- 最终提交：`ed965b0`
- 验收文档：`issue-71-data-quality-metrics.md`
- 数据回归：`27 passed`
- 真实基础记录：2,101,588 条；MySQL 快照：857 条

### 限制

- HDFS/Hive 保持 `CHECK_REQUIRED`，没有虚报为已验证
- fixture 只证明契约和边界，不替代真实全量数据
```

## 八、关闭并复查

```powershell
gh issue close 71
gh issue view 71
gh pr view <PR编号>
```

最终必须确认：PR 为 `Merged`、#71 为 `Closed`、#70 有独立 Resolution、`origin/main` 包含 `ed965b0`。

## 完成回报

```text
#71 已完成收口
- PR：#...
- merge commit：...
- ed965b0 已进入 main：PASS
- #70 Resolution：已发布
- #71 Resolution：已发布
- #71 状态：Closed
```

## 禁止事项

- 不要重复开发 #71
- 不要提交 `.tmp/`
- 不要把 fixture 当真实全量结果
- 不要把 HDFS/Hive 的 `CHECK_REQUIRED` 改成 `PASS`
- 不要只合并 PR 而不写 #70/#71 Resolution
- 未确认 `main` 包含最终提交前，不要关闭 #71
