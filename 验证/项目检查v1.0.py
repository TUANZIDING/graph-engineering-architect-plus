#!/usr/bin/env python3
"""项目检查：回归测试 + 示例预期状态 + 文件命名 + 图片与链接完整性 + 文档副本一致。

用法：python3 验证/项目检查v1.0.py      （GitHub Actions 每次 push 自动运行）
零依赖。任何一项失败即返回非零。
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "工具" / "graph-engineering-architect-plus"
fails: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


print("1. 回归测试")
for t in ("回归测试v1.0.py", "回归测试v1.1.py", "回归测试v1.2.py"):
    r = subprocess.run([sys.executable, str(ROOT / "验证" / t)], capture_output=True, text=True)
    ran = re.search(r"Ran (\d+) tests", r.stderr)
    check(r.returncode == 0, f"{t}：{ran.group(1) if ran else '?'} 个测试")

print("2. 示例预期状态")
s = importlib.util.spec_from_file_location("geaplus", SKILL / "scripts" / "geaplus-v1.2.py")
gea = importlib.util.module_from_spec(s)
s.loader.exec_module(gea)
EXPECT = {
    "faers-manuscript-graph-v1.1.json": "healthy",
    "broken-circular-graph-v1.0.json": "blocked",
    "legacy-trauma-audit-graph-v1.1.json": "blocked",
    "legacy-trauma-audit-graph-repaired-v1.1.json": "healthy",
}
for f, want in EXPECT.items():
    d = gea.diagnose(json.loads((ROOT / "示例" / f).read_text(encoding="utf-8")), dt.date(2026, 11, 15), None)
    check(d["status"] == want, f"{f} → {d['status']}（预期 {want}）")

print("3. 文件命名（无下划线；新文件带版本号）")
EXEMPT = {"README.md", "LICENSE", "SKILL.md", "CITATION.cff", ".nojekyll", ".gitignore", "index.html", "MIT.txt"}
for p in ROOT.rglob("*"):
    if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts:
        continue
    n = p.name
    if n in EXEMPT:
        continue
    if "_" in n:
        check(False, f"文件名含下划线：{p.relative_to(ROOT)}")
    if not re.search(r"v\d+\.\d+", n):
        check(False, f"缺版本号：{p.relative_to(ROOT)}")

n_named = sum(1 for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts)
check(True, f"已检查 {n_named} 个文件名")

print("4. README 与 index.html 引用的本地文件都存在")
for doc in ("README.md", "index.html", "文档/英文说明v1.0.md", "示例/示例说明v1.0.md"):
    txt = (ROOT / doc).read_text(encoding="utf-8")
    refs = set(re.findall(r'(?:src|href)="([^"#:]+)"', txt)) | set(re.findall(r"\]\(([^)#:]+)\)", txt))
    base = (ROOT / doc).parent
    missing = [r for r in refs if not (base / r).exists() and not (ROOT / r).exists()]
    check(not missing, f"{doc}：{len(refs)} 处本地引用" + (f"，缺 {missing}" if missing else ""))

print("5. 文档副本与 Skill 内参考文件一致")
for a, b in (("文档/设计手册v1.0.md", "工具/graph-engineering-architect-plus/references/design-principles-v1.0.md"),
             ("文档/规格说明v1.1.md", "工具/graph-engineering-architect-plus/references/graph-spec-v1.1.md"),
             ("文档/规格说明v1.2.md", "工具/graph-engineering-architect-plus/references/graph-spec-v1.2.md"),
             ("文档/领域效度清单v1.2.md", "工具/graph-engineering-architect-plus/references/domain-checklists-v1.2.md")):
    check((ROOT / a).read_bytes() == (ROOT / b).read_bytes(), f"{a} == {b}")

print("6. 第三方文件未混入")
bad = [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts and re.search(r"upstream|2023Anita|luxiaolei", str(p.relative_to(ROOT)))]
check(not bad, "仓库内没有上游副本")

print()
if fails:
    print(f"项目检查失败：{len(fails)} 项")
    sys.exit(1)
print("项目检查通过")
