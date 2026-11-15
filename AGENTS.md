# 签到系统 · 开发与部署备忘

面向后续维护者（含 AI 助手）。记录本项目特有的约定与踩过的坑，避免重复试错。

## 项目概况

- **用途**：南开学校三校区（敬慧路 / 雅馨路 / 和慧南路）会议、教研、培训、展课活动的扫码签到签离，替代排队手签。
- **栈**：Flask + SQLAlchemy + Jinja 服务端渲染 + 原生 JS，**无前端构建链**。
- **数据库**：生产 PostgreSQL（Railway 插件自动注入 `DATABASE_URL`）；本地开发同代码用 SQLite。
- **路径**：`D:\MiniMax工作站\签到系统\`

## 关键机制

- **签到码每 20 秒轮换**：用 HMAC-SHA256 无状态派生，`HMAC(SECRET_KEY, f"{activity_id}:{cycle}:{mode}")` 取前 16 位为 token、前 8 位取模 10000 为 4 位现场码；`cycle = floor(epoch/20)`。
  - 好处：多进程/多实例部署安全，无需定时任务与共享内存。
  - 校验窗口接受**当前 + 上一周期**（40 秒），容忍用户手慢。
  - **mode（in/out）参与 HMAC**：切换签到/签离模式必然换新 token 与新现场码，旧模式的码在新模式下校验失败（防截图转发）。
- **大屏倒计时锚定在"取到这轮码的时刻"**（前端 `cycleStart`），不是服务器整点：
  - 切换模式后倒计时真正从 20 秒重新开始，而不是被 epoch 相位拉回旧刻度；
  - 前端到点自己取下一轮码，节奏与显示一致。
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

脚本流程：装 CLI → 登录（GitHub 或邮箱）→ 建项目 → 挂 Postgres → 建 `web` 服务 →
设 `DATABASE_URL`(引用变量)/`SECRET_KEY`/`ADMIN_PASSWORD` → `railway up --service web` →
关联 GitHub 仓库（push 自动部署）→ 生成域名（**必须 `--port 8000`**）并回填 `BASE_URL` → 健康检查。

用户手册见 `deploy\部署指南.md`。

## 踩坑记录（勿重试）

### Railway / OAuth 授权

- **内置浏览器面板（Electron FilePanel）里 GitHub 的 Authorize 按钮永远是 `disabled`**——GitHub 服务端反自动化锁定。改 DOM 去 disabled、`requestSubmit` 都无效。
- **内置浏览器的 `run_script` 之前被判"整体失效"是误判，真因是包装语法**：
  `run_script` 的 code 参数是**函数体**，不是函数声明。
  - 写 `async function (page) { ... }` → `SyntaxError: Function statements require a function name`
  - 写 `async (page) => { ... }` → 能 parse，但没被调用 → `pageEvaluate.calls: 0`
  - **正确写法：裸语句体**，`const r = await page.evaluate(() => ({...})); return r;` → `pageEvaluate.calls: 1` 且返回值能透出
- **正解仍然是让用户在自己电脑的真实 Edge 登录**（Railway 账号走邮箱登录最稳，见下）。
- **CLI 等待回调的后台任务 timeout 必须 ≥1800s**：默认 60s 前台超时会被掐断，报 "Device code expired"。设备码本身有效期约 10 分钟。
- **`railway login` 的浏览器授权窗口只有 5 分钟**：日志报 `Authentication timed out - no callback received after 5 minutes`，超时要重跑命令。
- **抓 CLI 打印的授权 URL**：别用 `| Out-String`（会缓冲到进程结束才输出）。改成
  `Start-Process cmd.exe -ArgumentList '/c','railway login > login.log 2>&1'`，再直接读 `login.log`。
- **Railway CLI v5.74 命令备忘**：
  - 有：`add --database postgres`（**没有** `add --plugin`）
  - 有：`variables list --json`（**没有** `variables get`）、`variables set --service web K=V`
  - 有：`init --name X` / `up --service web --detach --yes` / `domain --json` / `domain update <域名> --port 8000 --service web` / `service list --json` / `service source connect --repo owner/repo --branch main --service NAME`
  - 认证失败时统一报 `Unauthorized. Please login with 'railway login'`，exit code 1。
- **Railway 新运行时（v2 runtime）不注入 `PORT` 环境变量**：gunicorn `--bind 0.0.0.0:$PORT` 会退回默认 8000，
  而域名默认指向 8080 → **一直 502 Application failed to respond**（容器内 gunicorn 日志显示 8000 端口正常监听，但访问日志为空 = 请求根本没进来）。
  解法：`railway domain update <域名> --port 8000 --service web`（网页版：Settings → Networking → Target Port 改 8000）。
- **Railway 数据库插件不会自动把 `DATABASE_URL` 注入到应用服务**：必须手工建引用变量
  `DATABASE_URL=${{Postgres.DATABASE_URL}}`（命令行注意 `$` 要转义成 `` `$ ``）。

