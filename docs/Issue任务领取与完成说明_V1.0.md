# 医数云策组员 Issue 任务领取与完成说明 V1.0

> 给全组成员的最短操作说明。以后项目任务统一在 GitHub Issues 领取、执行、验收和关闭，不再只靠群聊分配。

## 一、Issue 是什么

Issue 就是一张项目任务卡，说明要解决什么问题、谁负责、依赖什么、交付什么以及怎样证明完成。

Issue 不一定都是写代码，也可能是开会决策、检查数据、查阅材料、制作原型或完成一次验证。

项目仓库：
<https://github.com/Martin7816/yishuyunce-medical-analytics>

项目总地图：
<https://github.com/Martin7816/yishuyunce-medical-analytics/issues/3>

## 二、先看懂标签

| 标签 | 含义 | 主要工作 |
|---|---|---|
| `wayfinder:map` | 总地图 | 查看整体路线 |
| `wayfinder:grilling` | 讨论和决策 | 开会、询问成员、形成结论 |
| `wayfinder:task` | 实际检查或准备 | 执行检查、整理事实、完成前置工作 |
| `wayfinder:research` | 资料研究 | 查一手材料，写出有来源的结论 |
| `wayfinder:prototype` | 原型验证 | 做草图、响应样例或交互原型 |

看到标签不代表马上写代码，先读 Issue 的 `Question`。

## 三、怎样找到可以领取的任务

### 网页操作

1. 打开项目 GitHub 页面，点击 `Issues`；
2. 找状态为 `Open` 的 Issue；
3. 优先选择没有 `Blocked by`、没有负责人、且自己能完成的 Issue；
4. 阅读标题、`Question`、标签、依赖和评论；
5. 在右侧 `Assignees` 中选择自己；
6. 评论说明：`我已认领，将在……前提交……`。

不要只在群里说“我来做”。没有分配到 GitHub Issue，就不算正式领取。

### 命令行操作

在仓库根目录执行：

```powershell
gh issue list --state open --limit 50
gh issue view <Issue编号> --comments
gh issue edit <Issue编号> --add-assignee "@me"
```

## 四、领取前检查

- [ ] Issue 仍是 Open；
- [ ] 没有其他负责人；
- [ ] 没有未关闭的阻塞 Issue；
- [ ] Question 能读懂；
- [ ] 输入资料、输出和验收标准明确；
- [ ] 没有和别人重复。

有阻塞就先说明缺少什么，不要硬领或静等。

## 五、领取后怎么做

1. 阅读项目概况、`CONTEXT.md` 和相关数据/API/验收文档；
2. 在 Issue 评论中写执行计划、预计输出和时间；
3. 如果涉及代码，从最新 `main` 创建短分支：

```powershell
git switch main
git pull --ff-only origin main
git switch -c feature/<Issue编号>-<简短名称>
```

4. 只修改当前 Issue 相关文件；
5. 先用固定样例或 Mock 得到可检查结果，再接真实上游；
6. 每完成一个小结果就 Commit，并在 Issue/PR 中记录；
7. 不私自修改公共字段、指标、表、API、端口或环境版本；
8. 遇到阻塞立即在 Issue 中说明。

不涉及代码的 Issue，直接在 Issue、文档、数据检查结果或原型文件中留下证据，不为“有提交”而写无用代码。

### 5.1 如何拆分可并行的 Issue

如果一个工作同时包含设计、实现、联调和验收，应先按阶段拆分，而不是让所有人等待同一个 Issue 完成：

- `#10 前`：做页面原型、固定样例、验收清单、测试用例和证据模板；
- `#10 后`：按冻结的接口完成正式适配、联调、实际运行和最终验收；
- 前置 Issue 的完成，不代表正式功能已经完成；
- 后置 Issue 要写清楚 `Blocked by`、需要使用的输入和最终验收条件。

写 Issue 时分别说明“现在可以做什么”和“必须等待什么”。能独立完成的准备工作不应被未完成的接口或代码阻塞；但没有正式契约时，不得把临时字段、示例数据或猜测的错误码写成最终标准。这样既能让成员并行推进，也能避免联调时出现无法判断责任的返工。

## 六、不同标签怎样完成

### `wayfinder:grilling`

完成标准是“人做出了决定”，不是“讨论过”。记录同意、异议、处理方式、待确认事项和同步的文档。不能替其他成员或老师做决定。

### `wayfinder:task`

完成标准是事实或前置结果已经取得。例如数据核验要交付真实列名、类型、缺失、异常、固定样例、运行命令和对后续任务的影响。

### `wayfinder:research`

完成标准是报告可复查，必须有来源、定位、结论和仍不确定的内容。

### `wayfinder:prototype`

完成标准是原型足够让大家作出决定。原型不等于正式功能完成。

## 七、提交代码和 PR

完成修改后检查：

```powershell
git status
git diff --name-only
git diff
git add <相关文件>
git diff --cached --name-only
git commit -m "type(scope): 简短说明"
git push -u origin HEAD
```

然后在 GitHub 创建 PR：

- `base` 选择 `main`；
- `compare` 选择自己的任务分支；
- 关联当前 Issue；
- 写清修改内容、验证命令、实际结果和已知限制；
- 邀请相关上下游 Review。

PR 合并前，代码任务不能算完成。

## 八、怎样写完成评论

关闭 Issue 前，先评论：

```markdown
## Resolution

### 已完成
- ……

### 证据
- 文件 / PR：……
- 执行命令：……
- 实际结果：……

### 对下游的影响
- 下游现在可以使用……
- 仍需注意……
```

不要只写“完成了”“数据看完了”“GPT 已经生成代码”。

## 九、什么时候可以关闭 Issue

只有满足以下条件才能关闭：

- [ ] Question 已经真正回答；
- [ ] 输出、结论或代码已经存在；
- [ ] 有文件、PR、命令、截图或来源作为证据；
- [ ] 公共文档已同步；
- [ ] 下游知道怎样使用结果；
- [ ] 已写 `Resolution` 评论；
- [ ] 没有隐藏未解决事项。

网页中发布评论后点击 `Close issue`；命令行：

```powershell
gh issue close <Issue编号> --comment "已完成，证据见 Resolution 评论。"
```

以下情况不能关闭：刚开始做、只创建分支或 PR、只有 GPT 代码、还在等待别人、没有验证、下游无法使用。

## 十、关闭后怎么处理

Wayfinder 决策 Issue 关闭后，需要把一句话结论追加到总地图的 `Decisions so far`。通常由组长完成；详细证据留在原 Issue。

```markdown
- [Issue标题](Issue链接) — 一句话说明结论和对后续工作的影响。
```

如果结论产生了新问题，创建新的子 Issue，不要把新问题塞进旧 Issue。

## 十一、当前项目示例

### 数据核验 Issue

```text
认领 → 检查真实 CSV → 记录列名/类型/缺失/异常
→ 制作脱敏样例和期望结果 → 写 Resolution → 关闭
→ 通知指标、后端和组长继续使用
```

### 全组范围确认 Issue

```text
认领 → 发项目概况 → 收集五人同意或异议
→ 处理异议并更新概况 → 写全组结论
→ 关闭 → 由组长更新 Wayfinder 地图
```

## 十二、记住这句话

> 先在 GitHub Issue 领取任务，再按 Question 执行；用证据证明结果，写 Resolution 后才能关闭；不确定就标记阻塞，不要自己猜。
