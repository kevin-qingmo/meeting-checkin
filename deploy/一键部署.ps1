<#
  会议扫码签到系统 · 一键部署到 Railway
  用法：
      cd "D:\MiniMax工作站\签到系统"
      .\deploy\一键部署.ps1

  脚本会自动完成：
    1. 安装 Railway CLI（若未安装）
    2. 登录（会弹出 Edge，需要你点一次 GitHub 的 Authorize，只此一次）
    3. 创建项目 meeting-checkin
    4. 挂 PostgreSQL 数据库插件
    5. 上传代码并构建
    6. 关联 GitHub 仓库（以后 git push 即自动重新部署）
    7. 生成公网域名、回填 BASE_URL
    8. 健康检查验证

  完成后终端会打印网址和 admin 密码。
#>

$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir
$GitHubRepo = 'kevin-qingmo/meeting-checkin'

function Say($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    [!]  $msg" -ForegroundColor Yellow }
function Die($msg)  { Write-Host "    [X]  $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  会议扫码签到系统 · 一键部署" -ForegroundColor White
Write-Host "  -------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# ---------- 1. Railway CLI ----------
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Say "未检测到 Railway CLI，正在安装（需要 Node.js）..."
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Die "没有 Node.js。请先到 https://nodejs.org 下载安装 LTS 版，然后重跑本脚本。"
    }
    npm i -g @railway/cli --registry=https://registry.npmmirror.com
    if ($LASTEXITCODE -ne 0) { Die "Railway CLI 安装失败。" }
}
Ok "Railway CLI $(railway --version)"

# ---------- 2. 登录 ----------
$null = railway whoami 2>&1
if ($LASTEXITCODE -ne 0) {
    Say "需要登录 Railway。接下来会弹出 Edge，请在页面里点 GitHub 的 Authorize（只需这一次）。"
    Write-Host ""
    Write-Host "    若浏览器没自动弹出、或 GitHub 按钮点不动，" -ForegroundColor DarkGray
    Write-Host "    请手动打开 https://railway.com/activate ，输入命令行显示的验证码。" -ForegroundColor DarkGray
    Write-Host ""
    railway login
    if ($LASTEXITCODE -ne 0) {
        Say "浏览器登录未完成，改用设备码方式，请按提示在浏览器输入验证码..."
        railway login --browserless
    }
    $null = railway whoami 2>&1
    if ($LASTEXITCODE -ne 0) { Die "登录失败，请重跑本脚本。" }
}
Ok "已登录：$(railway whoami 2>&1)"

# ---------- 3. 管理员密码 ----------
$secure = Read-Host "请为管理员 admin 设置登录密码（至少 6 位，直接回车则自动生成）" -AsSecureString
$AdminPassword = [System.Net.NetworkCredential]::new("", $secure).Password
if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
    $AdminPassword = "nk" + (Get-Random -Minimum 100000 -Maximum 999999)
    Write-Host "    自动生成的密码：$AdminPassword" -ForegroundColor Yellow
}
if ($AdminPassword.Length -lt 6) { Die "密码至少 6 位。" }

# ---------- 4. 项目 ----------
$null = railway status --json 2>&1
if ($LASTEXITCODE -ne 0) {
    Say "创建 Railway 项目 meeting-checkin ..."
    railway init --name meeting-checkin
    if ($LASTEXITCODE -ne 0) { Die "创建项目失败。" }
}
Ok "项目就绪"

# ---------- 5. Postgres（必须在首次构建前挂上，否则首启会因缺 DATABASE_URL 失败） ----------
$varsRaw = railway variables list --json 2>$null | Out-String
if ($varsRaw -notmatch '"name"\s*:\s*"DATABASE_URL"') {
    Say "添加 PostgreSQL 数据库插件..."
    railway add --database postgres
    if ($LASTEXITCODE -ne 0) { Warn "添加数据库失败；若已存在可忽略。" }
    Start-Sleep -Seconds 5
}
Ok "数据库就绪（DATABASE_URL 由插件自动注入）"

# ---------- 6. 环境变量 ----------
$SecretKey = -join ((1..64) | ForEach-Object { "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"[(Get-Random -Maximum 62)] })
Say "写入 SECRET_KEY / ADMIN_PASSWORD ..."
railway variables set "SECRET_KEY=$SecretKey" "ADMIN_PASSWORD=$AdminPassword" --skip-deploys | Out-Null
if ($LASTEXITCODE -ne 0) { Die "环境变量写入失败。" }
Ok "变量已写入"

# ---------- 7. 上传代码并构建 ----------
Say "上传代码并构建（首次约 2-4 分钟）..."
railway up --detach --yes
if ($LASTEXITCODE -ne 0) { Die "上传失败。" }
Start-Sleep -Seconds 5

# ---------- 8. 关联 GitHub 仓库，实现 push 自动部署 ----------
$svcRaw = railway service list --json 2>$null | Out-String
$svcName = $null
if ($svcRaw -match '"name"\s*:\s*"([^"]+)"') { $svcName = $matches[1] }
if ($svcName) {
    Say "关联 GitHub 仓库 $GitHubRepo （以后 git push 即自动部署）..."
    railway service source connect --repo $GitHubRepo --branch main --service $svcName | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "已关联 GitHub 自动部署" }
    else { Warn "自动部署关联失败，不影响本次上线；可稍后在控制台手动关联。" }
} else {
    Warn "未能读到服务名，跳过 GitHub 自动部署关联。"
}

# ---------- 9. 生成域名 ----------
Say "生成公网域名 ..."
$domainName = $null
$domainRaw = railway domain --json 2>$null | Out-String
if ($domainRaw -match '"domain"\s*:\s*"([^"]+)"') { $domainName = $matches[1] }
if (-not $domainName) {
    $raw = railway domain 2>&1 | Out-String
    if ($raw -match 'https://([a-zA-Z0-9\-\.]+\.up\.railway\.app)') { $domainName = $matches[1] }
}
if (-not $domainName) { Die "没能取得域名，请到 Railway 控制台查看后在 Variables 手动填 BASE_URL。" }
$BaseUrl = "https://$domainName"
Ok "域名：$BaseUrl"

Say "回填 BASE_URL 并触发重新部署 ..."
railway variables set "BASE_URL=$BaseUrl" | Out-Null
if ($LASTEXITCODE -ne 0) { Warn "BASE_URL 回填失败，请稍后在控制台手动设置。" }

# ---------- 10. 等待就绪 ----------
Say "等待服务启动（最多 3 分钟）..."
$ready = $false
for ($i = 0; $i -lt 36; $i++) {
    Start-Sleep -Seconds 5
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl/api/health" -UseBasicParsing -TimeoutSec 8
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}
if ($ready) { Ok "健康检查通过" } else { Warn "健康检查未通过，请到 Railway 控制台查看 Logs。" }

# ---------- 完成 ----------
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  部署完成" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host "  网址   ： $BaseUrl"
Write-Host "  用户名 ： admin"
Write-Host "  密码   ： $AdminPassword"
Write-Host ""
Write-Host "  登录后请立刻："
Write-Host "   1) 「账号管理」里修改 admin 密码"
Write-Host "   2) 给其他教务老师各建一个账号（他们只能管自己的活动）"
Write-Host "   3) 「新建活动」-> 导入名册 -> 打开签到大屏 -> 投影到会场"
Write-Host ""
Write-Host "  以后改了代码：git push，Railway 会自动重新部署"
Write-Host "================================================" -ForegroundColor Green
