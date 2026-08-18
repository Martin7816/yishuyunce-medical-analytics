# TOP10 页面

## 正式 API 模式（默认）

先启动 Flask API：

```powershell
cd backend
python -m pip install -r requirements.txt
python run.py
```

另开终端启动前端：

```powershell
cd frontend
npm install
npm run dev
```

前端默认请求 `GET /api/v1/diseases/top10`。Vite 开发服务器会把 `/api` 代理到 `http://127.0.0.1:5000`；跨主机或预览环境可在 `frontend/.env` 设置 `VITE_API_BASE_URL`。

正式模式只渲染 API 返回的 `data.items`，不在浏览器重新聚合、排序、截断或连接数据库。

## Mock 状态复现

Mock 必须显式开启，仅用于页面状态检查：

```powershell
$env:VITE_TOP10_MODE='mock'
$env:VITE_TOP10_MOCK_STATE='success'
npm run dev
```

页面上的状态按钮可以复现 `loading`、`success`、`empty`、`error`；错误状态的“重新加载”会重新走 success Mock。正式 success 证据必须使用后端 API，不能用 Mock 替代。

## 页面验收要点

- success：逐项对照 `rank`、`diagnosis_name`、`case_count`、`unit`、`data_version` 和 `generated_at`；
- empty：HTTP 200 且 `data.items=[]` 时显示空状态；
- error：非 2xx 时显示安全提示、错误码和重试入口，不展示旧数据或堆栈；
- loading：请求未结束时不显示旧结果；
- 长名称：坐标轴可省略，悬浮提示保留完整诊断名称；
- 窗口变化：图表 resize，不改变 API 返回顺序。