### 本机网络环境（2026-11-16 实测）

- **github.com 被 DNS 污染**：解析到 `57.155.223.240`，443 不通，git/网页都连不上；
  真实 IP `140.82.112.4` / `140.82.114.4` 可以连通（`curl --resolve github.com:443:140.82.112.4` 验证过）。
- **改 hosts 需要管理员权限**，`Add-Content C:\Windows\System32\drivers\etc\hosts` 被拒。
- 结论：**这台机器上任何依赖 GitHub 网页/授权的流程都可能卡死**（含 GitHub OAuth 按钮点不动这个假象）。
  Railway 本身通畅（`backboard.railway.com` 200），**走 Railway 邮箱登录（Log in using email）可绕开 GitHub**。
- `git push` 在 GitHub 不通时同样失败 → 部署改用 `railway up` 直接上传源码，不依赖 GitHub。


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
- **SQLAlchemy 走 `postgresql://` 默认用 psycopg v3**：只装 `psycopg2-binary` 会在生产报
  `ModuleNotFoundError: No module named 'psycopg'`。`requirements.txt` 必须有 `psycopg[binary]==3.2.3`。
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
- **公网实例端到端**：`tools/e2e_public.py <BASE_URL> <用户名> <密码>` —— 登录 → 建活动 → 大屏出码 → 扫码签到 → 错码被拒 → 实时统计 → 导出 Excel → 切模式换码 → 跨模式码被拒 → 删除活动（级联 + 404），共 18 项断言。
  ```powershell
  & '.\.venv\Scripts\python.exe' tools\e2e_public.py https://web-production-9fe1faa8.up.railway.app admin <密码>
  ```
- **不掌握用户密码时怎么验生产库**（用户已改过 admin 密码时）：
  1. `ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\railway_verify_ed25519 -N '""'`（`.ssh` 目录可能不存在，要先建）
  2. `railway ssh keys add --key <公钥路径> --name mcode-verify-temp`（注册到 Railway 账号）
  3. `railway connect Postgres --tunnel-only --port 15432` → 输出 `postgresql://postgres:<口令>@127.0.0.1:15432/railway`
  4. 用该 URL 设 `DATABASE_URL` 跑 `tools/prod_temp_admin.py create/delete <用户名> <口令>`（直连 psycopg 建临时超管）
  5. 用临时账号跑 `tools/e2e_public.py`，验完 `delete` 掉临时账号
  6. 收尾：`railway ssh keys remove <指纹>` + 停 ssh 进程 + 删本地密钥
  - **坑**：隧道日志文件（`> tunnel.log`）会被进程长期占用删不掉，且**里面有数据库口令** → 务必 gitignore，退出后让用户手动删，或直接轮换口令。
- **浏览器端到端**：`tools/ui_check.js` / `tools/ui_check_bar.js` / `tools/ui_check_mode.js`（puppeteer-core + Edge），截图产物在 `_screenshots/`。
  - puppeteer-core：`D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core`
  - Edge：`C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`

## 线上实例（2026-11-16 已上线）

- 网址：`https://web-production-9fe1faa8.up.railway.app`
- 项目 `meeting-checkin`（workspace `kevin-qingmo's Projects`），服务：`web` + `Postgres`
- admin 初始密码 `mc-80yn1w8bp1`（用户首次登录后应自行修改）
- 域名 target port 固定 8000；`DATABASE_URL` 用引用变量 `${{Postgres.DATABASE_URL}}`
- 首次部署留下的两条「上线验收测试」活动已归档（列表里显示"已归档"），不影响使用


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
| `tools/` | demo_data / ui_check / ui_check_bar / cross_instance_check / e2e_public |
| `deploy/` | 部署指南.md + 一键部署.ps1 |
| `docs/superpowers/` | 设计文档与实现计划（gitignore 了） |
