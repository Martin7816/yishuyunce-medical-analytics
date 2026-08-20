@'
# #79 本机执行记录与验收状态


> Issue：#79 `[AI大模型问答与洞察报告] 白名单工具与DeepSeek编排`
>
> 执行日期：2026-08-18
>
> 环境：Windows PowerShell + Conda `csupy311`
>
> 分支：`ai/deepseek-assistant`
>
> 核心实现 commit：`7bec092`


## 1. 当前实现


当前 #79 已实现：


- 8 个固定白名单工具
- DeepSeekChatClient
- AIAssistantService 编排
- 第一轮必须返回 1～2 个 tool_calls
- 未知工具拒绝
- 工具参数只允许 `{}`
- AnalyticsSnapshotService 聚合数据读取
- tool_trace / sources / data_versions
- 第二轮空回答拒绝
- SQL、个人诊断、治疗和因果结论安全边界
- timeout / network / HTTP upstream 错误处理
- FakeAIClient 自动化测试


## 2. Fixture 快照验证


执行：


```powershell
python -c "import sys; from pathlib import Path; sys.path.insert(0, 'backend'); from app.repositories.analytics_snapshot import FixtureAnalyticsSnapshotRepository; from app.services.analytics_snapshot import AnalyticsSnapshotService; r=FixtureAnalyticsSnapshotRepository(Path('backend/app/fixtures/analytics_snapshot_success.json')); s=AnalyticsSnapshotService(r); x=s.get('dashboard','overview'); print('snapshot OK'); print('data_version =', x['data_version']); print('metrics =', len(x.get('metrics', [])))"

实际结果：

snapshot OK
data_version = fixture:sparcs_full_analytics:v1
metrics = 8

状态：PASS

3. AI 模块验证

执行：

python -c "import sys; sys.path.insert(0, 'backend'); from app.services.ai_assistant import AIAssistantService, DeepSeekChatClient, tool_definitions; print('AI import OK'); print('tool count =', len(tool_definitions()))"

实际结果：

AI import OK
tool count = 8

状态：PASS

4. AI 专项测试

执行：

python -m pytest backend/tests/test_ai_assistant.py -q

实际结果：

25 passed in 0.06s

状态：PASS

覆盖白名单工具、0/>2 tool_calls、未知工具、非法参数、空回答、SQL 诱导、诊断/治疗诱导、无 Key、timeout、network failure 和 HTTP upstream error。

5. Backend 全量回归

执行：

python -m pytest backend/tests -q

实际结果：

37 passed in 0.13s

状态：PASS

6. Git 与敏感信息检查

执行：

git diff --check
git diff --cached --check
git diff --cached | Select-String -Pattern 'sk-[A-Za-z0-9_-]{10,}'

实际结果均无输出。

状态：PASS

当前提交内容未发现疑似真实 DeepSeek API Key。

7. 配置

backend/.env.example 提供：

ANALYTICS_DATA_SOURCE=fixture
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=20

真实 Key 不允许写入 .env.example、evidence、Git commit 或 Issue。

8. 验收材料

问题与工具映射：

evidence/79/question-tool-matrix.md

安全红队：

evidence/79/security-red-team.md


## 9. 真实 DeepSeek API 连通性


使用本机 `backend/.env` 中的真实 `DEEPSEEK_API_KEY` 验证 DeepSeek API。


实际结果：


```text
API_OK

客户端返回字段：

role
content
reasoning_content

状态：PASS

说明：

