"""跨实例（模拟多 worker / 多进程）一致性验收。

场景：实例 A 生成签到码与现场码 → 实例 B 校验并落库 → 实例 A 读取计数。
用于证明「无状态 HMAC 派生 + 数据库共享」在多进程部署下不会串号或失效。
"""
import http.cookiejar
import json
import re
import sys
import urllib.request
import urllib.parse

A = "http://localhost:5056"
B = "http://localhost:5057"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def http(method, url, data=None, headers=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-Requested-With", "XMLHttpRequest")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with opener.open(req, timeout=15) as r:
        return r.status, r.read().decode("utf-8")


def main():
    # 1) 在实例 A 上登录（CookieJar 自动保存会话）
    _, body = http("POST", A + "/login", {"username": "admin", "password": "prodtest123456"})
    print("[1] A 登录:", "成功" if "活动管理" in body else "失败")

    # 2) 在实例 A 上建活动
    _, body = http("POST", A + "/admin/activity/new", {
        "title": "跨实例一致性测试活动",
        "campus_ids": "敬慧路校区",
        "start_at": "2026-01-01T08:00",
        "end_at": "2030-12-31T20:00",
        "location": "测试",
    })
    ids = re.findall(r"/admin/activity/(\d+)/dashboard", body)
    activity_id = int(ids[0]) if ids else None
    if not activity_id:
        _, listbody = http("GET", A + "/admin/")
        ids = re.findall(r"/admin/activity/(\d+)/dashboard", listbody)
        activity_id = int(ids[0]) if ids else None
    print("[2] A 建活动, id =", activity_id)

    # 3) A 生成签到码 + 现场码
    _, qa = http("GET", A + "/api/board/%d/qr" % activity_id)
    q = json.loads(qa)
    print("[3] A 出码: cycle=%s site_code=%s token=%s" % (q["cycle"], q["site_code"], q["token"]))

    # 4) B 校验并落库（关键：token 来自 A）
    st, sb = http("POST", B + "/api/scan/%d" % activity_id, {
        "name": "跨进程测试", "phone": "13900001111", "campus": "敬慧路校区",
        "site_code": q["site_code"], "token": q["token"], "cycle": str(q["cycle"]), "mode": "in",
    })
    print("[4] B 提交:", sb.strip())

    # 5) A 读计数
    _, la = http("GET", A + "/api/activity/%d/live" % activity_id)
    live = json.loads(la)
    print("[5] A 读计数: 已签到=%s 已签离=%s" % (live["checked_in"], live["checked_out"]))

    # 6) 错误现场码应被拒（跨实例同样生效）
    st2, sb2 = http("POST", B + "/api/scan/%d" % activity_id, {
        "name": "错误码测试", "phone": "13900002222", "campus": "敬慧路校区",
        "site_code": "0000", "token": q["token"], "cycle": str(q["cycle"]), "mode": "in",
    })
    print("[6] B 错码: ", sb2.strip())

    ok = live["checked_in"] == 1 and "签到成功" in sb and "现场码不正确" in sb2
    print("\n结果:", "通过 ✅" if ok else "未通过 ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
