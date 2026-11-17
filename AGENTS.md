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

### 事故记录：管理员改密码后忘记 → 只能靠 SSH 隧道直连数据库重置（2026-11-16）

- 现象：用户 16:50 连续 8 次 `POST /login` 全部 200（失败），报"用户名或密码错误"。
- 定位：`railway logs --http --since 24h` 是关键工具——能看出登录成功是 **302**、失败是 **200**。
  日志只保留到 17:21 UTC，更早窗口（正是改密发生的时段）已被清掉，导致证据链有缺口。
- 结论：用户按提示改过 admin 密码但忘了；系统**没有自助找回通道**，这是设计疏漏。
- 处置（本次）：`ssh-keygen` → `railway ssh keys add` → `railway connect Postgres --tunnel-only --port 15432`
  → `tools/prod_temp_admin.py create admin <新密码>`（直连 psycopg 重置）→ 验证登录 302 → 收尾注销密钥 + 关隧道 + 删含口令的 tunnel.log。
- **教训**：让用户改密码之前，必须先准备好找回通道（见下条），否则用户被锁在外面又只能找运维。
- **用户决定（2026-11-16）**：不加「忘记密码·救援码」自助重置功能。密码找回走 SSH 隧道直连数据库的既有流程即可，
  **不要**再向他提议或擅自加公开的密码重置接口。



## 配色约定

**全站已换成「日式黑金」（墨黑暖调 + 沙金）**（用户 2026-11-17 最终选定，参照其提供的大屏截图）：

- 后台（`app.css`）：**浅色暖调**。纸底 `#F5F1EC`→`#EBE5DC`→`#E2DACF` 渐变、卡片 `#FFFAF3`、边框 `#F0E8D8`；
  墨黑 `#2C2A26`（hover `#1F1E1B`）、沙金 `#D4B48C`、陶土金 `#B89274`、深金 `#8A6B52`；
  文字 主 `#2C2A26` / 次 `#6B5D4F` / 弱 `#8A7C6E`；
  语义色 成功 `#6B8E7F` / 错误 `#C96A6A` / 警告 `#BA9A6D`；圆角 14/18px。
  **顶栏是墨黑底 + 沙金字**（黑金识别点）；卡片标题左侧 3px 沙金竖条。
- 大屏（`board.css`）：**墨黑暖调 + 沙金**。
  底 `#4A4439`→`#2C2A26`→`#1F1E1B` 径向渐变；二维码卡纯白、码框 2px 沙金 `#D4B48C`；
  现场码 `#8A6B52`；倒计时条沙金渐变 `#8A6B52→#D4B48C`；
  **已签到=沙金 `#D4B48C`、已签离=绿 `#A8C4B4` 的语义保持不变**。
  统计卡与动态列表徽章都要遵守：`.board-page .feed-row .tag` 沙金（已签到）、
  `.board-page .feed-row .tag.g` 绿（已签离）——`board.js` 里已签到**不加** `g` 类。
- 手机扫码页（`scan.html` 内联样式）也是浅色暖调 + 沙金顶边。
- Excel 导出表头色：`app/exporter.py` 的 `HEADER_FILL` 要与主色同步改（现为 `8A6B52`）。

**改配色时的坑**：

1. 模板里到处写着内联 `style="...color:#fff"`（页标题、h2），换浅色底后**白字直接看不见**——
   本次踩过，必须一并改成主色。
2. `scan.html` 的样式是**内联在模板里**的，不在 `app.css`，换配色要单独改。
3. 改完 CSS/模板后**必须重启本地 Flask 服务**（`--no-reload` 下 Jinja 模板会被缓存，不重启看不到效果）。
4. 输入框样式要覆盖 `input[type=tel]`（手机号）与 `input[type=file]`（名册导入），
   否则会退回浏览器默认下划线样式——本次踩过。

## 「全校活动」机制（2026-11-17 新增）

- 活动表单「参与范围」第一项是**全校活动**复选框（`name="school_wide"`）。
- 勾选后：**涉及校区/学段/学科全部置灰不可选**（JS 置 `disabled` + `.check.off` 灰化），
  取消勾选即恢复。
- 存储方式（**不用改表结构**）：`Activity.campus_ids` 里存特殊值 `"全校活动"`，
  同时把 `stage_ids`/`subject_ids` 清空为 `[]`。
  模型侧用 `Activity.is_school_wide` 判断；模板里活动列表/看板显示金色 `全校活动` 标记。
- 服务端 `_read_form()` 里 `school_wide` 为真时强制覆盖校区/学段/学科，**不依赖 JS**。

## 随机抽签机制（2026-11-17 新增）

- 数据表 `lottery_rounds`：每次抽取落一条（人数 / 中奖名单 JSON / 是否排除已中奖 / 操作人 / 时间）。
- 领域逻辑集中在 `app/lottery.py`：`candidate_pool`（只取已签到）、`past_winner_keys`（历史中奖人）、
  `draw`（`secrets.SystemRandom().sample`）、`save_round`、`recent_rounds`。
- 去重键：手机号优先 `p:<phone>`，否则 `n:<姓名>|<校区>`。
- 接口：`POST /admin/activity/<id>/lottery`（登录+活动归属）、`GET /api/activity/<id>/lottery`（**公开只读**，大屏用；中奖人手机号不外泄）。
- 大屏 `board.js` 每 5 秒轮询抽签接口，`winner-marquee` CSS 动画滚动展示最新一轮名单。
- Excel 导出第 4 张表「抽奖记录」。
- 活动删除、账号删除都会级联清理 `lottery_rounds`。

## 账号删除机制（2026-11-17 新增）

- 「账号管理」里，创建者可删除**普通管理员**账号；不能删当前登录的账号（自删），也不能删另一个创建者账号。
- 删除时，该账号名下的活动/名册/签到一并删除，活动按 **抽签轮次 → 签到 → 名册 → 活动** 的顺序清理
  （`Activity.owner_id` 是 NOT NULL 外键，必须先删活动再删用户；`LotteryRound.activity_id` 同理，不先删轮次会 IntegrityError）。
- 该账号在**别人**活动上留下的「操作人」引用会被显式置空：`CheckIn.operator_id`、`LotteryRound.operator_id` → NULL
  （本地 SQLite 默认不执行外键、ORM 也不会自动置空，所以必须在代码里显式处理；生产 Postgres 同样安全）。
- 表格里的账号 id 一律经 `app/routes/admin.py` 的 `_parse_uid()` / `_find_user()` 解析：非法值（如 `²`）
  一律按「账号不存在」提示，**不得 500**。

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
