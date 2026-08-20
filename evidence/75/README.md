# Issue #75 执行证据：高费用病例分类模型

执行日期：2026-08-20（Asia/Shanghai）。真实 CSV、完整模型工件和完整统一快照只保留在本机临时工件目录，不进入 Git；本目录保存可复查的版本摘要、指标、命令输出和下游加载结果。

## 输入与版本

| 项目 | 实际值 |
|---|---|
| 文件名 | `Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv` |
| 文件大小 | `832,373,138` bytes |
| SHA-256 | `185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `data_version` | `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` |
| `generated_at` | `2026-08-20T00:00:00.000000Z` |
| 真实原始/纳入记录 | `2,101,588 / 2,101,588` |

共享清洗函数已修正真实 CSV 的 `Hospital Service Area` 列映射，并保留旧的 `Health Service Area` 兼容别名；最终模型的 `hospital_service_area` 实际学习到 8 个类别。

## 交付结果

- 训练脚本：[`data/src/train_high_cost_model_pyspark.py`](../../data/src/train_high_cost_model_pyspark.py)
- 共享列映射：[`data/src/run_full_analytics_pyspark.py`](../../data/src/run_full_analytics_pyspark.py)
- 依赖清单：[`data/requirements.txt`](../../data/requirements.txt)
- 实际模型版本：`high_cost_lr_seed_20260818_185808e20900`
- 训练集：`1,681,301` 条；测试集：`420,287` 条
- 训练集收费 P75 阈值：`77,202.39` 美元
- 系数向量宽度：`253`；八个特征均记录了 learned category、encoder category、编码宽度和 `OTHER` 未知桶

完整 `high-cost-model.json`、`high-cost-metrics.json` 和带模型记录的 `analytics-snapshot.json` 在本机临时目录中生成，运行手册明确不提交真实工件。这里的摘要文件对应同一批次：[`artifact-summary.json`](l2-data-task/DT-MODEL-01/artifact-summary.json)、[`high-cost-metrics.json`](l2-data-task/DT-MODEL-01/high-cost-metrics.json)、[`train-run1-stdout.json`](l2-data-task/DT-MODEL-01/train-run1-stdout.json)、[`train-run2-stdout.json`](l2-data-task/DT-MODEL-01/train-run2-stdout.json) 和 [`reproducibility.json`](l2-data-task/DT-MODEL-01/reproducibility.json)。

## 执行命令与结果

```powershell
python data/src/run_full_analytics_pyspark.py `
  --input "<本地完整 CSV>" `
  --output "<临时目录>\analytics-snapshot.json" `
  --generated-at 2026-08-20T00:00:00Z

python data/src/train_high_cost_model_pyspark.py `
  --input "<本地完整 CSV>" `
  --artifact "<临时目录>\high-cost-model.json" `
  --metrics "<临时目录>\high-cost-metrics.json" `
  --snapshot "<临时目录>\analytics-snapshot.json" `
  --repetitions 2 `
  --reproducibility "<临时目录>\reproducibility.json"

python data/src/verify_dashboard_snapshot.py `
  --input "<本地完整 CSV>" `
  --snapshot "<临时目录>\analytics-snapshot.json"

python data/src/publish_analytics_snapshot_mysql.py `
  --input "<临时目录>\analytics-snapshot.json"
```

实际输出摘要：[`snapshot-stdout.json`](l2-data-task/DT-MODEL-01/snapshot-stdout.json)、[`dashboard-verify.json`](l2-data-task/DT-MODEL-01/dashboard-verify.json) 和 [`publish-dry-run.json`](l2-data-task/DT-MODEL-01/publish-dry-run.json)。快照独立核对为 `PASS`，最终发布器 dry-run 为 `PASS`、`7,198` 条记录，其中模型记录为新增的 1 条。

## 验收矩阵

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| MD-01 | 切分/阈值顺序 | `PASS`：先以 seed `20260818` 做 `0.8/0.2` 切分，再只在训练集计算 `percentile_approx(Total Charges, 0.75, 10000)` | 训练脚本、`high-cost-metrics.json` |
| MD-02 | 泄漏检查 | `PASS`：pipeline 只接收 8 个允许字段；收费、成本、住院时长、离院/手术及其他非允许清洗列均在排除清单中 | `artifact-summary.json`、源码回归测试 |
| MD-03 | 评估 | `PASS`：Accuracy、Precision、Recall、F1、AUC、TN/FP/FN/TP 和训练/测试规模齐全；零分母返回稳定 `0` | `high-cost-metrics.json` |
| MD-04 | 可复现 | `PASS`：连续两次训练全部检查通过，系数最大绝对差 `6.277012243316449e-11`，容差 `1e-6` | 两次 stdout、`reproducibility.json` |
| MD-05 | 工件可读 | `PASS`：后端直接加载真实 artifact，未知机构编号落入 `OTHER`，返回 `fixture_only=false`；预测边界保持运营分类，不作诊疗建议 | [`predict-real.json`](l2-data-task/DT-MODEL-01/predict-real.json) |
| MD-06 | 版本一致 | `PASS`：artifact、metrics、统一快照和后端预测均使用同一 `data_version`；模型版本为 `high_cost_lr_seed_20260818_185808e20900` | `high-cost-metrics.json`、`dashboard-verify.json` |

## 下游交接

- #76 可直接把本次真实 artifact 配置到 `HIGH_COST_MODEL_PATH`，沿用八字段请求、`OTHER` 未知桶、`model_version` 和 `data_version`。
- #77/模型页面可从同一快照读取训练/测试规模、五项指标、混淆矩阵、阈值和版本；真实版本不显示 fixture 提示。
- 预测结果只代表高费用记录的运营分类，不表示个人诊断、治疗或因果判断。
- 真实 MySQL `--apply`、API HTTP 和页面截图仍属于 #76/#77 的独立验收范围；本 Issue 不用固定 fixture 指标代替真实模型结果。
