# Issue #51 执行证据：疾病画像分析数据快照

执行日期：2026-08-19（Asia/Shanghai）。真实 CSV、完整快照和数据库凭证不进入 Git；仓库只保留可复查的摘要、公式和命令。

## 输入与版本

| 项目 | 实际值 |
|---|---|
| 文件名 | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 文件大小 | `832373138` bytes |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-19T00:00:00.000000Z` |

## 实现与公式

- `run_full_analytics_pyspark.py` 读取一次原始 CSV，持久化统一 clean frame，再生成 `diseases/index` 和每个 `diseases/profile:{diagnosis_code}`；疾病枚举按编码排序，不再人为截断 1000 项。
- `verify_disease_snapshot.py` 只使用 Python 标准库流式读取 CSV，独立重算诊断枚举、TOP10、每个 profile 的记录数、平均住院时长、平均收费/成本、急诊/外科/重症率，以及年龄、性别、严重程度、死亡风险、操作 TOP5、医院 TOP5。
- 金额只对可解析的非负值求平均；`120 +` 按 120 天计入；比率分母是当前诊断编码的住院出院记录数；空分组不进排行，排行按值降序、名称升序。

## 固定边界样例

命令：

```powershell
python data/src/run_full_analytics_pyspark.py `
  --input data/fixtures/dashboard_edge_sample.csv `
  --output "<临时目录>\issue51-edge.json" `
  --module all `
  --generated-at 2026-08-19T00:00:00Z
python data/src/verify_disease_snapshot.py `
  --input data/fixtures/dashboard_edge_sample.csv `
  --snapshot "<临时目录>\issue51-edge.json"
```

结果：`PASS`；4 条原始记录、3 条可纳入记录、2 个诊断编码、2 个 profile、0 个空 profile。`END003` 的 `120 +`、负收费和外科/重症率，以及 `RSP009` 的金额和急诊率均通过独立核对。摘要见 [`fixed-disease-verify.json`](fixed-disease-verify.json)。

## 真实全量

命令：

```powershell
python data/src/run_full_analytics_pyspark.py `
  --input "<本地完整 CSV>" `
  --output "<临时目录>\issue51-real-full.json" `
  --module all `
  --generated-at 2026-08-19T00:00:00Z
python data/src/verify_disease_snapshot.py `
  --input "<本地完整 CSV>" `
  --snapshot "<临时目录>\issue51-real-full.json"
```

PySpark 结果：`PASS`，2,101,588 条原始记录，690 条基础快照记录。独立疾病核对：`PASS`，477 个诊断编码、477 个 profile、0 个空 profile；疾病 TOP10、全部 profile 指标和六类分区逐项一致。摘要见 [`real-disease-verify.json`](real-disease-verify.json)。

真实样例中 `BLD001` profile 的独立核对值为：记录数 5,494，平均住院时长 3.87 天，平均收费 46,512.55 美元，平均成本 13,960.22 美元，急诊率 0.9394，重症率 0.2377；年龄、性别、严重程度、死亡风险、操作和医院分区分别有 5、2、4、4、5、5 项。

## 发布与 MySQL 状态

为保留同一批次已有的模型记录，将模型记录合并回真实基础快照后，发布工件共 691 行；发布器 dry-run 为 `PASS`，见 [`publish-dry-run.json`](publish-dry-run.json)。

本轮 `--apply` 未完成：工作区 `.env` 中的 `192.168.219.128:3306` 超时，工作区数据库说明中的 `192.168.57.16:3306` 也未连通；因此没有声称 MySQL PASS，也没有发生删除旧快照的事务。当前状态是 `BLOCKED`，原因是共享 MySQL/VM 未运行或地址不可达，不是代码或快照校验失败，见 [`mysql-blocked.json`](mysql-blocked.json)。

VM/数据库恢复后，使用管理员确认的最新地址加载环境变量并依次执行：

```powershell
python data/src/publish_analytics_snapshot_mysql.py `
  --input "<临时目录>\issue51-final-snapshot.json" `
  --apply
python data/src/verify_disease_snapshot.py `
  --input "<本地完整 CSV>" `
  --snapshot "<临时目录>\issue51-final-snapshot.json" `
  --mysql
```

预期：发布 691 行；`diseases` 模块查询 478 行（`index` 加 477 个 profile），payload、主键、`data_version` 和 `generated_at` 全部一致。仓库已有的发布器回滚单元测试覆盖完整性校验失败时旧批次仍可读；本次真实数据库回滚证据需在数据库恢复后补录。

## 下游交接

- 后端读取 `diseases/index` 和 `diseases/profile:{diagnosis_code}`，白名单值来自 `index.payload.options.diagnoses`，不在请求时重新聚合或排序。
- 前端 index 使用 `top10`；profile 使用 `age`、`gender`、`severity`、`mortality`、`procedures`、`hospitals`，所有指标沿用快照返回顺序和单位。
- 当前真实版本为上表 `data_version`，所有模块共享同一 `generated_at`；fixture 只能用于并行联调，不能替代真实 success。
