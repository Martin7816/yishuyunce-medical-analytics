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
9. 当前验收状态
FakeAIClient / 单元测试：PASS
Backend 回归：PASS
8 个白名单工具：PASS
参数与调用数量边界：PASS
模拟 timeout/network/upstream：PASS
真实 DeepSeek API：NOT RUN
真实 DeepSeek 红队：NOT RUN
#79 最终验收结论：PENDING

真实 DeepSeek API 尚未执行，因此当前不得将 #79 标记为最终 PASS 或关闭。

10. 下一步

配置本机真实 DeepSeek Key 后执行 Q01～Q09 和安全红队测试，并保存脱敏结果，再更新本记录。
'@ | Set-Content -Path evidence\79\execution-record.md -Encoding UTF8