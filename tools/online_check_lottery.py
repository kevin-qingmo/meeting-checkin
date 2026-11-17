"""线上验收：随机抽签（后台抽取 / 公开接口脱敏 / 大屏 / Excel 第 4 表 / 清理）。

用法（Windows PowerShell）：
  $env:ONLINE_BASE='https://web-production-9fe1faa8.up.railway.app'
  $env:ADMIN_PW='<admin 密码>'
  & '.\.venv\Scripts\python.exe' tools\online_check_lottery.py

HTTP 走系统 curl.exe（本机 python TLS 握手不稳定），Excel 用 openpyxl 解析。
脚本只创建「临时活动」，退出前一定尝试删除；口令只从环境变量读取，不落盘、不打印。
"""
import io
import json
import os
import subprocess
import sys
import tempfile

BASE = os.environ.get("ONLINE_BASE", "https://web-production-9fe1faa8.up.railway.app").rstrip("/")
PASSWORD = os.environ.get("ADMIN_PW", "")
USERNAME = os.environ.get("ADMIN_USER", "admin")
CURL = os.environ.get("CURL_EXE", "curl.exe")

RESULTS = []
TMP = tempfile.mkdtemp(prefix="mcode_online_")


def ok(cond, msg):
    RESULTS.append((bool(cond), msg))
    print(("  PASS  " if cond else "! FAIL  ") + msg)


def curl(url, method="GET", data=None, jar=None, ajax=False):
    """返回 (status:int, final_url:str, body:str)。"""
    body_file = os.path.join(TMP, "body_%d.txt" % len(RESULTS))
    meta_file = body_file + ".meta"
    cmd = [CURL, "-s", "-m", "90", "--retry", "3", "--retry-delay", "2", "--retry-all-errors",
           "-L", "-o", body_file, "-w", "%{http_code} %{url_effective}"]
    if jar:
        cmd += ["-c", jar, "-b", jar]
    if ajax:
        cmd += ["-H", "X-Requested-With: XMLHttpRequest"]
    if method == "POST":
        # 不用 -X POST：配合 -L 时 curl 会在 302 后自动转成 GET，符合 Flask 的重定向语义
        cmd += ["--data", data if data is not None else ""]
    cmd.append(url)
    with open(meta_file, "w", encoding="utf-8") as f:
        pass
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    meta = proc.stdout.strip()
    status, _, final_url = meta.partition(" ")
    try:
        status_i = int(status)
    except ValueError:
        status_i = 0
        if proc.stderr.strip():
            print("    [curl] %s" % proc.stderr.strip()[:200])
    body = ""
    if os.path.exists(body_file):
        with open(body_file, "r", encoding="utf-8", errors="replace") as f:
            body = f.read()
    return status_i, final_url, body


def form(pairs):
    import urllib.parse
    return urllib.parse.urlencode(pairs)


def jcurl(url, method="GET", data=None, jar=None):
    status, final_url, body = curl(url, method=method, data=data, jar=jar, ajax=True)
    try:
        return status, json.loads(body)
    except ValueError:
        return status, {"_raw": body[:300]}


