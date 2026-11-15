#!/usr/bin/env python3
"""生成仓库全部配图：拓扑图（4 张）、示意图（3 张）、封面、终端诊断截图。

用法：python3 工具/制作配图v1.0.py
输出：图片/拓扑图/*.svg|webp、图片/示意图/*.webp、文档/主图/封面v1.0.jpg、文档/截图/终端诊断截图v1.0.png
所有图都由仓库里的真实示例和真实命令输出生成，不使用 AI 绘图。
"""
from __future__ import annotations

import datetime as dt
import html
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "工具"
TODAY = "2026-11-15"


def load(name: str, file: str):
    s = importlib.util.spec_from_file_location(name, TOOLS / file)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


topo = load("topo", "绘制拓扑图v1.0.py")
shot = load("shot", "渲染图片v1.0.py")
CLI = TOOLS / "graph-engineering-architect-plus" / "scripts" / "geaplus-v1.1.py"

GRAPHS = [
    ("faers-manuscript-graph-v1.1", "faers-manuscript", "FAERS/JADER 药物警戒论文图（正例）"),
    ("broken-circular-graph-v1.0", "broken-circular", "自我确认的论文图（反例）"),
    ("legacy-trauma-audit-graph-v1.1", "trauma-audit-before", "急诊创伤病历质控图（修复前）"),
    ("legacy-trauma-audit-graph-repaired-v1.1", "trauma-audit-after", "急诊创伤病历质控图（修复后）"),
]

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b1118;color:#e8eef6;font-family:"Noto Sans SC","PingFang SC",sans-serif}
.k{font-size:15px;color:#a9b6c6}
h1{font-size:34px;font-weight:700;letter-spacing:.5px}
h2{font-size:26px;font-weight:700}
small{color:#7f8ea3}
"""


def page(body: str, w: int, h: int) -> str:
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}body{{width:{w}px;height:{h}px;overflow:hidden}}</style></head><body>{body}</body></html>'


def render_html(src: str, out: Path, w: int, h: int, sm: bool = True) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(src)
    shot.shoot(Path(f.name), out, w, h, 2, False, sm, 400)


def schem_repair() -> str:
    layers = [
        ("1", "根结果与归属", "wrong_target", "#f5b84a"),
        ("2", "现实锚点与来源", "decayed_measurement · circular_confirmation · completion_by_consensus", "#43c59e"),
        ("3", "验证者独立性", "watcher_theater · meta_loop_capture", "#b98cff"),
        ("4", "边的权力与仲裁", "metric_gaming · loop_conflict · decorative_graph · local_success_global_harm", "#ff8fb1"),
        ("5", "节奏分离", "cadence_thrashing", "#5b9cff"),
        ("6", "节点实现", "加 Agent、加重试、换模型，放在最后", "#8b98a9"),
    ]
    rows = "".join(
        f'<div style="display:flex;align-items:center;margin:0 0 14px {i * 26}px">'
        f'<div style="width:54px;height:54px;border-radius:14px;background:{c};color:#0b1118;font-size:26px;font-weight:800;display:flex;align-items:center;justify-content:center">{n}</div>'
        f'<div style="margin-left:18px;padding:12px 20px;border:1.5px solid {c};border-radius:14px;background:#121b26;width:{820 - i * 26}px">'
        f'<div style="font-size:21px;font-weight:700;color:{c}">{t}</div><div class="k" style="margin-top:4px;font-family:monospace;font-size:14px">{html.escape(p)}</div></div></div>'
        for i, (n, t, p, c) in enumerate(layers))
    return page(f'<div style="padding:44px 56px"><h2>修复顺序：从底层修起</h2><p class="k" style="margin:8px 0 28px">diagnose 给每个病灶标 repair_layer，按 1 → 6 排序。结构有病时，先修扎根和权力，再考虑加 Agent 或重试。</p>{rows}</div>', 1000, 760)


def schem_cadence() -> str:
    tiers = [("执行", "每次迭代", "在冻结边界内动作", "#5b9cff", 1.0), ("验证", "每个候选 / 每版", "判这一版能不能过", "#b98cff", 0.78),
             ("审计", "每周 / 每月", "查来源、口径、漂移", "#ff9f6b", 0.58), ("治理", "每季度", "审目标、阈值、取舍", "#9fd36f", 0.4),
             ("人", "需要时", "改根目的、冻结规则、权限", "#f5b84a", 0.26)]
    bars = "".join(
        f'<div style="display:flex;align-items:center;margin-bottom:16px"><div style="width:90px;font-size:22px;font-weight:700;color:{c}">{t}</div>'
        f'<div style="flex:1;height:58px;position:relative;border-radius:12px;background:#121b26;border:1.5px solid #223042;overflow:hidden">'
        + "".join(f'<span style="position:absolute;top:13px;left:{14 + j * 34 / f:.0f}px;width:{max(8, 22 * f):.0f}px;height:30px;border-radius:6px;background:{c};opacity:.85"></span>' for j in range(int(26 * f)))
        + f'</div><div style="width:270px;padding-left:18px"><div style="font-size:16px;font-weight:700">{p}</div><div class="k">{d}</div></div></div>'
        for t, p, d, c, f in tiers)
    note = ('<div style="margin-top:20px;padding:14px 18px;border:1.5px dashed #ff6b6b;border-radius:12px;color:#ffb3b3;font-size:16px">'
            'E-CADENCE：更快的层对更慢的层有“修订 / 约束”边 → 快回路搅动慢变量，振荡、掩盖因果。</div>')
    return page(f'<div style="padding:44px 56px"><h2>快慢分层</h2><p class="k" style="margin:8px 0 26px">越往下越慢、权力越大。快层只能输入或升级，不能改慢层的目标、验证者和审批规则。</p>{bars}{note}</div>', 1000, 640)


def schem_patterns() -> str:
    pats = [
        ("刷分", "metric_gaming", "指标变好，真实结果变差", "#ff8fb1"),
        ("目标错位", "wrong_target", "优化的指标不在根目标里", "#f5b84a"),
        ("回路冲突", "loop_conflict", "两个检查者拉扯，没人裁决", "#e7d36f"),
        ("测量过期", "decayed_measurement", "锚点超过有效期仍在用", "#43c59e"),
        ("循环互证", "circular_confirmation", "验证者和执行者读同一来源", "#43c59e"),
        ("元回路劫持", "meta_loop_capture", "改进者能改自己的裁判", "#b98cff"),
        ("看守剧场", "watcher_theater", "验证者只复述执行者的报告", "#b98cff"),
        ("装饰图", "decorative_graph", "箭头很多，没有一条能否决", "#ff8fb1"),
        ("局部成功全局受损", "local_success_global_harm", "各自达标，根结果没人复核", "#ff8fb1"),
        ("节奏搅动", "cadence_thrashing", "快回路反复改慢变量", "#5b9cff"),
        ("共识即完成", "completion_by_consensus", "大家都同意就宣布成功", "#43c59e"),
    ]
    cards = "".join(
        f'<div style="padding:16px 18px;border-radius:14px;background:#121b26;border:1.5px solid {c}">'
        f'<div style="font-size:19px;font-weight:700;color:{c}">{zh}</div><div style="font-family:monospace;font-size:12.5px;color:#7f8ea3;margin:3px 0 7px">{en}</div>'
        f'<div style="font-size:14.5px;color:#cfd8e3">{d}</div></div>' for zh, en, d, c in pats)
    tail = ('<div style="padding:16px 18px;border-radius:14px;border:1.5px dashed #43c59e;display:flex;flex-direction:column;justify-content:center">'
            '<div style="font-size:17px;font-weight:700;color:#43c59e">全部未命中</div><div style="font-size:14.5px;color:#cfd8e3;margin-top:6px">status: healthy<br><small>只说明结构没有漏洞，不证明结论正确</small></div></div>')
    return page(f'<div style="padding:40px 50px"><h2>diagnose 识别的 11 类病灶</h2><p class="k" style="margin:8px 0 24px">每一类都对应 validate 里的一条或几条硬约束，命中后给出证据、修法和修复层级。</p>'
                f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px">{cards}{tail}</div></div>', 1100, 520)


def cover(svg_good: str, svg_bad: str) -> str:
    def crop(svg: str) -> str:
        return svg.replace("<svg ", '<svg style="width:100%;height:auto;display:block" ', 1)
    return page(f'''
<div style="position:absolute;inset:0;background:radial-gradient(1200px 700px at 78% 30%,#14304a 0%,#0b1118 60%)"></div>
<div style="position:absolute;right:40px;top:30px;width:430px;opacity:.95;border-radius:18px;overflow:hidden;box-shadow:0 20px 60px #000a;border:1px solid #223042">{crop(svg_good)}</div>
<div style="position:absolute;right:500px;top:110px;width:330px;opacity:.55;border-radius:18px;overflow:hidden;border:1px solid #3a2026;transform:rotate(-3deg)">{crop(svg_bad)}</div>
<div style="position:absolute;left:70px;top:150px;width:720px">
  <div style="display:inline-block;padding:6px 14px;border:1.5px solid #43c59e;border-radius:20px;color:#43c59e;font-size:16px;font-weight:700">Codex / Claude Code Skill · 零依赖 CLI · v1.1</div>
  <h1 style="font-size:64px;line-height:1.12;margin-top:24px">图工程架构师 Plus</h1>
  <div style="font-size:30px;color:#cfd8e3;margin-top:6px;font-weight:600">Graph Engineering Architect Plus</div>
  <div style="font-size:24px;color:#a9b6c6;margin-top:30px;line-height:1.6">让会自我改进的 Agent 系统，<br><span style="color:#f5b84a;font-weight:700">不会学会骗自己。</span></div>
  <div style="margin-top:38px;display:flex;gap:12px;flex-wrap:wrap">{"".join(f'<span style="padding:8px 14px;border-radius:10px;background:#121b26;border:1px solid #223042;font-size:16px;color:#cfd8e3">{x}</span>' for x in ("validate 硬约束","diagnose 11 类病灶","按修复顺序排序","init 脚手架","Mermaid / SVG 拓扑图","医学科研示例"))}</div>
  <div style="margin-top:46px;font-size:17px;color:#7f8ea3">Haixiang Ding, M.D. · github.com/TUANZIDING/graph-engineering-architect-plus</div>
</div>''', 1600, 900)


def terminal() -> str:
    cmds = [
        ["validate", str(ROOT / "示例" / "legacy-trauma-audit-graph-v1.1.json")],
        ["diagnose", str(ROOT / "示例" / "broken-circular-graph-v1.0.json"), "--today", TODAY],
    ]
    blocks = []
    for c in cmds:
        r = subprocess.run([sys.executable, str(CLI), *c], capture_output=True, text=True)
        txt = r.stdout
        if c[0] == "diagnose":
            d = json.loads(txt)
            txt = f'status: {d["status"]}\n' + "\n".join(
                f'  [{p["repair_layer"]}] {p["pattern"]:<24} {(p["evidence"][:66] + "…") if len(p["evidence"]) > 66 else p["evidence"]}' for p in d["patterns"])
        else:
            txt = "\n".join(l for l in txt.splitlines() if not l.strip().startswith("fix:"))
        shown = " ".join(["geaplus-v1.1.py", c[0], Path(c[1]).name] + c[2:])
        body = html.escape(txt)
        for w, col in (("[ERROR]", "#ff6b6b"), ("[warn ]", "#f5b84a"), ("FAIL", "#ff6b6b"), ("PASS", "#43c59e"), ("blocked", "#ff6b6b")):
            body = body.replace(w, f'<b style="color:{col}">{w}</b>')
        blocks.append(f'<div><span style="color:#43c59e">$</span> <span style="color:#e8eef6">python3 {html.escape(shown)}</span></div><div style="color:#a9b6c6;white-space:pre;margin:6px 0 20px">{body}</div>')
    return page('<div style="margin:34px;border-radius:14px;background:#0f1620;border:1px solid #223042;overflow:hidden">'
                '<div style="height:38px;background:#16202c;display:flex;align-items:center;padding-left:16px;gap:8px">'
                + "".join(f'<i style="width:12px;height:12px;border-radius:6px;background:{c};display:inline-block"></i>' for c in ("#ff5f57", "#febc2e", "#28c840"))
                + '<span style="margin-left:14px;color:#7f8ea3;font-size:13px">geaplus · 真实命令输出</span></div>'
                f'<div style="padding:20px 24px 4px;font-family:DejaVu Sans Mono,Menlo,monospace;font-size:13.5px;line-height:1.55">{"".join(blocks)}</div></div>', 1200, 610)


def main() -> int:
    today = dt.date.fromisoformat(TODAY)
    svgs = {}
    for src, slug, title in GRAPHS:
        spec = json.loads((ROOT / "示例" / f"{src}.json").read_text(encoding="utf-8"))
        svg = topo.render(spec, today, title)
        svgs[slug] = svg
        p = ROOT / "图片" / "拓扑图" / f"{slug}-v1.0.svg"
        p.write_text(svg, encoding="utf-8")
        shot.shoot(p, p.with_suffix(".webp"), None, 900, 2, False, True, 300)
    for name, fn, w, h in (("修复顺序", schem_repair, 1000, 760), ("快慢分层", schem_cadence, 1000, 640), ("十一类病灶", schem_patterns, 1100, 520)):
        render_html(fn(), ROOT / "图片" / "示意图" / f"{name}v1.0.webp", w, h)
    render_html(cover(svgs["faers-manuscript"], svgs["broken-circular"]), ROOT / "文档" / "主图" / "封面v1.0.jpg", 1600, 900, sm=False)
    render_html(terminal(), ROOT / "文档" / "截图" / "终端诊断截图v1.0.png", 1200, 610, sm=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
