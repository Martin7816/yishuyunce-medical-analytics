# Issue #76 验收证据

执行日期：2026-08-20（Asia/Shanghai）。本证据只记录接口代码、固定 fixture 和本机已有的 #75 风格模型工件；完整模型工件不进入 Git。

## 交付范围

- `HighCostModelService` 首次成功请求加载并缓存 JSON 工件，校验版本、截距、八个公开特征和类别权重；缺失工件返回 `503 RESULT_NOT_READY`，损坏或结构错误返回 `500 SERVER_MISCONFIGURED`。
- 预测请求只接受 `age_group`、`gender`、`race`、`ethnicity`、`hospital_service_area`、`facility_id`、`admission_type`、`emergency_indicator` 八个非空字符串字段。
- 收费、成本、住院时长、出院去向、手术和目标字段返回 `400 LEAKAGE_FIELD_FORBIDDEN`；普通额外字段、缺字段、空值和无可用 `OTHER` 桶的非法类别返回 `400 INVALID_REQUEST_FIELD`。
- `GET /api/v1/models/high-cost/metrics` 读取 `high_cost_model/metrics` 快照；`POST /api/v1/models/high-cost/predict` 严格 POST-only，预测逻辑集中在 Service。

## 验收矩阵

| 编号 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| M-01 | 指标快照和字段 | PASS：模型版本、阈值、八个特征、五项指标和混淆矩阵均可读取 | `backend/tests/test_high_cost_model_api.py::test_metrics_and_prediction_expose_the_frozen_contract` |
| M-02 | 高/低费用预测 | PASS：fixture 同时覆盖 `HIGH_COST` 与 `NOT_HIGH_COST` | 同上 |
| M-03 | OTHER 类别 | PASS：未见 `facility_id` 归一化为 `OTHER`，概率按截距与类别权重 sigmoid 计算 | `test_prediction_uses_sigmoid_and_normalizes_unknown_categories_to_other` |
| M-04 | 泄漏字段 | PASS：8 类收费/成本、住院时长、出院、手术、目标字段逐项返回专用错误码 | `test_prediction_rejects_each_known_leakage_field` |
| M-05 | 请求边界 | PASS：额外字段、缺字段、空字符串、非法类别、非 JSON、非对象和非 POST 方法均有稳定错误 | 同文件对应参数化测试 |
| M-06 | 未发布/坏工件/缓存 | PASS：未发布 503、损坏/缺字段 500、成功工件修改后仍返回缓存结果 | `test_prediction_reports_unpublished_model_and_corrupt_configuration`、`test_successful_artifact_is_cached_after_first_request` |
| M-07 | #75 风格真实工件 | PASS：重复预测结果一致，`fixture_only=false`；`model_version=high_cost_lr_seed_20260818_185808e20900`；`data_version=sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` | 本机 `D:\HuaDi\analytics-output\high-cost-model.json` 适配器检查 |

## 验证命令

```text
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_high_cost_model_api.py -q
23 passed

.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_high_cost_model_api.py backend\tests\test_analytics_api.py -q
47 passed

.\backend\.venv\Scripts\python.exe -m pytest backend\tests --ignore=backend\tests\test_disease_analytics_api.py data\tests -q
82 passed, 3 skipped
```

完整 `backend/tests data/tests` 回归还受到工作区原有 `backend/tests/test_disease_analytics_api.py` 未提交改动影响：`test_unknown_diagnosis_code_is_rejected_without_profile_lookup` 期望 `details.parameter=diagnoses`，当前路由返回 `diagnosis_code`。本任务未修改该文件或相关疾病接口。

## 下游交接

- 模型页面可使用指标接口返回的 `model_version`、`threshold_amount`、`feature_names`、`metrics` 和 `sections`，预测结果中的 `fixture_only` 用于显示联调边界。
- 真实环境必须设置 `HIGH_COST_MODEL_PATH`，并让模型工件与已发布 `high_cost_model/metrics` 快照使用同一 `data_version`；fixture 版本不得当作真实效果。
