"""公网实例端到端验收：登录 → 建活动 → 出码 → 扫码签到 → 实时统计 → 导出 Excel
                  → 切换模式换码 → 跨模式码被拒 → 删除活动（级联清理）。

用法: python tools/e2e_public.py <BASE_URL> <USERNAME> <PASSWORD>
"""
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000").rstrip("/")
USER = sys.argv[2] if len(sys.argv) > 2 else "admin"
PWD = sys.argv[3] if len(sys.argv) > 3 else "admin123456"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

FAIL = []


def check(label, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print("[{}] {} {}".format(mark, label, detail))
    if not cond:
        FAIL.append(label)


def req(path, data=None, headers=None, raw=False):
    url = path if path.startswith("http") else BASE + path
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    r = urllib.request.Request(url, data=body)
    r.add_header("User-Agent", "Mozilla/5.0 e2e")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    with opener.open(r, timeout=30) as resp:
        content = resp.read()
        if raw:
            return resp.status, content, dict(resp.headers)
        return resp.status, content.decode("utf-8", "replace"), dict(resp.headers)


def req_status(path, data=None, headers=None):
    """不跟随重定向，返回原始状态码（用于 404 断言）。"""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)
    url = path if path.startswith("http") else BASE + path
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    r = urllib.request.Request(url, data=body)
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with op.open(r, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


# 1. 登录
status, body, _ = req("/login", {"username": USER, "password": PWD})
check("登录成功", "用户名或密码错误" not in body, "HTTP {}".format(status))

# 2. 创建活动
now = datetime.now()
title = "上线验收测试 " + now.strftime("%m%d-%H%M%S")
data = {
    "title": title,
    "start_at": (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M"),
    "end_at": (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
    "campus_ids": ["c3"],
    "stage_ids": ["s1"],
    "subject_ids": ["j1"],
    "location": "线上验收",
    "need_checkout": "on",
}
status, body, headers = req("/admin/activity/new", data)
check("创建活动", status == 200, "HTTP {}".format(status))
m = re.search(r"/admin/activity/(\d+)/dashboard", str(headers.get("Location", "")))
if not m:
    m = re.search(r"/admin/activity/(\d+)/dashboard", body)
if not m:
    m = re.search(r"/(?:admin/activity|board)/(\d+)", body)
aid = m.group(1) if m else None
check("拿到活动 ID", bool(aid), str(aid))
if not aid:
    print(body[:1500])
    sys.exit(1)

# 3. 大屏取码（签到模式）
status, body, _ = req("/api/board/{}/qr".format(aid))
check("大屏出码", status == 200)
qr = json.loads(body)
token, cycle, site = qr.get("token"), qr.get("cycle"), qr.get("site_code")
check("码字段齐全", bool(token and cycle and site), "cycle={} site={}".format(cycle, site))

# 4. 扫码签到
status, body, _ = req(
    "/api/scan/{}".format(aid),
    {"name": "验收老师", "phone": "13800000000", "campus": "和慧南路校区",
     "site_code": site, "token": token, "cycle": cycle, "mode": "in"},
    headers={"X-Requested-With": "XMLHttpRequest"},
)
res = json.loads(body) if body.strip().startswith("{") else {"raw": body[:200]}
check("扫码签到成功", res.get("ok") is True, str(res.get("message") or res))

# 5. 错码被拒
status, body, _ = req(
    "/api/scan/{}".format(aid),
    {"name": "验收老师", "phone": "13800000000", "campus": "和慧南路校区",
     "site_code": "0000", "token": token, "cycle": cycle, "mode": "in"},
    headers={"X-Requested-With": "XMLHttpRequest"},
)
res2 = json.loads(body) if body.strip().startswith("{") else {"raw": body[:200]}
check("错误现场码被拒", res2.get("ok") is not True, str(res2.get("message") or res2))

# 6. 实时看板统计
status, body, _ = req("/api/activity/{}/live".format(aid))
live = json.loads(body)
cnt = live.get("checked_in", live.get("checked_in_count"))
check("实时统计读到 1 条签到", str(cnt) == "1",
      "live={}".format(json.dumps(live, ensure_ascii=False)[:200]))

# 7. 导出 Excel
status, content, headers = req("/admin/activity/{}/export".format(aid), raw=True)
check("导出 Excel", status == 200 and content[:2] == b"PK",
      "HTTP {} bytes={}".format(status, len(content)))

# 8. 切换签到/签离模式 → 必须换新码
d_in = json.loads(req("/api/board/{}/qr?mode=in".format(aid))[1])
d_out = json.loads(req("/api/board/{}/qr?mode=out".format(aid))[1])
check("切模式后 token 变化", d_in["token"] != d_out["token"])
check("切模式后现场码变化", d_in["site_code"] != d_out["site_code"])
check("切模式后二维码指向 out", d_out["qr_url"].endswith("m=out")
      and d_out["qr_png"].endswith("mode=out"))

# 9. 签离码不能拿去签到
status, body, _ = req(
    "/api/scan/{}".format(aid),
    {"name": "验收老师2", "phone": "13800000001", "campus": "和慧南路校区",
     "site_code": d_out["site_code"], "token": d_out["token"],
     "cycle": d_out["cycle"], "mode": "in"},
    headers={"X-Requested-With": "XMLHttpRequest"},
)
res3 = json.loads(body) if body.strip().startswith("{") else {"raw": body[:200]}
check("跨模式码被拒", res3.get("ok") is not True, str(res3.get("message") or res3))

# 10. 删除活动 → 级联清理 + 页面 404
status, body, _ = req("/admin/activity/{}/delete".format(aid), data={})
check("删除活动", "已删除活动" in body, "HTTP {}".format(status))
listing = req("/admin/")[1]
check("活动列表已无该活动", title not in listing)
check("删除后大屏 404", req_status("/board/{}".format(aid)) == 404)
check("删除后扫码页 404", req_status("/scan/{}".format(aid)) == 404)
check("删除后实时接口 404", req_status("/api/activity/{}/live".format(aid)) == 404)

print("\n结果: {} 项失败 -> {}".format(len(FAIL), FAIL) if FAIL else "\n结果: 全部通过")
sys.exit(1 if FAIL else 0)
