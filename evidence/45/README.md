# Issue #45 前端独立验收证据

## 范围

- 目标页面：`/overview`；公共分析 renderer 的回归覆盖十个桌面路由。
- 本次按用户明确要求只验收桌面端；手机适配不属于本次关闭范围，并需在 Resolution 中明确记录。
- fixture 只用于页面契约和四态验收；真实成功态单独使用实际 dashboard 快照验收。

## 验收矩阵

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| U-01 | `/overview` 标题、8 张 KPI、5 个图表分区、页脚顺序 | PASS | [`l4-page/desktop-routes.json`](l4-page/desktop-routes.json) |
| U-02 | 真实接口 HTTP 200、8 个指标、5 个分区、`data_version` 与页面一致 | PASS | [`l4-page/real-overview-api.json`](l4-page/real-overview-api.json) |
| U-03 | fixture loading / success / empty / error 四态与 retry | PASS | [`l4-page/fixture-states.json`](l4-page/fixture-states.json) |
| U-04 | 十个桌面路由无错误态；正文无横向溢出 | PASS | [`l4-page/desktop-routes.json`](l4-page/desktop-routes.json) |
| U-05 | 构建、后端回归和前端 diff 检查 | PASS | [`l4-page/build-and-tests.txt`](l4-page/build-and-tests.txt) |
| U-06 | fixture 明示警告；真实版本单独记录；错误只显示稳定提示、错误码和 trace id | PASS | 上述四份证据及前端源码 |

## 关闭前仍需完成的外部动作

1. 将本次前端 commit 交给 `frontend/multi-page-dashboard` 工作流维护者，合入 `main`；本地 `integration/final-product` 不创建独立前端 PR。
2. 将本目录证据随工作流 commit/PR 推送，并在 #45 和 #42 分别发布 Resolution/交接结论。
3. 由负责人确认“桌面端完成、手机适配按用户决定不纳入本次范围”，然后关闭 #45。

## 已知边界

- 当前真实 dashboard API 的 MySQL/服务快照链路由上游 #39/#43 负责；本证据记录页面消费到的真实 `data_version`，不重新声称数据任务完成。
- AI 密钥、模型真实训练工件和其他模块的独立 Issue 不作为 #45 的关闭条件。
