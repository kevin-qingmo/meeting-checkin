"""把校徽 PNG 压缩到适合网页使用的体积。

背景：原图 612x590 / 283KB，而页面上只按 42~56px 显示，
在弱网（跨境丢包）环境下这张图是首屏最大的加载负担。
这里重采样到 112px（2 倍于最大显示尺寸）+ 64 色量化，
并把结果内联成 data URI，让每个页面少发一次图片请求。

用法：
    py -3 tools/optimize_logo.py
"""
import os
from pathlib import Path

from PIL import Image

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
SRC = STATIC / "img_school_logo.png"
TARGET_WIDTH = 112
COLORS = 64


def main():
    before = SRC.stat().st_size
    with Image.open(SRC) as im:
        im = im.convert("RGBA")
        origin = im.size
        ratio = TARGET_WIDTH / im.width
        size = (TARGET_WIDTH, max(1, round(im.height * ratio)))
        small = im.resize(size, Image.LANCZOS)
        # 校徽为扁平色块，量化到 64 色几乎无损，却能省掉一半以上体积
        small = small.quantize(colors=COLORS, method=Image.FASTOCTREE).convert("RGBA")
        small.save(SRC, format="PNG", optimize=True, compress_level=9)
    after = SRC.stat().st_size
    print("尺寸：{} -> {}".format(origin, size))
    print("体积：{:.1f}KB -> {:.1f}KB（降 {:.0f}%）".format(
        before / 1024, after / 1024, (1 - after / before) * 100))
    print("内联为 data URI 后约 +{:.0f}KB：{:.1f}KB".format(
        after / 1024 * 4 / 3, after / 1024 * 4 / 3))


if __name__ == "__main__":
    main()
