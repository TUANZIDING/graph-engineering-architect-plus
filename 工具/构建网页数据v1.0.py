#!/usr/bin/env python3
"""对 示例/ 里的四张图运行 validate + diagnose，把结果和拓扑 SVG 写进 assets/data/examplesv1.0.js 供 index.html 使用。

用法：python3 工具/构建网页数据v1.0.py   （先运行 工具/制作配图v1.0.py 生成 SVG）
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location("geaplus", ROOT / "工具" / "graph-engineering-architect-plus" / "scripts" / "geaplus-v1.1.py")
gea = importlib.util.module_from_spec(s)
s.loader.exec_module(gea)

TODAY = dt.date(2026, 11, 15)
ITEMS = [
    ("faers-manuscript", "faers-manuscript-graph-v1.1", "药物警戒论文（正例）",
     "FAERS/JADER 信号分析 → 独立复算 + 阴性对照 → 仲裁 → 初稿 → 结论审计 → 作者确认。复算者不看主代码，只拿冻结的数据快照。"),
    ("broken-circular", "broken-circular-graph-v1.0", "自我确认（反例）",
     "同一张论文图删掉反指标、让复算者读主分析代码、锚点 106 天未复核。diagnose 一次查出循环互证、测量过期、刷分风险。"),
    ("trauma-audit-before", "legacy-trauma-audit-graph-v1.1", "病历质控（修复前）",
     "旧格式写法，字段齐全；但现实锚点只连到书写医生，质控员没拿到原始记录，补写 ↔ 核对也没有轮数上限。"),
    ("trauma-audit-after", "legacy-trauma-audit-graph-repaired-v1.1", "病历质控（修复后）",
     "加 3 条边（锚点 → 质控员；病历、核对报告 → 反指标）和轮数上限、锚点有效期，validate 与 diagnose 都通过。"),
]


def main() -> int:
    out = []
    for slug, src, name, desc in ITEMS:
        spec = json.loads((ROOT / "示例" / f"{src}.json").read_text(encoding="utf-8"))
        f = gea.validate(spec)
        d = gea.diagnose(spec, TODAY, None)
        out.append({
            "slug": slug, "name": name, "desc": desc, "file": f"示例/{src}.json",
            "svg": (ROOT / "图片" / "拓扑图" / f"{slug}-v1.0.svg").read_text(encoding="utf-8"),
            "status": d["status"],
            "errors": [{"code": i["code"], "msg": i["message"]} for i in f.errors],
            "warnings": [{"code": i["code"], "msg": i["message"]} for i in f.items if i["level"] == "warning"],
            "patterns": [{k: p[k] for k in ("pattern", "evidence", "repair_layer", "layer_name")} for p in d["patterns"]],
        })
    p = ROOT / "assets" / "data" / "examplesv1.0.js"
    p.write_text("window.GEA_EXAMPLES = " + json.dumps(out, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(p, len(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
