#!/usr/bin/env python3
"""汇总评分结果v0.2.json：按任务×条件给出通过次数与断言通过率，并按断言统计 guided vs unguided。不改评分逻辑。"""
import json
from collections import defaultdict
from pathlib import Path

rows = json.loads((Path(__file__).resolve().parent / "运行结果" / "评分结果v0.2.json").read_text(encoding="utf-8"))
by = defaultdict(list)
for r in rows:
    by[(r["task"], r["condition"])].append(r)
print("任务   条件       通过/次数  断言均值  结构通过")
for t in sorted({r["task"] for r in rows}, key=lambda x: int(x[1:])):
    for c in ("unguided", "guided"):
        rs = by.get((t, c), [])
        if rs:
            print(f"{t:5s}  {c:9s}  {sum(x['semantic_pass'] for x in rs)}/{len(rs):<8d} {sum(x['semantic_rate'] for x in rs)/len(rs):6.0%}   {sum(x['structural_pass'] for x in rs)}/{len(rs)}")
print("\n断言                                    unguided  guided")
agg = defaultdict(lambda: {"unguided": [0, 0], "guided": [0, 0]})
for r in rows:
    for k, v in (r.get("semantic") or {}).items():
        a = agg[(r["task"], k)][r["condition"]]
        a[0] += bool(v); a[1] += 1
for (t, k), d in sorted(agg.items(), key=lambda x: int(x[0][0][1:])):
    u, g = d["unguided"], d["guided"]
    print(f"{t:4s} {k:34s}  {u[0]}/{u[1]}      {g[0]}/{g[1]}")

# 结构错误拆成“格式类”和“实质类”：格式类只说明没按规格填字段，实质类才是控制设计缺陷。
FORMAT = {"E-STATE", "E-FAIL", "E-CONTRACT", "E-MODE", "E-NODES", "E-METRICS", "E-BUDGET", "E-APPROVAL", "E-STOP", "E-PERM", "E-EXEC", "E-SCHEMA"}
print("\n实质类结构缺陷（每份图出现的错误码）")
sub = {"unguided": [0, 0], "guided": [0, 0]}
for r in rows:
    if r.get("mode") not in ("graph", "graph_plus_loop"):
        continue
    codes = sorted({e.split(":")[0] for e in (r.get("validate_errors") or [])} - FORMAT)
    sub[r["condition"]][1] += 1
    sub[r["condition"]][0] += bool(codes) or bool(r.get("structural_crash"))
    if codes:
        print(f"  {r['file']:30s} {codes}")
for c, (bad, n) in sub.items():
    print(f"{c:9s} 有实质缺陷的图 {bad}/{n}")
