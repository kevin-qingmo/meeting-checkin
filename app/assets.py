"""首屏资源内联。

背景：服务器部署在境外节点，国内访问时链路丢包严重（实测 83%），
一次 TCP+TLS 握手可能耗时 15~60 秒。浏览器首屏若要并行拉取
CSS / JS / 校徽图片等多个静态资源，每个都要单独握手，
弱网下就会表现为「打开网页一直转圈、加载不出内容」。

对策：把首屏用到的 CSS / JS / 校徽直接内联进 HTML，
让整页只依赖 1 个请求（HTML 本身），并配合 gzip 压缩传输。
文件内容在进程内缓存，读取开销可忽略。
"""
import base64
import os

from flask import current_app
from markupsafe import Markup

_cache = {}

LOGO_REL = "img_school_logo.png"


def _static_path(rel):
    folder = current_app.static_folder or os.path.join(current_app.root_path, "static")
    return os.path.join(folder, rel)


def _read_text(rel):
    key = ("text", rel)
    if key not in _cache:
        path = _static_path(rel)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as fh:
            _cache[key] = fh.read()
    return _cache[key]


def inline_css(rel):
    """把 CSS 文件内容内联（模板里放进 <style>）。

    必须返回 Markup：Jinja 默认对 .html 模板做 HTML 转义，
    直接输出会把 CSS/JS 里的 > < & 改写掉，脚本会直接失效。
    """
    return Markup(_read_text(rel))


def inline_js(rel):
    """把 JS 文件内容内联（模板里放进 <script>）。"""
    return Markup(_read_text(rel))


def logo_data_uri():
    """校徽图片转成 data URI，省掉一次图片请求。"""
    key = ("logo", LOGO_REL)
    if key not in _cache:
        path = _static_path(LOGO_REL)
        uri = ""
        if os.path.exists(path):
            with open(path, "rb") as fh:
                raw = fh.read()
            uri = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        _cache[key] = uri
    return Markup(_cache[key])
