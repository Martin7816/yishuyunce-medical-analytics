# 前端（L4 页面层）验收记录与交接

> 记录时间：2026-08-18T06:49Z（UTC）
> 结论：本机 **BLOCKED**（无 Node.js/npm），运行时证据引用 #25 **RECORD_LEVEL_EVIDENCE**；本机可执行部分（源码边界静态核对）PASS。

## 本机限制

本机（胡钰炜电脑）未安装 Node.js 与 npm（`node`/`npm` 命令不存在，常见安装目录未发现），因此无法在本机执行：

```powershell
cd frontend
npm ci
npm run build
npm run dev
```

## #25 记录级证据（可复查位置）

- Issue #25 Resolution（2026-08-18T04:00:21Z）：`npm ci`、`npm run build` 通过；真实 API 联调 HTTP 200、10 项、`unit=discharge_records`、真实 `data_version`；页面四态、重试、长名称 Tooltip、并列顺序、390px/1280px 窗口、控制台无 error/warning 全部 PASS。
- Issue #26 评论（#25 交接，2026-08-18T03:59:50Z）：启动命令、Mock 复现步骤、证据范围与已知限制。
- `docs/06-test-and-acceptance.md` “Issue #25 页面正式接口适配记录”：UI-01—UI-08 结果与证据说明。
- main 提交：页面适配 `e36f70a`，验收记录 `3ca67c9`。

## 本机完成的静态源码核对（PASS）

对 `frontend/src/` 逐项静态核对（2026-08-18，工作树 SHA `3ca67c9`）：

| 检查项 | 结果 | 依据 |
|---|---|---|
| 页面不重新计算 TOP10 | PASS | `App.vue`/`diseaseTop10.js` 无 `.sort()`/`groupBy`/聚合/截断逻辑；唯一 `slice(0, maxLength)` 是坐标轴显示省略号（`truncateText`），不作用于数据顺序 |
| 不直连数据库/HDFS/Spark | PASS | `src/` 无 `mysql`/`pymysql`/`hdfs`/`spark` 引用 |
| 请求只发 GET、无请求体 | PASS | `diseaseTop10.js` 仅 `method: 'GET'`，无 `body` |
| Mock 不能冒充正式验收 | PASS | Mock 仅在显式 `VITE_TOP10_MODE=mock` 时启用（`App.vue:12`、`:219`），默认正式 API 模式 |
| 病例量单位文案 | PASS | “有效住院出院记录数量，不表示患者人数”（`App.vue:347`），单位从 `unit=discharge_records` 映射 |
| 前端契约校验 | PASS | `diseaseTop10.js` 校验 `metric`、`unit`、`data_version`、`generated_at`、`items≤10`、`rank/case_count` 整数、名称非空，异常统一映射稳定 `code` |
| loading 清空旧结果 | PASS | `loadData` 先 `clearResult()` 再置 `loading`（`App.vue:216-217`） |

## 组长电脑 HANDOFF 复现清单（按 docs/06 第 8 章）

```powershell
# 1. 前端（需 Node.js；组长电脑实测 v22.13.1 / npm 10.9.2）
cd frontend
npm ci
npm run build
npm run dev

# 2. 四态复现（Mock，仅状态触发）
$env:VITE_TOP10_MODE='mock'
$env:VITE_TOP10_MOCK_STATE='success'   # 或 loading/empty/error
npm run dev

# 3. 正式模式：另开终端启动后端（backend/.env 为 MySQL 模式）
cd backend
python run.py
# 页面访问 http://localhost:5173，同时记录 API 响应与页面 DOM/截图
```

证据保存位置：按 `evidence/26/l4-page/` 命名约定，保存截图（含浏览器尺寸）、同刻 API 响应、触发状态方式说明；不得进入 Git 的内容按 docs/06 第 9.2 节执行。
