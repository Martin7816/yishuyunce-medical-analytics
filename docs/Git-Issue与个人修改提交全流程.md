# Git Issue 与个人修改提交全流程

> 适用于一个 Issue、一个功能、一个 Bug 或一次独立的个人修改。  
> 核心原则：一个任务一个分支，一个分支一个 Pull Request，不直接在 main 上开发。

## 一、先确定这次要做什么

每次开发前，先在 GitHub 创建或确认一个 Issue。

Issue 至少写清楚：

- 要解决什么问题；
- 准备修改哪些内容；
- 完成后怎样验收；
- 是否需要测试或更新文档。

如果只是很小的文档修改，也建议使用一个独立分支，不要和其他任务混在一起。

## 二、分支名称怎么写

实际开发不要只使用姓名缩写，应该使用“类型/编号-简短描述”：

```text
feat/123-login
fix/456-order-timeout
docs/789-update-readme
refactor/321-user-service
chore/654-update-dependencies
```

常用类型：

- feat：新增功能；
- fix：修复问题；
- docs：修改文档；
- refactor：重构代码；
- chore：依赖、配置或其他维护工作。

其中的编号通常是 Issue 编号。

## 三、开始任务前同步 main

进入项目根目录，确认当前没有不属于自己的未提交修改：

```powershell
cd "你的项目路径\项目文件夹"
git status
```

如果看到其他人的修改，不要执行 git restore 或 git reset，先联系项目负责人。

然后同步 main：

```powershell
git switch main
git pull --ff-only origin main
```

含义：

- git switch main：切换到稳定分支；
- git pull：下载 GitHub 上最新的代码；
- --ff-only：避免自动产生不清楚的合并提交。

## 四、为任务创建分支

例如 Issue 编号是 123，任务是增加登录功能：

```powershell
git switch -c feat/123-login
```

确认当前分支：

```powershell
git branch
```

应该看到：

```text
* feat/123-login
  main
```

从现在开始，只在 feat/123-login 分支上修改代码。

## 五、开发、测试、检查修改范围

先编写代码或修改文档，然后在本地测试。

查看修改了哪些文件：

```powershell
git status
git diff --name-only
```

查看具体修改内容：

```powershell
git diff
```

重点确认：

- 修改的文件都属于当前 Issue；
- 没有修改其他业务模块；
- 没有混入格式化或临时文件；
- 没有提交密码、Token 或本地配置；
- 代码或文档已经完成基本测试。

如果发现无关文件，不要继续提交，先恢复或联系负责人确认。

## 六、只把相关文件加入暂存区

不要未经检查直接使用 git add .。

推荐指定文件：

```powershell
git add src/login.js
git add tests/login.test.js
```

如果本次修改的是文档：

```powershell
git add docs/xxx.md
```

检查暂存区：

```powershell
git diff --cached --name-only
```

这里列出的文件，才会进入下一次 Commit。

如果误加了无关文件，只取消暂存，不会删除本地文件：

```powershell
git restore --staged -- path/to/unrelated-file
```

## 七、创建 Commit

确认暂存区文件正确后提交：

```powershell
git commit -m "feat: add login feature"
```

提交信息要说明本次做了什么：

```text
feat: add login feature
fix: resolve order timeout
docs: update project guide
refactor: simplify user service
chore: update dependencies
```

一次 Commit 尽量只完成一个小目标。一个 Issue 可以有多个 Commit，但不要把多个 Issue 混在一个分支中。

查看提交：

```powershell
git log -1 --oneline --decorate
```

## 八、把分支推送到 GitHub

第一次推送当前分支：

```powershell
git push -u origin HEAD
```

含义：

```text
本地 feat/123-login
        ↓ push
GitHub 上的远程 feat/123-login
```

这一步不会修改 main。

后续继续修改同一个任务时：

```powershell
git add 相关文件
git commit -m "说明本次修改"
git push
```

同一个 Pull Request 会自动更新。

## 九、创建 Pull Request

进入 GitHub 仓库，点击 Pull requests → New pull request。

确认：

```text
base：main
compare：feat/123-login
```

意思是：

> 把远程 feat/123-login 分支的修改申请合并到 main。

PR 标题：

```text
feat: add login feature
```

