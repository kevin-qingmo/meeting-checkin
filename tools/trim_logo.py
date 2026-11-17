"""裁掉校徽 PNG 四周空白：以「紫色墨迹」为准求包围盒，导出紧凑版本。"""
import sys

from PIL import Image

src = sys.argv[1]
dst = sys.argv[2]
img = Image.open(src).convert("RGBA")
r, g, b, a = img.split()
px = list(img.getdata())
mask = Image.new("L", img.size)
mask.putdata([
    255 if (p[3] > 20 and min(p[0], p[1], p[2]) < 200) else 0
    for p in px
])
bbox = mask.getbbox()
print("原图:", img.size, "墨迹包围盒:", bbox)
if bbox:
    pad = 4
    left = max(0, bbox[0] - pad)
    top = max(0, bbox[1] - pad)
    right = min(img.width, bbox[2] + pad)
    bottom = min(img.height, bbox[3] + pad)
    out = img.crop((left, top, right, bottom))
    # 铺白底，避免透明区域在深色顶栏上变成黑块
    bg = Image.new("RGBA", out.size, (255, 255, 255, 255))
    bg.alpha_composite(out)
    bg.convert("RGB").save(dst)
    print("已输出:", dst, bg.size)
else:
    img.save(dst)
    print("未检测到墨迹，原样输出:", dst)
