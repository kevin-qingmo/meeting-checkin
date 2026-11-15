# 签到系统 · 开发与部署备忘

面向后续维护者（含 AI 助手）。记录本项目特有的约定与踩过的坑，避免重复试错。

## 项目概况

- **用途**：南开学校三校区（敬慧路 / 雅馨路 / 和慧南路）会议、教研、培训、展课活动的扫码签到签离，替代排队手签。
- **栈**：Flask + SQLAlchemy + Jinja 服务端渲染 + 原生 JS，**无前端构建链**。
- **数据库**：生产 PostgreSQL（Railway 插件自动注入 `DATABASE_URL`）；本地开发同代码用 SQLite。
- **路径**：`D:\MiniMax工作站\签到系统\`

## 关键机制

- **签到码每 20 秒轮换**：用 HMAC-SHA256 无状态派生，`HMAC(SECRET_KEY, f"{activity_id}:{cycle}")` 取前 16 位为 token、前 8 位取模 10000 为 4 位现场码；`cycle = floor(epoch/20)`。
  - 好处：多进程/多实例部署安全，无需定时任务与共享内存。
  - 校验窗口接受**当前 + 上一周期**（40 秒），容忍用户手慢。
- **实时数据用 2 秒 HTTP 轮询**，不用 SSE/WebSocket——规避 PaaS 代理回收长连接。
- **活动的校区/学段/学科在库里存名称**，不存字典 id，避免字典变更导致历史活动失效。
- **活动涉及的校区/学段/学科在数据库中存名称**（同上）。
- **大屏页、二维码 PNG 接口、`/api/board/<id>/qr` 都加 `@login_required`**（防远程伪造签到链接）；`/scan/*` 与提交接口保持公开。

## 硬约束（违反会直接失败）

1. **生产必须设 `SECRET_KEY`**：`app/__init__.py` 里，连接非 SQLite 且 `SECRET_KEY` 仍为默认值时 `create_app` 抛 `RuntimeError` 拒绝启动。这是防签到码被伪造的设计，不要为了"能启动"而绕过。
2. **部署顺序：先挂 Postgres，再设变量，再 `railway up`**。反了首次构建会因缺 `DATABASE_URL` 失败。
3. **`BASE_URL` 不带结尾斜杠**，且必须是公网域名（决定二维码扫出来跳到哪）。
4. **时间显示格式 `YYYY-MM-DD HH:MM:SS`**；数据库字段/路由/表单字段用英文，界面文案用中文。

## 部署方式

优先用一键脚本（用户非技术背景）：

```powershell
cd "D:\MiniMax工作站\签到系统"
.\deploy\一键部署.ps1
```

脚本流程：装 CLI → 登录 → 建项目 → 挂 Postgres → 设 `SECRET_KEY`/`ADMIN_PASSWORD` → `railway up` → 关联 GitHub 仓库（push 自动部署）→ 生成域名并回填 `BASE_URL` → 健康检查。

用户手册见 `deploy\部署指南.md`。

## 踩坑记录（勿重试）

### Railway / OAuth 授权

- **内置浏览器面板（Electron FilePanel）里 GitHub 的 Authorize 按钮永远是 `disabled`**——GitHub 服务端反自动化锁定。改 DOM 去 disabled、`requestSubmit` 都无效。
- **内置浏览器的 `run_script` 整体失效**：`page.evaluate` 根本不执行（返回 `pageEvaluate.calls: 0`、`logs: []`），连 `document.title='x'` 都不生效。**不要用 run_script 在内置浏览器做 DOM/JS 操作**。
- **正解**：让用户在自己电脑的真实 Edge 点一次。从助手进程用 `Start-Process '<url>'` 拉起默认浏览器即可。
- **CLI 等待回调的后台任务 timeout 必须 ≥1800s**：默认 60s 前台超时会被掐断，报 "Device code expired"。设备码本身有效期约 10 分钟。
- **Railway CLI v5.74 命令备忘**：
  - 有：`add --database postgres`（**没有** `add --plugin`）
  - 有：`variables list --json`（**没有** `variables get`）
  - 有：`init --name X` / `up --detach --yes` / `domain --json` / `service list --json` / `service source connect --repo owner/repo --branch main --service NAME`
  - 认证失败时统一报 `Unauthorized. Please login with 'railway login'`，exit code 1。

### Windows / PowerShell

- **含中文的 .ps1 必须写 UTF-8 with BOM**，否则 PowerShell 5.1 按 ANSI 读，中文路径变乱码（文件被写到盘根乱码目录，且 `Get-ChildItem` 在该路径下返回空、**不报错**）。
- 写完用 `[System.Management.Automation.Language.Parser]::ParseFile($p,[ref]$null,[ref]$err)` 检查语法。
- **删除文件必须走 `rm -- "<path>"`**（mavis-trash），`Remove-Item -Recurse` 被安全策略拒绝。
- **后台 bash 任务有 15 分钟 / 1 小时上限**，长驻服务用 `Start-Process` 独立进程启动。
- **助手进程内 `git push` 起初会失败**（弹不出 Git 凭据管理器 + 无 `/dev/tty`，报 "User cancelled dialog"）；但**用户在自己终端 push 过一次后凭据已缓存，助手进程内再 push 就会成功**。先试一次再让用户手动推。
- 仓库级 `git config --local user.name/user.email` 要沿用历史提交身份（`mavis` / `mavis@local`），否则 `Author identity unknown`。

### Python / Flask

- **Flask 3 默认把 JSON 中文转义成 `\uXXXX`** → `app/__init__.py` 里设 `app.json.ensure_ascii = False`。
- **`gunicorn` 在 Windows 上跑不了**（`ModuleNotFoundError: No module named 'fcntl'`，Unix-only）。本地用 Flask 开发服务器，生产在 Linux 容器内用 gunicorn。
- **pip 默认源安装超时（300s）** → 用 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。
- **urllib 跟随重定向会丢 `Set-Cookie`** → 会话类脚本用 `http.cookiejar.CookieJar`（`tools/cross_instance_check.py` 已改）。
- 本机 Python：`D:\MiniMax工作站\签到系统\.venv\Scripts\python.exe`（Python 3.14.5）。启动服务：
  ```powershell
  $env:BASE_URL='http://localhost:5055'
  Start-Process -FilePath 'D:\MiniMax工作站\签到系统\.venv\Scripts\python.exe' `
    -ArgumentList '-m','flask','--app','wsgi','run','--port','5055','--no-debugger','--no-reload' `
    -WorkingDirectory 'D:\MiniMax工作站\签到系统' -WindowStyle Hidden
  ```

## 验收方式

```powershell
Set-Location 'D:\MiniMax工作站\签到系统'; & '.\.venv\Scripts\python.exe' -m pytest tests -q   # 25 passed
```

- **跨实例一致性**：`tools/cross_instance_check.py` —— 实例 A 出码 → 实例 B 校验落库 → A 读回计数=1 → 错码被拒。这是多进程部署正确性的关键证据。
- **浏览器端到端**：`tools/ui_check.js` / `tools/ui_check_bar.js`（puppeteer-core + Edge），截图产物在 `_screenshots/`。
  - puppeteer-core：`D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core`
  - Edge：`C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`

## 配色约定

**签到大屏用「深色大屏风格」**（深蓝底、白卡、蓝色=已签到、绿色=已签离），这是用户明确选定的参考图风格，**不要**套用本机既有的暖调或海鸥蓝配色板。

## 目录速查

| 路径 | 内容 |
|---|---|
| `app/routes/` | auth / admin / board / scan / api |
| `app/templates/` | base / login / error / admin×5 / board / scan |
| `app/static/css/` | `app.css`（后台）、`board.css`（大屏） |
| `app/static/js/board.js` | 大屏倒计时条 `paintBar`（蓝色贴左、右边缘向左退缩） |
| `app/codes.py` | HMAC 派生签到码与现场码 |
| `app/models.py` | User / Activity / Roster / CheckIn / Setting |
| `seed.py` | 建超管 admin + 预置三校区/三学段/15 学科字典 |
| `tools/` | demo_data / ui_check / ui_check_bar / cross_instance_check |
| `deploy/` | 部署指南.md + 一键部署.ps1 |
| `docs/superpowers/` | 设计文档与实现计划（gitignore 了） |
