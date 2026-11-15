#!/usr/bin/env python3
"""把 graph.json 画成分层拓扑 SVG，并标出 diagnose 找到的问题节点。

用法：python3 工具/绘制拓扑图v1.0.py 示例/xxx.json 图片/拓扑图/xxx.svg [--today 2026-11-15] [--title 标题]
零依赖；SVG 可直接嵌进网页，也可用 工具/渲染图片v1.0.py 转成 webp。
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("geaplus", ROOT / "工具" / "graph-engineering-architect-plus" / "scripts" / "geaplus-v1.1.py")
gea = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gea)

KIND = {  # 颜色, 中文名
    "human_gate": ("#f5b84a", "人工门"),
    "anchor": ("#43c59e", "现实锚点"),
    "execution_loop": ("#5b9cff", "执行回路"),
    "execution": ("#5b9cff", "执行"),
    "synthesis": ("#7aa7ff", "综合"),
    "reducer": ("#7aa7ff", "汇总"),
    "verification_loop": ("#b98cff", "验证回路"),
    "counter_metric_loop": ("#ff8fb1", "反指标"),
    "audit_loop": ("#ff9f6b", "审计回路"),
    "arbitration": ("#e7d36f", "仲裁"),
    "governance_loop": ("#9fd36f", "治理回路"),
    "stop_handoff": ("#8b98a9", "收束交接"),
}
FEEDBACK = {"observes", "revises", "verifies"}
REL_ZH = {"feeds": "输入", "observes": "观察", "verifies": "核验", "constrains": "约束", "vetoes": "否决",
          "escalates": "升级", "arbitrates": "仲裁", "revises": "修订", "anchors": "锚定", "hands_off": "交接"}
AUTH = {"constrains", "vetoes", "escalates", "arbitrates"}



def layers(nodes: list[str], edges: list[dict]) -> dict[str, int]:
    fwd = [(e["from"], e["to"]) for e in edges if e.get("relation") not in FEEDBACK and e["from"] != e["to"]]
    lv = {n: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for a, b in fwd:
            if a in lv and b in lv and lv[b] < lv[a] + 1 and lv[a] + 1 < len(nodes):
                lv[b] = lv[a] + 1
                changed = True
        if not changed:
            break
    return lv


def flagged(spec: dict, today: dt.date) -> tuple[set[str], dict]:
    d = gea.diagnose(spec, today, None)
    ids = {n["id"] for n in spec.get("nodes", []) if isinstance(n, dict)}
    hit: set[str] = set()
    for p in d["patterns"]:
        for i in ids:
            if i in p["evidence"]:
                hit.add(i)
    return hit, d


def _bez(p0, p1, p2, p3, s=0.5):
    u = 1 - s
    return (u**3 * p0[0] + 3 * u * u * s * p1[0] + 3 * u * s * s * p2[0] + s**3 * p3[0],
            u**3 * p0[1] + 3 * u * u * s * p1[1] + 3 * u * s * s * p2[1] + s**3 * p3[1])


def render(spec: dict, today: dt.date, title: str | None = None) -> str:
    NW, NH, GX, GY = 250, 84, 70, 58
    nodes = [n for n in spec["nodes"] if isinstance(n, dict)]
    ids = [n["id"] for n in nodes]
    byid = {n["id"]: n for n in nodes}
    edges = [e for e in spec["edges"] if e.get("from") in ids and e.get("to") in ids]
    lv = layers(ids, edges)
    rows: dict[int, list[str]] = {}
    for i in ids:
        rows.setdefault(lv[i], []).append(i)
    px: dict[str, float] = {}
    for r in sorted(rows):
        if r > 0:
            def bary(n: str) -> float:
                ps = [px[e["from"]] for e in edges if e["to"] == n and e["from"] in px]
                return sum(ps) / len(ps) if ps else 0
            rows[r].sort(key=bary)
        k = len(rows[r])
        for j, n in enumerate(rows[r]):
            px[n] = j - (k - 1) / 2
    maxcols = max(len(v) for v in rows.values())
    head = 96 if title else 30
    side = 150
    W = max(900, side * 2 + maxcols * NW + (maxcols - 1) * GX)
    H = head + len(rows) * NH + (len(rows) - 1) * GY + 110
    cx = W / 2
    xy = {n: (cx + px[n] * (NW + GX) - NW / 2, head + lv[n] * (NH + GY)) for n in ids}
    bad, diag = flagged(spec, today)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" '
           f'font-family="Noto Sans SC, PingFang SC, Microsoft YaHei, sans-serif">',
           '<defs>'
           '<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#7f8ea3"/></marker>'
           '<marker id="arA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#f5b84a"/></marker>'
           '<marker id="arF" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#b98cff"/></marker>'
           '<filter id="gl" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
           '</defs>',
           '<rect width="100%" height="100%" fill="#0b1118"/>']
    if title:
        st = {"healthy": ("#43c59e", "diagnose：健康"), "at_risk": ("#f5b84a", "diagnose：有风险"), "blocked": ("#ff6b6b", "diagnose：阻断")}[diag["status"]]
        out.append(f'<text x="40" y="52" fill="#e8eef6" font-size="25" font-weight="700">{html.escape(title)}</text>')
        out.append(f'<rect x="40" y="66" width="190" height="28" rx="14" fill="none" stroke="{st[0]}" stroke-width="1.5"/>'
                   f'<text x="135" y="85" fill="{st[0]}" font-size="14" text-anchor="middle" font-weight="700">{st[1]}</text>')
    labels, side_used = [], {}
    for e in edges:
        a, b = e["from"], e["to"]
        (x1, y1), (x2, y2) = xy[a], xy[b]
        rel = e.get("relation", "")
        color, mk, dash = ("#f5b84a", "arA", "") if rel in AUTH else (("#b98cff", "arF", ' stroke-dasharray="6 5"') if rel in FEEDBACK else ("#7f8ea3", "ar", ""))
        span = lv[b] - lv[a]
        if span == 1:
            p0, p3 = (x1 + NW / 2, y1 + NH), (x2 + NW / 2, y2 - 3)
            p1, p2 = (p0[0], p0[1] + GY * 0.6), (p3[0], p3[1] - GY * 0.6)
        else:
            # 跨层或回边：从节点侧面绕行，避免压住中间节点
            right = (px[a] + px[b]) >= 0 if abs(px[a] - px[b]) < 0.6 else px[b] > px[a]
            key = "r" if right else "l"
            side_used[key] = side_used.get(key, 0) + 1
            off = 40 + 26 * side_used[key]
            sx = x1 + NW if right else x1
            tx = x2 + NW if right else x2
            p0, p3 = (sx, y1 + NH * (0.62 if span > 0 else 0.38)), (tx + (3 if right else -3), y2 + NH * (0.38 if span > 0 else 0.62))
            lo, hi = sorted((lv[a], lv[b]))
            between = [xy[m][0] for m in ids if lo < lv[m] < hi]
            if right:
                lane = max([x1 + NW, x2 + NW] + [bx + NW for bx in between]) + off
            else:
                lane = min([x1, x2] + between) - off
            p1 = (lane, p0[1] + (NH * 0.3 if span > 0 else -NH * 0.3))
            p2 = (lane, p3[1] - (NH * 0.3 if span > 0 else -NH * 0.3))
        d = f"M{p0[0]:.1f},{p0[1]:.1f} C{p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f} {p3[0]:.1f},{p3[1]:.1f}"
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{2.3 if rel in AUTH else 1.6}" marker-end="url(#{mk})"{dash} opacity="0.92"/>')
        labels.append((*_bez(p0, p1, p2, p3), REL_ZH.get(rel, rel), color))
    for i in ids:
        n = byid[i]
        x, y = xy[i]
        col, zh = KIND.get(n.get("kind"), ("#8b98a9", n.get("kind", "?")))
        if i in bad:
            out.append(f'<rect x="{x - 5}" y="{y - 5}" width="{NW + 10}" height="{NH + 10}" rx="16" fill="none" stroke="#ff6b6b" stroke-width="2.5" filter="url(#gl)"/>')
        out.append(f'<rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="12" fill="#121b26" stroke="{col}" stroke-width="1.8"/>')
        out.append(f'<rect x="{x}" y="{y}" width="6" height="{NH}" rx="3" fill="{col}"/>')
        out.append(f'<text x="{x + 18}" y="{y + 24}" fill="{col}" font-size="12.5" font-weight="700">{html.escape(zh)}</text>')
        out.append(f'<text x="{x + 18 + 13 * len(zh) + 10}" y="{y + 24}" fill="#e8eef6" font-size="14" font-weight="700">{html.escape(i)}</text>')
        resp = str(n.get("responsibility", ""))
        lines = [resp[:17], resp[17:33] + ("…" if len(resp) > 33 else "")]
        for k, ln in enumerate(l for l in lines if l):
            out.append(f'<text x="{x + 18}" y="{y + 48 + k * 19}" fill="#a9b6c6" font-size="13">{html.escape(ln)}</text>')
        if i in bad:
            out.append(f'<circle cx="{x + NW - 16}" cy="{y + 16}" r="9" fill="#ff6b6b"/><text x="{x + NW - 16}" y="{y + 21}" fill="#0b1118" font-size="13" font-weight="800" text-anchor="middle">!</text>')
    for lx, ly, t, c in labels:
        w = 13 * len(t) + 14
        out.append(f'<rect x="{lx - w / 2:.1f}" y="{ly - 10:.1f}" width="{w}" height="20" rx="10" fill="#0b1118" stroke="{c}" stroke-width="0.9"/>'
                   f'<text x="{lx:.1f}" y="{ly + 4.5:.1f}" fill="{c}" font-size="12" text-anchor="middle">{t}</text>')
    ly, lx = H - 40, 40
    for t, c, dash in (("数据流", "#7f8ea3", ""), ("权力边：约束 / 否决 / 仲裁 / 升级", "#f5b84a", ""), ("反馈边：核验 / 观察 / 修订", "#b98cff", "6 5")):
        out.append(f'<line x1="{lx}" y1="{ly}" x2="{lx + 30}" y2="{ly}" stroke="{c}" stroke-width="2.2" stroke-dasharray="{dash}"/>'
                   f'<text x="{lx + 38}" y="{ly + 5}" fill="#a9b6c6" font-size="13">{t}</text>')
        lx += 62 + sum(13 if ord(ch) > 255 else 7 for ch in t)
    if bad:
        out.append(f'<circle cx="{40 + 7}" cy="{ly + 26}" r="7" fill="#ff6b6b"/><text x="{40 + 22}" y="{ly + 31}" fill="#a9b6c6" font-size="13">diagnose 指出的问题节点</text>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--today", default="2026-11-15")
    ap.add_argument("--title")
    a = ap.parse_args()
    spec = json.loads(a.spec.read_text(encoding="utf-8"))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(spec, dt.date.fromisoformat(a.today), a.title), encoding="utf-8")
    print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
