# 医数云策

医数云策是第2组自主确定的智慧医疗运营数据分析项目。当前已完成工程边界和 VMware/CentOS 集群环境基线，业务代码仍按下游 Issue 逐步实现。

## 当前唯一目标

第一轮只完成“疾病病例量 TOP10”真实数据闭环：

```text
真实 CSV
  → HDFS 原始层
  → Spark 唯一正式清洗与 TOP10 聚合
  → Hive 元数据/检查（不重复计算）
  → 服务结果
  → Flask API
  → Vue + ECharts
  → 独立核对
```

在这个闭环完成前，不同时铺开大量页面、复杂 AI、登录和平台化建设；后续扩展按课程交付需要和实际展示价值决定。

## 开始阅读

1. [项目概况](docs/00-project-overview.md)：项目做什么、不做什么、第一轮目标和五人分工；
2. [业务术语](CONTEXT.md)：病例量、住院出院记录、主诊断描述和住院记录群体；
3. [M0/M1 架构与环境边界](docs/03-architecture-and-env.md)：最小链路、存储边界、启动顺序和降级方案；
4. [Agent 协作规则](AGENTS.md)：Issue tracker、标签和领域文档配置。

项目任务与决策依赖见 GitHub [Wayfinder 地图](https://github.com/Martin7816/yishuyunce-medical-analytics/issues/3)。

## 当前事实边界

- 老师提供的医疗 DOCX 和第1组工件是样例，不代表第2组必须原样实现；
- 第2组按本项目概况自主确定首轮技术链路和验收基线；学校或课程后续明确提出的要求再纳入对应扩展；
- 数据中的一行代表一次住院出院记录，不等于唯一患者；
- 完整原始数据、密码、Token、API Key、`.env` 和个人绝对路径不得提交 Git。

架构边界已经固定；VM 中 Hadoop/HDFS 三节点和 MySQL 基线已有实机证据，HiveServer2、Spark 正式任务、API 和前端复现由 Issue #12 及下游 Issue 补充。本 README 必须始终反映 `main` 的真实可运行状态，不提前写未实现功能。

## 配置与依赖的归属

- `backend/app/config.py` 属于后端 Python 代码，放在 `backend/app/`；它只负责读取环境变量并组织配置，不保存密码、Token 或 API Key。
- `backend/.env.example` 只描述后端运行所需的环境变量；真实的 `backend/.env` 仅存在于本地，并且必须写入 `.gitignore`。
- `backend/requirements.txt` 只维护后端 Python 运行和测试依赖。前端依赖继续由 `frontend/package.json` 管理；未来确实形成独立运行环境的数据或 AI 模块，再在对应模块维护自己的依赖文件。
- 根目录不再默认放后端的 `.env.example`、`.env` 或 `requirements.txt`。只有在全组确认整个仓库长期共用同一个 Python 环境时，才可以重新提议统一到根目录，并同步修改本规范、启动说明和验证脚本。
- 如果前端确实需要环境变量，使用 `frontend/.env.example` 单独描述；前端和后端不得共用含义不清的环境变量名。
