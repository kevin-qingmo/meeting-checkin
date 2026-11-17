"""检查校徽 PNG 是否为动图（APNG）并导出静态帧。"""
import sys

from PIL import Image

src = sys.argv[1]
img = Image.open(src)
print("mode:", img.mode, "size:", img.size, "format:", img.format)
print("n_frames:", getattr(img, "n_frames", 1))
print("info keys:", list(img.info.keys()))
try:
    print("is_animated:", img.is_animated)
except Exception as e:
    print("err:", e)

if getattr(img, "n_frames", 1) > 1:
    for i in range(img.n_frames):
        img.seek(i)
        print("  frame", i, "size:", img.size, "bbox:", img.convert("RGBA").getbbox())
    img.seek(img.n_frames - 1)
    img.convert("RGBA").save(src.replace(".png", "_last.png"))
    print("已导出最后一帧:", src.replace(".png", "_last.png"))
else:
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    print("alpha bbox:", alpha.getbbox())
    rgb = rgba.convert("RGB")
    print("rgb bbox (非白):", rgb.point(lambda p: 255 if p < 245 else 0).getbbox())
