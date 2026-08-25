# 医数云策系统架构与环境

## 1. 架构目标

系统需要让同一批住院运营指标可生成、可发布、可查询、可展示和可核对。每一层只承担一类责任，避免在数据任务、API 和页面中分别维护不同的计算逻辑。

```text
原始层：HDFS 中的 SPARCS CSV（Hive 外部表提供结构化访问）
    ↓
计算层：PySpark 读取 HDFS/Hive，清洗、聚合、模型训练
    ↓
工件层：分析快照 JSON、模型 JSON
    ↓
服务结果层：MySQL analysis_snapshot_result
    ↓
接口层：Flask /api/v1
    ↓
展示层：Vue Router + D3 SVG
    ↓
解释层：DeepSeek + 白名单分析工具
```

HDFS 保存正式分析使用的原始副本，Hive 提供外部表和字段检查；PySpark 的清洗、聚合和模型逻辑保持不变。HDFS/Hive 不重复生成另一套正式汇总结果，MySQL 继续承担前端查询服务结果的发布与读取。

## 2. 组件职责

| 组件 | 输入 | 输出 | 不承担的工作 |
|---|---|---|---|
| PySpark 数据任务 | HDFS CSV 或 Hive 外部表 | 统一分析快照 | HTTP 服务、页面展示 |
| PySpark 模型任务 | HDFS CSV 或 Hive 外部表 | 高费用模型与指标工件 | 个人诊断、治疗判断 |
| MySQL | 经过校验的分析快照 | 可按模块和实体键读取的服务结果 | 原始 CSV 存储、指标重算 |
| Flask | MySQL 或联调快照 | 白名单 API 响应 | 原始数据聚合、页面排序 |
| Vue / D3 SVG | Flask 响应 | 指标卡、图表、表格和交互状态 | 数据库访问、正式指标重算 |
| DeepSeek 工具层 | 用户问题与汇总 API | 带来源、版本和统计边界的回答 | 自由 SQL、原始明细访问、多轮记忆 |
| HDFS / Hive | 原始 CSV 副本与外部表 | PySpark 的正式输入、集群与表结构检查 | 指标的重复计算、服务结果发布 |

## 3. 统一分析快照

分析结果统一使用 `(module_key, entity_key)` 定位。每条记录包含 `payload_json`、`data_version` 和 `generated_at`。同一批发布中的所有模块共享同一个数据版本和生成时间。MySQL 发布在一个事务中完成；校验或写入失败时整批回滚，读接口不会看到半批数据。

主要模块键为 `dashboard`、`hospitals`、`diseases`、`cohorts`、`costs`、`risks`、`payments`、`data_quality` 和 `high_cost_model`。Payload、实体键和筛选顺序见 [公共产品契约](07-terminal-product-contract.md)。

## 4. 数据源模式

后端通过环境变量显式选择数据源：

| 变量 | 值 | 含义 |
|---|---|---|
| `ANALYTICS_DATA_SOURCE` | `fixture` | 读取仓库内联调快照 |
| `ANALYTICS_DATA_SOURCE` | `mysql` | 读取 MySQL 统一分析快照 |
| `TOP10_DATA_SOURCE` | `fixture` / `mysql` | 疾病病例量 TOP10 独立接口的数据源 |
| `AGGREGATE_DATA_SOURCE` | `mysql` | 受控语义问数读取 ACTIVE 聚合事实表 |

未设置或填写未知值时，后端返回配置错误，不会自动把联调数据当作真实结果。

## 5. 运行环境

### 5.1 本机应用环境

| 软件 | 基线 | 用途 |
|---|---|---|
| Python | 3.11 | Flask、测试和数据脚本 |
| PySpark | 3.4.0 | 全量清洗、聚合和模型训练 |
| Java | 8 或 17 | PySpark 运行时 |
| Node.js | 22 LTS | Vue 与 Vite |
| npm | 10 | 前端依赖与构建 |
| MySQL | 8.0 | 真实服务结果存储 |

`backend/requirements.txt` 管理 Flask 服务依赖，`data/requirements.txt` 管理 PySpark 数据依赖，`frontend/package-lock.json` 固定前端依赖。

### 5.2 课程虚拟机环境

三节点环境使用 Hadoop 3.3.4、Hive 3.1.3、MySQL 8.0.30 和 Java 8。PySpark 仍按原有本地模式执行清洗、聚合和模型训练，但原始数据改由虚拟机中的 HDFS/Hive 提供；运行任务的终端需要能够读取对应的 Hadoop/Hive 配置。虚拟机没有 `spark-submit` 不影响本项目的本地 PySpark 处理方式。

### 5.3 默认地址

| 服务 | 地址 |
|---|---|
| Flask | `127.0.0.1:5000` |
| Vite | `127.0.0.1:5173` |
| MySQL | 由 `backend/.env` 配置，默认端口 `3306` |

前端开发服务器把 `/api` 代理到 Flask。跨主机部署时使用 `frontend/.env` 的 `VITE_API_BASE_URL` 或反向代理保持 `/api/v1` 同源。

## 6. 文件与配置边界

```text
backend/.env                              本机运行配置，不提交
backend/.env.example                      配置字段示例
frontend/.env                             可选前端地址配置，不提交
data/sql/002-analysis-snapshot.sql        统一快照表结构
data/src/run_full_analytics_pyspark.py    分析快照生成入口（支持 HDFS/Hive 输入）
data/src/train_high_cost_model_pyspark.py 模型训练入口（支持 HDFS/Hive 输入）
data/src/run_sparcs_top10_pyspark.py     TOP10 服务结果入口（支持 HDFS/Hive 输入）
data/src/storage_input.py                 原始数据存储输入适配层
data/src/publish_analytics_snapshot_mysql.py
                                          MySQL 发布入口
```

不得提交完整 CSV、数据库密码、API 密钥、真实 `.env`、完整分析快照或模型工件。仓库只保存固定样例、代码、契约和可公开的验证摘要。

## 7. 失败处理

- CSV 结构、年份或关键字段不符合契约时，数据任务停止且不发布部分结果；
- 快照结构、版本或时间不一致时，发布器拒绝写入；
- MySQL 连接失败时，API 返回 `DATABASE_UNAVAILABLE`；
- 模块结果不存在时，API 返回 `RESULT_NOT_READY`；
- 合法筛选没有记录时，API 返回带版本信息的空结果；
- DeepSeek 密钥缺失、超时或网络失败时，AI 接口返回真实错误，不生成替代答案；
- 结构化语义规划和证据回答默认使用 DeepSeek thinking mode；旧版工具多轮仍按兼容协议传递消息；
- 前端在请求失败时清除旧指标和图表，显示错误类型、追踪编号和重试入口。

启动、发布和排障命令见 [开发与运行手册](04-development-and-runbook.md)。