PR 内容建议写：

```markdown
## 修改内容

- 增加登录接口
- 增加登录测试

## 关联 Issue

Closes #123

## 测试结果

- npm test
- 已手动测试登录成功和失败场景

## 修改范围

只修改了登录相关代码，没有修改其他业务模块。
```

## 十、审查意见怎么处理

如果负责人提出修改意见，不要关闭 PR，也不要重新创建分支。

直接在原分支继续修改：

```powershell
git status
git add 相关文件
git commit -m "fix: address review comments"
git push
```

推送后，原来的 Pull Request 会自动更新。

负责人重点审查：

- 功能是否符合 Issue；
- 修改范围是否合理；
- 测试是否通过；
- 是否影响其他模块；
- 是否存在安全或数据风险。

## 十一、谁来 Merge

Pull Request 通过代码审查和自动测试后，由项目负责人或具有合并权限的维护者点击：

```text
Merge pull request
→ Confirm merge
```

普通组员只负责：

```text
开发 → Commit → Push → 创建 PR → 修改审查意见
```

项目负责人或维护者负责：

```text
Review → 确认测试 → Merge 到 main
```

main 分支只接受经过审查的 Pull Request。

## 十二、合并后同步本地 main

PR 合并后，每个人都要同步本地代码：

```powershell
git switch main
git pull --ff-only origin main
```

删除已经完成的本地分支：

```powershell
git branch -d feat/123-login
```

如果 GitHub 页面提供 Delete branch，也可以删除远程分支。

## 十三、一天内的完整命令清单

以 Issue #123 登录功能为例：

```powershell
# 进入项目根目录
cd "你的项目路径\项目文件夹"

# 同步 main
git switch main
git pull --ff-only origin main

# 创建任务分支
git switch -c feat/123-login

# 编写代码并测试

# 查看修改
git status
git diff --name-only
git diff

# 添加相关文件
git add src/login.js
git add tests/login.test.js

# 检查暂存区
git diff --cached --name-only

# 创建提交
git commit -m "feat: add login feature"

# 推送分支
git push -u origin HEAD

# 然后在 GitHub 创建：
# feat/123-login → main
```

## 十四、没有 Issue 时怎么办

如果确实没有 Issue：

1. 先明确本次修改的目标；
2. 创建一个简短任务记录，或请负责人确认；
3. 按任务创建分支；
4. 不要把多个无关修改放到同一个分支。

例如：

```powershell
git switch -c docs/update-project-guide
```

## 十五、常见问题

### 1. git add 是不是提交到 GitHub

不是。

```text
git add       工作区 → 暂存区
git commit    暂存区 → 本地分支
git push      本地分支 → GitHub 远程分支
Pull Request  申请合并到 main
Merge         真正进入 main
```

### 2. 为什么 main 没有变化

因为你只执行了 Commit 或 Push。只有 Pull Request 被 Merge 后，main 才会变化。

### 3. 出现 Permission denied

说明当前账号没有向该仓库推送的权限。请联系仓库负责人添加 Collaborator，或者使用 Fork 流程。

### 4. 出现 LF will be replaced by CRLF

这是 Windows 换行格式提示，不是错误，可以继续操作。

### 5. 出现 not a git repository

说明当前终端没有进入项目根目录。重新进入包含 .git 文件夹的项目目录。

### 6. 发现自己改了无关文件

先不要 Commit，执行：

```powershell
git status
git diff --name-only
```

确认范围后，只添加当前任务相关文件。

## 十六、使用 AI 开发时的固定要求

给 AI 的任务说明应包含：

```text
本次任务只允许修改与 Issue #123 直接相关的文件。
不要修改其他业务模块，不要进行无关重构或批量格式化。
如果必须修改范围外文件，请先说明原因并等待确认。
完成后列出修改文件、修改原因和测试结果。
```

AI 修改完成后，必须自己检查：

```powershell
git status
git diff --name-only
git diff --cached --name-only
```

## 十七、最终标准

```text
一个 Issue
→ 一个开发分支
→ 只修改相关文件
→ 检查 diff
→ git add
→ git commit
→ git push
→ Pull Request 到 main
→ Review + CI
→ 负责人 Merge
→ 本地同步 main
```



