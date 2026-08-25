# AI 通用语义问数升级部署指导

## 1. 部署结论

本次版本已经把 AI 问数从少量固定问题路由升级为“自然语言意图识别 → DeepSeek 结构化分析 → 服务端白名单能力校验 → MySQL 聚合事实 → 有证据回答”的通用链路，并增加了模型不可用时的确定性规划与证据摘要降级。

因此组长拉取代码后需要：

- 重启后端 Flask 服务；
- 如果前端使用生产静态文件，重新执行前端构建并发布 `frontend/dist`；
- 在组长机器的 `backend/.env` 中确认聚合数据源和 DeepSeek 思考配置。

本次不需要数据库结构迁移，也不需要因为代码更新重新清洗 CSV 或重新发布数据；前提是目标环境已经存在可用的 ACTIVE 聚合事实批次。如果没有已发布的聚合批次，应用会按安全策略拒绝给出医疗统计结论，需要先走既有数据发布流程。代码没有新增必须安装的 LangChain/Deep Agents 依赖，避免部署环境因框架版本差异产生额外故障。

## 2. 拉取代码

在组长部署机执行：

```powershell
git fetch origin
git checkout test/assistant-integrated
git pull --ff-only origin test/assistant-integrated
```

如果团队把该分支合并到了正式部署分支，则在正式部署分支执行等价的 `git pull --ff-only`，不要直接复制工作区文件覆盖部署目录。

## 3. 后端配置与重启

只修改未提交的 `backend/.env`，不要把真实密钥写入 Git。确认至少包含以下配置；MySQL 主机、账号和密码沿用现有部署值：

```dotenv
TOP10_DATA_SOURCE=mysql
ANALYTICS_DATA_SOURCE=mysql
AGGREGATE_DATA_SOURCE=mysql

DEEPSEEK_API_KEY=<真实密钥>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=20
DEEPSEEK_THINKING_MODE=enabled
DEEPSEEK_REASONING_EFFORT=high
DEEPSEEK_STRUCTURED_MAX_TOKENS=4096
```

依赖没有变化时不需要重复安装；若部署机需要同步依赖，可执行：

```powershell
<Python路径> -m pip install -r backend\requirements.txt
```

停止旧 Flask 进程后，按现有部署方式重新启动：

```powershell
<Python路径> backend\run.py
```

如果使用 Windows 服务、任务计划、NSSM、Docker 或反向代理托管 Flask，只需重启对应后端服务，启动参数不需要改成新的接口。

## 4. 前端构建与发布

生产环境使用静态构建时：

```powershell
cd frontend
npm ci
npm run build
```

将新生成的 `frontend/dist` 发布到现有 Web 服务器目录，并按现有方式刷新反向代理或静态文件缓存。开发联调环境只需重新启动：

```powershell
cd frontend
npm run dev
```

## 5. 最小验收

先检查后端健康状态：

```powershell
curl.exe http://127.0.0.1:5000/api/v1/health
```

再检查 AI 流式接口：

```powershell
curl.exe -N -X POST http://127.0.0.1:5000/api/v1/ai/chat/stream `
  -H "Content-Type: application/json" `
  --data-binary '{"message":"50岁男性最容易得什么病"}'
```

页面上至少验证以下问题：

- `50岁男性最容易得什么病`：应明确说明数据按年龄组汇总，不能把 `50岁` 伪装成精确年龄；
- `哪些医院病例量最高？`：应返回医院维度的真实聚合结果；
- `男性和女性的疾病分布有什么不同？`：应进入性别 × 疾病的白名单能力，回答中应能看到数据来源和口径说明。

验收时确认回答仍显示数据版本、来源或限制说明，并且没有执行任意 SQL、编造患者级结论或把住院记录数描述成发病率/患病率。

## 6. 这次不需要组长额外做的事情

- 不需要新增 Flask URL；前端仍调用 `/api/v1/ai/chat/stream`；
- 不需要新增数据库表或修改现有数据发布脚本；
- 不需要上传医疗 CSV、模型文件或 `.env`；
- 不需要为每种新问题单独写一个前端按钮，通用语义路由会先尝试已登记的白名单分析能力。

如果健康检查正常但 AI 返回“暂无可用分析能力”或“聚合数据不可用”，优先检查 `AGGREGATE_DATA_SOURCE=mysql`、MySQL 连接参数和 ACTIVE 聚合批次，不要通过放开任意 SQL 来绕过安全边界。

本次升级后的模型故障恢复只解决“规划/总结模型不可用”这一层；它不能替代 MySQL 或 ACTIVE 聚合批次。如果页面仍显示“AI 服务暂时不可用”，先看后端实际连接的 MySQL 主机、端口、账号和数据库，再检查 DeepSeek 配置。

## 7. 回滚

若部署后出现异常，保留当前日志和提交号，然后回到上一个已验证提交重新部署并重启后端、前端。禁止使用强制推送覆盖远程分支；回滚完成后再根据日志修复。
