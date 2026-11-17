"""弱网优化回归测试。

背景：服务器部署在境外节点，国内访问链路丢包严重（实测 83%），
一次 TCP+TLS 握手可能耗时 15~60 秒。这些测试锁住三件事：
  1. 首屏只发 1 个请求（CSS / JS / 校徽全部内联进 HTML）；
  2. 响应走 gzip、静态资源走长缓存；
  3. 轮询请求有超时与在途防抖（弱网下不会把连接池打满），
     且签到码容忍窗足以覆盖大屏刷新滞后。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import engine_options  # noqa: E402
from app.codes import current_cycle, make_site_code, make_token  # noqa: E402


# ---------- 1. 首屏资源内联 ----------


def test_login_page_has_no_external_stylesheet(app):
    """登录页不再外链 CSS：弱网下少一次握手。"""
    client = app.test_client()
    html = client.get("/login").get_data(as_text=True)
    assert "/static/css/app.css" not in html
    assert "<style>" in html


def test_login_page_inlines_logo_as_data_uri(app):
    """校徽内联为 data URI，不再单独发图片请求。"""
    client = app.test_client()
    html = client.get("/login").get_data(as_text=True)
    assert "img_school_logo.png" not in html
    assert "data:image/png;base64," in html


def test_board_page_inlines_css_and_js(app):
    """大屏页内联 board.css 与 board.js，页面只依赖 HTML 一个请求。"""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
    html = client.get("/board/1").get_data(as_text=True)
    assert "/static/css/board.css" not in html
    assert "/static/js/board.js" not in html
    assert "winner-marquee" in html          # board.js 内容确实内联进来了
    assert "AbortController" in html         # 弱网超时逻辑已内联


def test_inlined_assets_are_not_html_escaped(app):
    """内联的 CSS/JS 不能被 Jinja 的 HTML 转义改写，否则脚本会直接失效。

    判据用 JS 源码里的转义正则片段：被 HTML 转义后会变成 /[&amp;&lt;&gt;...]/g。
    """
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
    html = client.get("/board/1").get_data(as_text=True)
    assert "replace(/[&<>\"]/g" in html
    assert "replace(/[&amp;" not in html
    assert "=&gt;" not in html      # JS 的箭头函数没被转义


def test_repeated_requests_stay_ok(app):
    """第二次及以后走缓存命中路径，不能报错（回归：曾出现 UnboundLocalError）。"""
    client = app.test_client()
    for _ in range(3):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "data:image/png;base64," in resp.get_data(as_text=True)


def test_scan_page_has_no_external_stylesheet(app):
    client = app.test_client()
    html = client.get("/scan/1").get_data(as_text=True)
    assert "/static/css/app.css" not in html


# ---------- 2. 传输层优化 ----------


def test_html_response_is_gzipped(app):
    """浏览器带 Accept-Encoding: gzip 时，HTML 应被压缩。"""
    client = app.test_client()
    resp = client.get("/login", headers={"Accept-Encoding": "gzip"})
    assert resp.headers.get("Content-Encoding") == "gzip"
    assert "Accept-Encoding" in resp.headers.get("Vary", "")
    # 内容仍然可正确解码
    body = resp.get_data()
    assert b"\x1f\x8b" == body[:2]


def test_response_without_accept_encoding_not_gzipped(app):
    client = app.test_client()
    resp = client.get("/login", headers={"Accept-Encoding": "identity"})
    assert resp.headers.get("Content-Encoding") is None


def test_static_file_has_long_cache(app):
    """静态资源走浏览器长缓存，二次打开不再重新握手。"""
    client = app.test_client()
    resp = client.get("/static/css/app.css")
    assert "max-age" in resp.headers.get("Cache-Control", "")


def test_engine_options_enable_pre_ping_for_postgres():
    """数据库连接启用探活，避免连接被静默断开后卡到超时。"""
    opts = engine_options("postgresql://u:p@host/db")
    assert opts.get("pool_pre_ping") is True
    assert opts.get("pool_recycle") == 300
    assert opts.get("connect_args", {}).get("connect_timeout") == 15


def test_engine_options_empty_for_sqlite():
    assert engine_options("sqlite://") == {}
    assert engine_options("") == {}


# ---------- 3. 签到码容忍窗 ----------


def test_verify_accepts_two_cycles_old_code(app):
    """弱网下大屏刷新滞后 2 个周期（约 40 秒）时，老师扫旧码仍应通过。"""
    from app.codes import verify

    with app.app_context():
        cur = current_cycle()
        old_cycle = cur - 2
        token = make_token(1, old_cycle)
        code = make_site_code(1, old_cycle)
        ok, why = verify(1, token, code, old_cycle)
        assert ok, why


def test_verify_rejects_code_beyond_grace(app):
    """超出容忍窗的码仍然拒绝，避免无限延长有效期。"""
    from app.codes import verify

    with app.app_context():
        cur = current_cycle()
        old_cycle = cur - 5
        token = make_token(1, old_cycle)
        code = make_site_code(1, old_cycle)
        ok, why = verify(1, token, code, old_cycle)
        assert not ok
        assert "已刷新" in why


def test_verify_rejects_wrong_site_code(app):
    from app.codes import verify

    with app.app_context():
        cur = current_cycle()
        token = make_token(1, cur)
        ok, why = verify(1, token, "0000" if make_site_code(1, cur) != "0000" else "1111", cur)
        assert not ok
        assert "现场码" in why


# ---------- 4. 前端弱网逻辑（静态断言） ----------


def test_board_js_has_timeout_and_backoff(app):
    """大屏脚本必须带请求超时与退避逻辑。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "app", "static", "js", "board.js")
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert "AbortController" in src
    assert "FETCH_TIMEOUT" in src
    assert "backoff" in src
    # 旧的固定频率 setInterval 轮询已换成自调度退避
    assert "setInterval(loadLive" not in src
