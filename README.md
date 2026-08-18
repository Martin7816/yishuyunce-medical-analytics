# 医数云策

医数云策是第 2 组自主确定的医疗运营数据分析产品。当前终局实现分支覆盖 10 个模块：运营驾驶舱、医院、疾病、群体、费用成本、病情风险、支付、数据质量、高费用分类模型，以及 AI 问答与洞察报告。

疾病 TOP10 是已经验证的 M1 最小闭环，接口 `/api/v1/diseases/top10` 保持兼容；它不是最终产品边界。终局任务和依赖统一维护在 [Wayfinder #37](https://github.com/Martin7816/yishuyunce-medical-analytics/issues/37)。

## 架构

```text
真实 CSV
  → HDFS 原始副本 / Hive 外部表检查
  → 本机 PySpark 一次清洗并生成统一分析快照与模型工件
  → MySQL 单事务发布
  → Flask 白名单 API
  → Vue Router 十页面 / DeepSeek 白名单工具
```

不实现登录权限、个人诊断、自由 SQL、多轮记忆、Redis、微服务、Kubernetes、3D 可视化和本地大模型部署。数据中的一行代表一次住院出院记录，不等于唯一患者。

## 快速启动（联调快照）

联调快照的版本以 `fixture:` 开头，只用于并行开发和页面状态验证，不代表真实全量结论。

```powershell
# 后端
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run.py

# 另开终端启动前端
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173/overview`。Vite 将 `/api` 转发到本机 Flask。AI 页面只有配置 `DEEPSEEK_API_KEY` 后才调用云端服务；缺少密钥会返回真实配置错误，不生成假答案。

## 真实数据发布

完整 CSV、真实 `.env`、密钥和大型工件不得提交 Git。

```powershell
python -m pip install -r data/requirements.txt
python data/src/run_full_analytics_pyspark.py `
  --input "<完整 SPARCS CSV>" `
  --output "<临时目录>\analytics-snapshot.json"

python data/src/train_high_cost_model_pyspark.py `
  --input "<完整 SPARCS CSV>" `
  --artifact "<临时目录>\high-cost-model.json" `
  --metrics "<临时目录>\high-cost-metrics.json" `
  --snapshot "<临时目录>\analytics-snapshot.json"

python data/src/publish_analytics_snapshot_mysql.py `
  --input "<临时目录>\analytics-snapshot.json" --apply
```

先在 MySQL 执行 `data/sql/002-analysis-snapshot.sql`，再设置 `ANALYTICS_DATA_SOURCE=mysql` 和 `HIGH_COST_MODEL_PATH`。事务发布失败会回滚；所有模块必须共享同一个 `data_version` 和 `generated_at`。

## 验证

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests data/tests -q
cd frontend
npm run build
```

已实现测试覆盖响应信封、读取接口、白名单筛选、合法空结果、费用筛选互斥、模型泄漏字段拒绝、AI 工具来源与数据版本追踪，以及快照发布契约。真实 CSV、MySQL、DeepSeek 和组长电脑的端到端验收仍须按 [终局验收文档](docs/06-test-and-acceptance.md) 留存证据后才能关闭对应 Issue。

## 文档入口

- [项目概况](docs/00-project-overview.md)
- [数据与可行性](docs/01-data-and-feasibility.md)
- [指标与数据契约](docs/02-metrics-and-data-contract.md)
- [架构与环境](docs/03-architecture-and-env.md)
- [开发与运行手册](docs/04-development-and-runbook.md)
- [API 契约](docs/05-api.md)
- [测试与验收](docs/06-test-and-acceptance.md)
- [终局产品冻结契约](docs/07-terminal-product-contract.md)

老师提供的医疗材料和第 1 组工件仅作参考，不代表第 2 组已完成的内容。README 只描述当前代码可运行的边界；真实验收状态以 Issue 证据为准。
