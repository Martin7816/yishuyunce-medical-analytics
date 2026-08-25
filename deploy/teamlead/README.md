# 组长电脑部署包

本目录用于内部验收部署。它只提供配置模板和启动脚本，不携带数据库、API key、密码或 SSH 私钥。

## 1. 获取代码

在组长电脑上使用 GitHub 私有仓库和当前交付分支：

```powershell
git clone -b test/assistant-integrated git@github.com:Martin7816/yishuyunce-medical-analytics.git
cd yishuyunce-medical-analytics
```

如果最终合并到了 `main`，将上面的分支替换为 `main`。

## 2. 创建本地配置

```powershell
Copy-Item deploy\teamlead\backend.env.example backend\.env
Copy-Item deploy\teamlead\frontend.env.example frontend\.env
Copy-Item deploy\teamlead\ssh-tunnel.config.ps1.example deploy\teamlead\ssh-tunnel.config.ps1
```

编辑 `backend\.env`：

- 填入真实 `DEEPSEEK_API_KEY`
- 填入真实 `MYSQL_PASSWORD`
- 默认保持 `MYSQL_HOST=127.0.0.1`、`MYSQL_PORT=3307`
- 保持 `ANALYTICS_DATA_SOURCE=mysql`
- 保持 `AGGREGATE_DATA_SOURCE=mysql`

编辑 `deploy\teamlead\ssh-tunnel.config.ps1`：

- 填入 SSH 用户名
- 填入 SSH 主机
- 填入 SSH 私钥绝对路径
- 根据实际网络确认 `$RemoteHost`

这些本地配置文件已被 Git 忽略，禁止复制回仓库或发送到聊天工具。

## 3. 安装运行依赖

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
cd ..
```

运行时不需要在组长电脑重新执行 Spark、publish 或 activate。ACTIVE aggregate 已经存在于 MySQL。

## 4. 启动顺序

打开三个 PowerShell 窗口。

窗口一，保持 SSH tunnel 运行：

```powershell
.\deploy\teamlead\start-ssh-tunnel.ps1
```

窗口二，启动 Flask：

```powershell
.\deploy\teamlead\start-backend.ps1
```

窗口三，启动 Vue：

```powershell
.\deploy\teamlead\start-frontend.ps1
```

浏览器访问 `http://127.0.0.1:5173/assistant`。

## 5. 只读验证

先检查后端：

```powershell
curl.exe http://127.0.0.1:5000/api/v1/health
```

再在浏览器或 API 中测试：

- 哪些疾病病例数量最多？
- Medicare 患者平均费用是多少？
- 某患者费用是多少？（必须安全拒绝）

AI SSE 请求入口是 `/api/v1/ai/chat/stream`，请求体字段必须是：

```json
{"message":"哪些疾病病例数量最多？"}
```

## 6. 不要做的事情

- 不要把 `backend\.env`、SSH 私钥、MySQL 密码或 DeepSeek key 上传 GitHub。
- 不要在组长电脑重新 publish 或 activate aggregate。
- 不要把 SPARCS 原始 CSV、数据库 dump 或 patient-level 数据放进仓库。
- 不要把 `fixture` 配置用于真实验收。

期望 ACTIVE batch：

`agg_11bb8c5caa79132304785ca2245c8a68cb1812687f2417f6`