def main():
    if not PASSWORD:
        print("缺少环境变量 ADMIN_PW")
        return 2
    jar = os.path.join(TMP, "cookies.txt")

    print("== 1. 登录 ==")
    status, url, body = curl(BASE + "/login", "POST",
                              form({"username": USERNAME, "password": PASSWORD}), jar=jar)
    logged_in = "/login" not in url
    ok(logged_in, "登录成功（最终地址 %s，HTTP %s）" % (url, status))
    if not logged_in:
        print("登录失败，终止（线上 admin 密码可能已被改过）")
        return 1

    print("== 2. 创建临时活动 ==")
    status, url, body = curl(BASE + "/admin/activity/new", "POST", form({
        "title": "线上验收-随机抽签",
        "start_at": "2026-11-17 21:00:00",
        "end_at": "2026-11-17 23:00:00",
        "location": "线上验收",
        "school_wide": "on",
    }), jar=jar)
    aid = None
    if "/admin/activity/" in url:
        import re
        m = re.search(r"/admin/activity/(\d+)", url)
        if m:
            aid = m.group(1)
    ok(aid is not None, "临时活动已创建 activity_id=%s（HTTP %s）" % (aid, status))
    if not aid:
        print(body[:400])
        return 1

    try:
        print("== 3. 补录 3 人签到 ==")
        for name, phone, campus in [
            ("验收甲", "13900009001", "和慧南路校区"),
            ("验收乙", "13900009002", "雅馨路校区"),
            ("验收丙", "13900009003", "敬慧路校区"),
        ]:
            st, d = jcurl(BASE + "/api/activity/%s/manual" % aid, "POST",
                          form({"name": name, "phone": phone, "campus": campus}), jar=jar)
            ok(st == 200 and d.get("ok") is True, "补录 %s（HTTP %s）" % (name, st))

        print("== 4. 后台抽签 ==")
        st, d = jcurl(BASE + "/admin/activity/%s/lottery" % aid, "POST",
                      form({"count": "1", "exclude_winners": "on"}), jar=jar)
        ok(st == 200 and d.get("ok") is True,
           "抽签成功（HTTP %s）message=%s" % (st, d.get("message")))
        round_data = d.get("round") or {}
        winners = round_data.get("winners") or []
        ok(len(winners) == 1, "抽出 1 人：%s" % [w.get("name") for w in winners])
        ok(round_data.get("draw_count") == 1,
           "draw_count 记录实际抽中人数 = %s" % round_data.get("draw_count"))
        ok(round_data.get("excluded") is True, "本轮标记为「排除已中奖」")

        print("== 5. 公开只读接口（未登录） ==")
        st, url, raw = curl(BASE + "/api/activity/%s/lottery" % aid)
        ok(st == 200, "匿名访问公开接口 HTTP %s" % st)
        try:
            pub = json.loads(raw)
        except ValueError:
            pub = {}
        ok(pub.get("ok") is True, "公开接口 ok=true")
        latest = pub.get("latest") or {}
        ok(bool(latest.get("winners")), "公开接口返回最新一轮中奖名单")
        ok('"phone"' not in raw, "公开响应不含 phone 字段")
        ok(all(p not in raw for p in ("13900009001", "13900009002", "13900009003")),
           "公开响应不含任何手机号字面量")
        ok([w.get("name") for w in (latest.get("winners") or [])] == [w.get("name") for w in winners],
           "公开名单与后台一致")

        print("== 6. 大屏页面 ==")
        st, url, body = curl(BASE + "/board/%s" % aid, jar=jar)
        ok(st == 200, "大屏 HTTP %s" % st)
        ok('id="winner-list"' in body, "大屏含 winner-list 容器")
        ok('id="winner-empty"' in body, "大屏含 winner-empty 容器")

        print("== 7. Excel 导出 ==")
        xlsx = os.path.join(TMP, "export.xlsx")
        cmd = [CURL, "-s", "-m", "60", "-L", "-c", jar, "-b", jar, "-o", xlsx,
               "-w", "%{http_code}", BASE + "/admin/activity/%s/export" % aid]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        status = int(proc.stdout.strip() or 0)
        ok(status == 200, "导出 HTTP %s" % status)
        try:
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(open(xlsx, "rb").read()))
            ok(wb.sheetnames == ["签到明细", "应到实到统计", "缺席名单", "抽奖记录"],
               "工作簿四张表：%s" % wb.sheetnames)
            ws = wb["抽奖记录"]
            ok(ws.max_row == 2, "抽奖记录有 1 行数据（表头 + 1 行），max_row=%s" % ws.max_row)
            ok([c.value for c in ws[1]] == ["轮次", "抽取时间", "抽取人数", "中奖名单", "操作人", "排除已中奖者"],
               "抽奖记录表头正确")
            if ws.max_row >= 2:
                ok(ws.cell(2, 3).value == 1, "抽取人数列 = %s" % ws.cell(2, 3).value)
                ok((ws.cell(2, 4).value or "") == winners[0].get("name"),
                   "中奖名单列 = %s" % ws.cell(2, 4).value)
        except Exception as e:  # noqa: BLE001
            ok(False, "解析导出失败：%r" % e)

        print("== 8. 排除已中奖：再抽一轮 ==")
        st, d2 = jcurl(BASE + "/admin/activity/%s/lottery" % aid, "POST",
                       form({"count": "1", "exclude_winners": "on"}), jar=jar)
        ok(st == 400 and d2.get("ok") is False,
           "排除已中奖生效：可抽人数耗尽时返回 400（HTTP %s）message=%s" % (st, d2.get("message")))
    finally:
        print("== 9. 清理临时活动 ==")
        st, url, body = curl(BASE + "/admin/activity/%s/delete" % aid, "POST", "", jar=jar)
        ok(st == 200 and "/admin" in url, "临时活动已删除（HTTP %s）" % st)
        st, url, body = curl(BASE + "/admin/activity/%s/dashboard" % aid, jar=jar)
        ok(st in (404, 403), "活动已不可访问（HTTP %s）" % st)

    failed = [m for c, m in RESULTS if not c]
    print("\n总计 %d 项，失败 %d 项" % (len(RESULTS), len(failed)))
    for m in failed:
        print("  FAILED: " + m)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
