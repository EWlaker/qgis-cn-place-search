# -*- coding: utf-8 -*-
"""生成「中国地名搜索」插件图标。

设计：QGIS 绿圆角底 + 白色放大镜，镜中一枚红色地图定位针 ——
一眼同时读出「搜索」与「地点」两层含义。

产物（写回仓库根目录）：
    icon.png       64x64    metadata.txt 里 icon 指向它
    icon-128.png   128x128  README 与插件页用的大图
    icon.svg       矢量源   任意尺寸清晰，也可直接替换 metadata 的 icon

用法：
    python tools/build_icon.py

绘制统一在 4 倍超采样画布上完成，最后用 LANCZOS 缩小，
这样 64px 下边缘也不毛糙。颜色与几何参数集中在下面常量里，改一处即可。
"""
import math
import os

from PIL import Image, ImageDraw

# --------------------------------------------------------------- 设计参数
SS = 4                       # 超采样倍数
RADIUS_RATIO = 0.22          # 圆角半径 / 边长
BG_TOP = "#5FAE64"           # 底色渐变上端
BG_BOTTOM = "#2C7A45"        # 底色渐变下端
LENS_CENTER = (0.44, 0.43)   # 镜片圆心（相对边长）
LENS_RADIUS = 0.255          # 镜片半径
LENS_STROKE = 0.072          # 镜圈线宽
HANDLE_END = (0.80, 0.80)    # 手柄末端
HANDLE_WIDTH = 0.095         # 手柄线宽
PIN_SIZE = 0.072             # 定位针圆头半径
PIN_DY = -0.045              # 定位针相对镜心的纵向偏移
PIN_HOLE = 0.030             # 针孔半径
COLOR_WHITE = "#FFFFFF"
COLOR_PIN = "#E5484D"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


# ----------------------------------------------------------------- 绘制
def rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def vertical_gradient(size, top, bottom):
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        draw.line([(0, y), (size, y)],
                  fill=tuple(int(top[i] + (bottom[i] - top[i]) * t)
                             for i in range(3)))
    return img


def caps_line(draw, p0, p1, width, fill):
    """带圆头的线段（PIL 的 line 不封口）。"""
    draw.line([p0, p1], fill=fill, width=int(round(width)))
    r = width / 2.0
    for x, y in (p0, p1):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def draw_icon(px):
    """按目标像素尺寸出图。"""
    s = px * SS
    top, bottom = rgb(BG_TOP), rgb(BG_BOTTOM)

    base = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    base.paste(vertical_gradient(s, top, bottom), (0, 0),
               rounded_mask(s, s * RADIUS_RATIO))
    draw = ImageDraw.Draw(base)
    white = rgb(COLOR_WHITE) + (255,)

    lx, ly = s * LENS_CENTER[0], s * LENS_CENTER[1]
    lr = s * LENS_RADIUS

    # 手柄先画，让镜圈压在上面，接缝干净
    a = math.radians(45)
    caps_line(draw,
              (lx + math.cos(a) * lr * 0.72, ly + math.sin(a) * lr * 0.72),
              (s * HANDLE_END[0], s * HANDLE_END[1]),
              s * HANDLE_WIDTH, white)

    # 镜圈
    draw.ellipse([lx - lr, ly - lr, lx + lr, ly + lr],
                 outline=white, width=int(round(s * LENS_STROKE)))

    # 镜中定位针：圆头 + 下三角，三角两角落在圆内所以并集平滑
    px_, py_ = lx, ly + s * PIN_DY
    pr = s * PIN_SIZE
    draw.ellipse([px_ - pr, py_ - pr, px_ + pr, py_ + pr],
                 fill=rgb(COLOR_PIN) + (255,))
    draw.polygon([(px_ - pr * 0.74, py_ + pr * 0.55),
                  (px_ + pr * 0.74, py_ + pr * 0.55),
                  (px_, py_ + pr * 2.0)], fill=rgb(COLOR_PIN) + (255,))
    hr = s * PIN_HOLE
    draw.ellipse([px_ - hr, py_ - hr, px_ + hr, py_ + hr], fill=white)

    return base.resize((px, px), Image.LANCZOS)


# ----------------------------------------------------------------- 矢量
def svg_source(view=256):
    """手写矢量版：与位图同一套参数，任意尺寸都清晰。"""
    def f(v):
        return round(v * view, 2)

    lx, ly = f(LENS_CENTER[0]), f(LENS_CENTER[1])
    lr, stroke = f(LENS_RADIUS), f(LENS_STROKE)
    px_ = lx
    py_ = round(ly + PIN_DY * view, 2)
    pr, hr = f(PIN_SIZE), f(PIN_HOLE)
    a = math.radians(45)
    hx0 = round(lx + math.cos(a) * lr * 0.72, 2)
    hy0 = round(ly + math.sin(a) * lr * 0.72, 2)
    hx1, hy1 = f(HANDLE_END[0]), f(HANDLE_END[1])
    tri = "%.2f,%.2f %.2f,%.2f %.2f,%.2f" % (
        px_ - pr * 0.74, py_ + pr * 0.55,
        px_ + pr * 0.74, py_ + pr * 0.55,
        px_, py_ + pr * 2.0)
    return """<?xml version="1.0" encoding="UTF-8"?>
<!-- 中国地名搜索插件图标 —— 由 tools/build_icon.py 生成，勿手改 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {v} {v}" width="{v}" height="{v}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{bg_top}"/>
      <stop offset="1" stop-color="{bg_bottom}"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{v}" height="{v}" rx="{rx}" ry="{rx}" fill="url(#bg)"/>
  <g fill="none" stroke="{white}" stroke-linecap="round">
    <path d="M{hx0} {hy0} L{hx1} {hy1}" stroke-width="{hw}"/>
    <circle cx="{lx}" cy="{ly}" r="{lr}" stroke-width="{stroke}"/>
  </g>
  <g fill="{pin}">
    <circle cx="{px}" cy="{py}" r="{pr}"/>
    <polygon points="{tri}"/>
  </g>
  <circle cx="{px}" cy="{py}" r="{hr}" fill="{white}"/>
</svg>
""".format(v=view, rx=f(RADIUS_RATIO), bg_top=BG_TOP, bg_bottom=BG_BOTTOM,
           white=COLOR_WHITE, pin=COLOR_PIN, hx0=hx0, hy0=hy0, hx1=hx1,
           hy1=hy1, hw=f(HANDLE_WIDTH), lx=lx, ly=ly, lr=lr,
           stroke=stroke, px=px_, py=py_, pr=pr, tri=tri, hr=hr)


def main():
    jobs = [("icon.png", 64), ("icon-128.png", 128)]
    for name, px in jobs:
        path = os.path.join(ROOT, name)
        draw_icon(px).save(path)
        print("写出 %-14s %dx%d  %d 字节" % (name, px, px,
                                            os.path.getsize(path)))
    svg_path = os.path.join(ROOT, "icon.svg")
    with open(svg_path, "w", encoding="utf-8") as fh:
        fh.write(svg_source())
    print("写出 %-14s 矢量        %d 字节" % ("icon.svg",
                                             os.path.getsize(svg_path)))


if __name__ == "__main__":
    main()