API Key 可用；
DeepSeek API 网络连通；
当前 base URL 可用；
当前 model 可用；
未在命令、日志或 evidence 中输出真实 API Key。
10. 真实 DeepSeek Q01～Q09 验证
编号	问题类型	预期工具	最终实际工具	结果
Q01	整体医疗运营	get_dashboard_overview	get_dashboard_overview	PASS
Q02	医院运营	get_hospital_overview	get_hospital_overview	PASS
Q03	疾病分布	get_disease_overview	get_disease_overview	PASS
Q04	住院记录群体	get_cohort_summary	get_cohort_summary	PASS
Q05	费用和成本	get_cost_overview	get_cost_overview	PASS
Q06	风险指标	get_risk_overview	get_risk_overview	PASS
Q07	支付方式	get_payment_overview	get_payment_overview	PASS
Q08	模型评估指标	get_model_metrics	get_model_metrics	PASS
Q09	整体运营 + 费用	get_dashboard_overview + get_cost_overview	get_dashboard_overview + get_cost_overview	PASS

所有成功调用均返回：

status = success
data_version = fixture:sparcs_full_analytics:v1
Q01 首次失败与修复

Q01 首次真实调用时，DeepSeek 一次选择了 7 个工具：

get_dashboard_overview
get_hospital_overview
get_disease_overview
get_cost_overview
get_risk_overview
get_payment_overview
get_model_metrics

服务正确触发：

The AI exceeded the two-tool-call limit.

说明“两工具上限”安全拦截正常。

随后加强 system prompt 路由规则：

单主题优先且通常只调用 1 个工具；
只有明确跨两个主题才调用 2 个；
整体运营明确映射到 get_dashboard_overview；
禁止为了让答案更全面而额外调用工具。

复测 Q01：

get_dashboard_overview

状态：PASS

Q04 首次失败与修复

Q04 首次真实调用：

问题：请概括当前住院记录群体的总体情况。
预期：get_cohort_summary
实际：get_dashboard_overview

原因：

“总体情况”与“整体运营”存在路由语义歧义

随后加强路由规则：

群体 / 人群 / 患者群体 / 住院记录群体 / cohort
→ get_cohort_summary

并明确：

即使同时出现“总体情况”，也不得因此选择 dashboard

复测实际工具：

get_cohort_summary

状态：PASS

Q09 双工具验证

实际调用：

get_dashboard_overview
get_cost_overview

调用数量：

2

未超过上限。

状态：PASS

11. 修改后回归测试

修改真实 DeepSeek 路由 prompt 后执行：

python -m pytest backend/tests/test_ai_assistant.py -q

结果：

25 passed in 0.06s

再次执行 Backend 全量回归：

python -m pytest backend/tests -q

结果：

37 passed in 0.14s

状态：PASS

## 12. 当前验收状态

FakeAIClient / 单元测试：PASS
Backend 全量回归：PASS
8 个白名单工具：PASS
真实 DeepSeek API 连通性：PASS
真实 DeepSeek Q01～Q09：PASS
单主题 1 工具路由：PASS
双主题 2 工具路由：PASS
>2 工具安全拦截：PASS
参数安全边界：PASS
模拟 timeout/network/upstream：PASS
真实 DeepSeek 20 秒 timeout：PASS
真实 DeepSeek 安全红队：PASS
SQL / 患者级数据 / 诊断 / 治疗 / 因果边界：PASS
Prompt Injection / Key 泄露 / 图表注入 / data_version 伪造：PASS
#79 工作分支验收结论：PASS
#79 最终关闭状态：PENDING（等待 ai/deepseek-assistant 工作流 PR 合并 main，并在 #78 发布独立 Resolution）

真实 DeepSeek Q01～Q09、核心安全红队、Backend 全量回归、Git 差异检查和敏感信息检查均已完成并通过，因此 #79 在当前 ai/deepseek-assistant 工作分支上的验收结论为 PASS；Issue 最终关闭仍等待工作流 PR 合并 main 及 #78 独立 Resolution。

## 13. 下一步

提交并推送本次最终验收结论；随后继续 #78～#81 的 ai/deepseek-assistant 工作流开发。待工作流 PR 完成并合并 main 后，再在 #78 发布 #79 的独立 Resolution，并按 Issue 关闭条件处理 #79。
