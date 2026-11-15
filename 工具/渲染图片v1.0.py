#!/usr/bin/env python3
"""用无头 Chromium 把 SVG / HTML 渲染成 webp 或 png（另出一份 -sm 缩略图）。

用法：
  python3 工具/渲染图片v1.0.py 图片/拓扑图/a.svg 图片/拓扑图/a-v1.0.webp
  python3 工具/渲染图片v1.0.py index.html 文档/截图/桌面截图v1.0.png --width 1440 --full
需要：pip install playwright pillow && python3 -m playwright install chromium
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


def shoot(src: Path, out: Path, width: int | None, height: int, scale: float, full: bool, sm: bool, wait: int, anchor: str | None = None) -> None:
    src = src.resolve()
    with sync_playwright() as p:
        b = p.chromium.launch()
        if src.suffix == ".svg":
            svg = src.read_text(encoding="utf-8")
            import re
            m = re.search(r'width="(\d+)" height="(\d+)"', svg)
            w, h = int(m.group(1)), int(m.group(2))
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
            pg.set_content(f'<html><body style="margin:0;background:#0b1118">{svg}</body></html>')
            pg.wait_for_timeout(300)
            png = pg.screenshot(clip={"x": 0, "y": 0, "width": w, "height": h})
        else:
            pg = b.new_page(viewport={"width": width or 1440, "height": height}, device_scale_factor=scale)
            pg.goto(src.as_uri())
            pg.wait_for_timeout(wait)
            if anchor:
                pg.evaluate("a => { document.documentElement.style.scrollBehavior = 'auto'; const e = document.querySelector(a); window.scrollTo(0, e.getBoundingClientRect().top + window.scrollY - 58); }", anchor)
                pg.wait_for_timeout(300)
            png = pg.screenshot(full_page=full)
        b.close()
    im = Image.open(io.BytesIO(png)).convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    kw = {"quality": 90, "method": 6} if out.suffix == ".webp" else ({"quality": 90} if out.suffix in (".jpg", ".jpeg") else {"optimize": True})
    im.save(out, **kw)
    if sm:
        t = im.copy()
        t.thumbnail((900, 900))
        t.save(out.with_name(out.stem + "-sm" + out.suffix), **kw)
    print(out, im.size)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--scale", type=float, default=2)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--sm", action="store_true", help="另出 -sm 缩略图")
    ap.add_argument("--wait", type=int, default=600)
    ap.add_argument("--anchor", help="先滚动到这个 CSS 选择器，如 #lab")
    a = ap.parse_args()
    shoot(a.src, a.out, a.width, a.height, a.scale, a.full, a.sm, a.wait, a.anchor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
