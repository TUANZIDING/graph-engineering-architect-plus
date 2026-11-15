#!/usr/bin/env python3
"""按冻结模板拼出每个运行的派发文本：python3 生成派发文本v0.3.py <cond> <tid> <r>"""
import json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
KIT = "/workspace/projects/83285865-ddff-4b21-b031-2ead93455e58/evalkit"
tpl = (HERE / "派发模板v0.3.md").read_text(encoding="utf-8")
common = tpl.split("## 共同部分\n", 1)[1].split("\n## unguided", 1)[0]
extra = {c: re.search(rf"## {c} 追加\n(.*?)(?=\n## |\Z)", tpl, re.S).group(1).strip() for c in ("unguided", "g11", "g12")}
tasks = {t["id"]: t for t in json.loads((HERE / "评测任务v0.3.json").read_text(encoding="utf-8"))["tasks"]}
cond, tid, r = sys.argv[1], sys.argv[2], sys.argv[3]
runid = f"{cond}-{tid}-r{r}-v0.3"
out = f"{HERE}/运行结果/{runid}.json"
text = (common + "\n" + extra[cond]).replace("{BRIEF}", tasks[tid]["brief"]).replace("{OUT}", out).replace("{RUNID}", runid).replace("{KIT}", KIT)
print(text.strip())
