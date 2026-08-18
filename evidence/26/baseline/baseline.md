# Issue #26 验收基线

> 记录时间：2026-08-18T06:49Z（UTC）
> 执行人：hu-yuwei（岗位5 正式验收）
> 分支：`test/26-m1-final-acceptance`，与 `main`/`origin/main` 同一提交，工作树干净

## Git 基线

| 项目 | 值 |
|---|---|
| HEAD SHA | `3ca67c978453ea40cda4cfcffa931e9f88c4a753` |
| origin/main | `3ca67c978453ea40cda4cfcffa931e9f88c4a753`（git ls-remote 实测一致） |
| 分支 | `test/26-m1-final-acceptance`（`main..HEAD` 为空，无未合并提交） |

## 本机环境

| 项目 | 实测值 | 备注 |
|---|---|---|
| 操作系统 | Windows 11 家庭中文版 10.0.26200 | 本机（胡钰炜），非组长电脑 |
| Python | 3.11.15（conda 环境 `csupy311`） | 与 docs/04 记录的环境名一致 |
| PySpark | 3.4.0 | 与 docs/04 的 `pyspark==3.4.0` 一致 |
| Flask | 3.1.3 | requirements 允许区间内 |
| PyMySQL | 2.2.8 | 仅用于 API 依赖失败路径；本机未连接真实 MySQL |
| pytest | 9.1.1 | |
| python-dotenv | 已安装 | `backend/.env` 在本机不存在 |
| Java | PATH 为 Temurin JDK 17.0.20；`JAVA_HOME` 指向 JDK 21 | 运行 PySpark 时临时改用 JDK 17（Spark 3.4 与 JDK 21 不兼容，JDK 17 正常） |
| Node.js / npm | **未安装** | 前端运行时验收在本机 BLOCKED，见 evidence/26/l4-page/ |

## 数据版本

| 版本 | 说明 |
|---|---|
| `fixture:sparcs_mvp_sample:v1` | 固定样本逻辑核对版本（本机复验） |
| `sparcs_2021_20231012_sha256_185808e20900c0499f7974d5ac9c05f0909df506bc088a244443bff895ca2219` | 真实 SPARCS 2021 全量版本（#31 记录级证据；本机无完整 CSV，未复跑） |

## API 契约状态

`docs/05-api.md` V1.0，状态 `FROZEN`（2026-08-18，Issue #10 Resolution 与真实服务结果复核后冻结，提交 `3ca67c9`）。

## 上游 Issue 状态（GitHub API 快照，2026-08-18T06:31Z 获取）

| Issue | 标题 | 状态 | 关闭时间（UTC） |
|---|---|---|---|
| #10 | 确定疾病病例量TOP10 API契约 | closed（completed） | 2026-08-18T03:11:17Z |
| #25 | 完成 TOP10 页面正式接口适配与联调（#10 后） | closed（completed） | 2026-08-18T04:00:31Z |
| #31 | feat(data): 完成疾病病例量 TOP10 数据任务与服务结果发布 | closed（completed） | 2026-08-18T02:10:43Z |
| #26 | 补全并执行 M1 TOP10 全链路验收（#10 后） | open（本 Issue，执行中） | — |

#26 最新评论：`#31 已提供真实数据和 API 联调证据…`（2026-08-18T02:05:53Z）与 `#25 页面联调交接`（2026-08-18T03:59:50Z），均按只读方式核对。
