#!/usr/bin/env python3
"""图工程架构师 Plus 评测 v0.1 评分器（零依赖）。

思路借鉴 GoogleChrome/modern-web-guidance：同一批真实任务，分别让 Agent 在
“无 Skill（unguided）”与“有 Skill（guided）”两种条件下作答，用同一套评分器打分，
看提升多少个百分点（uplift）。

两类断言分开报告，避免“拿自己的尺子量自己”：
  - 结构分（structural）：geaplus validate 无错误 + diagnose 为 healthy。
    这是 Skill 自己的规则，偏向 guided，只作参考。
  - 语义分（semantic）：每个任务从任务描述本身推出的 4-5 条断言
    （例如“隐藏测试集不得喂给调参回路”“上传前有我的人工门”），
    与 geaplus 代码无关，是更公平的主指标。

用法：
  python3 评分器v0.1.py calibrate          标准答案必须 100% 通过、朴素基线必须 100% 不通过
  python3 评分器v0.1.py grade <文件或目录>  打分；目录内文件名形如 guided-t1-r1-v0.1.json
  python3 评分器v0.1.py report <目录>        汇总 unguided vs guided 的通过率与提升
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKS = {t["id"]: t for t in json.loads((HERE / "评测任务v0.1.json").read_text(encoding="utf-8"))["tasks"]}
GRAPH_MODES = {"graph", "graph_plus_loop"}
TODAY = dt.date(2026, 11, 15)

_s = importlib.util.spec_from_file_location(
    "geaplus", ROOT / "工具" / "graph-engineering-architect-plus" / "scripts" / "geaplus-v1.1.py")
gea = importlib.util.module_from_spec(_s)
_s.loader.exec_module(gea)

VERIFY_KINDS = {"verification_loop", "audit_loop", "counter_metric_loop"}
FORWARD = {"feeds", "verifies", "constrains", "vetoes", "escalates", "arbitrates", "anchors", "hands_off"}


# ---------- 小工具 ----------
def txt(o) -> str:
    return json.dumps(o, ensure_ascii=False).lower()


def nodes(g):
    return g.get("nodes", []) or []


def edges(g):
    return g.get("edges", []) or []


def mode(g) -> str:
    m = g.get("mode") or (g.get("classification") or {}).get("mode") or ""
    return str(m).strip().lower()


def by_kind(g, kinds):
    return [n for n in nodes(g) if n.get("kind") in kinds]


def anchor_blobs(g):
    """锚点 = anchors[] 条目 + kind=anchor 的节点（两者都算）。返回 (node_id, 文本)。"""
    out = []
    for a in g.get("anchors", []) or []:
        nid = a.get("node_id")
        node = next((n for n in nodes(g) if n.get("id") == nid), {})
        out.append((nid, txt(a) + txt(node)))
    for n in by_kind(g, {"anchor"}):
        if not any(n.get("id") == x[0] for x in out):
            out.append((n.get("id"), txt(n)))
    return out


def any_node_matches(g, kinds, pattern):
    rx = re.compile(pattern, re.I)
    return any(rx.search(txt(n)) for n in by_kind(g, kinds))


def gate_or_forbidden(g, pattern, gate_owner_pattern=None):
    rx = re.compile(pattern, re.I)
    for n in by_kind(g, {"human_gate"}):
        t = txt(n)
        if rx.search(t) and (gate_owner_pattern is None or re.search(gate_owner_pattern, t, re.I)):
            return True
    perms = g.get("permissions") or {}
    forb = txt(perms.get("forbidden_actions", [])) + txt((g.get("root_goal") or {}).get("out_of_scope", []))
    return gate_owner_pattern is None and bool(rx.search(forb))


def optimizers(g):
    opt = [n for n in nodes(g) if n.get("optimizes")]
    return opt or by_kind(g, {"execution_loop", "execution"})


# ---------- 语义断言（每个任务独立于 geaplus 的规则） ----------
def sem_t1(g):
    anchors = anchor_blobs(g)
    hold = [a for a in anchors if re.search(r"hold|sealed|留出|未见|隐藏|held-out|holdout|冻结.*(折|集)|private|盲", a[1], re.I)]
    opt_ids = {n.get("id") for n in optimizers(g)}
    hold_ids = {a[0] for a in hold}
    leak = any(e.get("from") in hold_ids and e.get("to") in opt_ids and e.get("relation") in {"feeds", "anchors"} for e in edges(g))
    return {
        "留出/隐藏数据作锚点": bool(hold),
        "留出数据不喂给调参回路（防泄漏）": bool(hold) and not leak,
        "有防过拟合/公开榜偏差的反指标": any_node_matches(g, {"counter_metric_loop", "audit_loop"},
                                              r"过拟合|overfit|公开|public|方差|variance|稳定|泄漏|leak|波动|shake"),
        "最终上传前有我的人工门": gate_or_forbidden(g, r"上传|提交|submit|upload"),
        "写明提交次数限制": bool(re.search(r"5\s*次|配额|quota|一次|once|次数|limit", txt(g), re.I)),
    }


def sem_t2(g):
    anchors = anchor_blobs(g)
    return {
        "有独立的引用核实节点": any_node_matches(g, VERIFY_KINDS, r"引用|参考文献|citation|reference|pubmed|doi|crossref"),
        "有数字/数据核对节点": any_node_matches(g, VERIFY_KINDS, r"数字|数值|number|numeric|统计|数据|figure"),
        "有防夸大结论的检查": any_node_matches(g, VERIFY_KINDS | {"arbitration"}, r"夸大|新颖|overclaim|hype|因果|措辞|过度|exaggerat|novel"),
        "锚点是外部文献库/原文": any(re.search(r"pubmed|crossref|doi|原文|全文|数据库|database|full.?text", a[1], re.I) for a in anchors),
        "投稿由我决定": gate_or_forbidden(g, r"投稿|submi"),
    }


def sem_t3(g):
    anchors = anchor_blobs(g)
    opt_ids = {n.get("id") for n in optimizers(g)}
    guard_ids = {n.get("id") for n in nodes(g) if n.get("kind") in VERIFY_KINDS | {"anchor", "human_gate", "governance_loop", "arbitration"}}
    capture = any(e.get("from") in opt_ids and e.get("to") in guard_ids and e.get("relation") in {"revises", "constrains"} for e in edges(g))
    return {
        "有报警负担/误报反指标": any_node_matches(g, {"counter_metric_loop", "audit_loop"},
                                       r"误报|假阳性|报警(负担|量|次数)|疲劳|false|alarm|ppv|特异"),
        "锚点是真实结局/病历复核": any(re.search(r"病历|结局|outcome|复核|chart|确诊|真实|随访", a[1], re.I) for a in anchors),
        "上线前有质量委员会人工门": gate_or_forbidden(g, r"上线|部署|deploy|阈值|threshold|发布", r"委员会|committee"),
        "调参者不能改裁判": not capture,
        "敏感度与报警量冲突有仲裁": bool(by_kind(g, {"arbitration"})) or bool(re.search(r"priority_policy", txt(g))),
    }


def sem_t4(g):
    anchors = anchor_blobs(g)
    succ = txt((g.get("root_goal") or {}).get("observable_success", ""))
    return {
        "有答案准确性核对": any_node_matches(g, VERIFY_KINDS, r"指南|guideline|准确|正确|accuracy|答案|answer"),
        "锚点是现行指南/教材": any(re.search(r"指南|guideline|教材|共识|textbook|consensus", a[1], re.I) for a in anchors),
        "根目标不是满意度本身": bool(re.search(r"正确|准确|掌握|成绩|学习|learning|accuracy|知识|能力|指南|guideline", succ, re.I)),
        "有防迎合满意度的反指标": any_node_matches(g, {"counter_metric_loop", "audit_loop"},
                                        r"满意|satisfaction|难度|迎合|简单|difficulty|区分度|discriminat"),
        "发布前带教老师审核": gate_or_forbidden(g, r"发布|上线|release|publish|审核", r"老师|教师|带教|teacher|faculty"),
    }


SEM = {"t1": sem_t1, "t2": sem_t2, "t3": sem_t3, "t4": sem_t4}


def grade(g: dict, task_id: str) -> dict:
    t = TASKS[task_id]
    m = mode(g)
    res = {"task": task_id, "mode": m, "semantic": {}, "structural": {}}
    if t["kind"] == "simple":
        res["semantic"] = {f"mode 为 {'/'.join(t['expected_modes'])}（不过度建图）": m in t["expected_modes"]}
        res["structural"] = {"不适用": True}
    else:
        res["semantic"]["判为 graph / graph_plus_loop"] = m in GRAPH_MODES
        if m in GRAPH_MODES:
            res["semantic"].update(SEM[task_id](g))
            try:
                errs = gea.validate(g).errors
                d = gea.diagnose(g, TODAY, None)
                res["structural"] = {"validate 无错误": not errs, "diagnose 为 healthy": d["status"] == "healthy"}
                res["validate_errors"] = [f"{e['code']}: {e['message']}" for e in errs][:12]
                res["diagnose_patterns"] = [p.get("pattern") for p in d.get("patterns", [])]
            except Exception as e:  # geaplus 自身在畸形输入上崩溃：结构判不过，但语义照常计分
                res["structural"] = {"validate 无错误": False, "diagnose 为 healthy": False}
                res["structural_crash"] = f"{type(e).__name__}: {e}"
        else:
            for k in SEM[task_id]({}).keys():
                res["semantic"][k] = False
            res["structural"] = {"validate 无错误": False, "diagnose 为 healthy": False}
    res["semantic_pass"] = all(res["semantic"].values())
    res["structural_pass"] = all(res["structural"].values())
    res["semantic_rate"] = sum(res["semantic"].values()) / len(res["semantic"])
    return res


def task_of(path: Path) -> str:
    m = re.search(r"(?:^|-)(t\d+)(?:-|$)", path.stem)
    if not m:
        raise SystemExit(f"文件名里找不到任务号：{path.name}")
    return m.group(1)


def load(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return json.loads(raw)


def cmd_calibrate() -> int:
    bad = 0
    print("标准答案（必须全部通过）")
    for p in sorted((HERE / "标准答案").glob("*.json")):
        r = grade(load(p), task_of(p))
        ok = r["semantic_pass"] and r["structural_pass"]
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {p.name}  语义 {r['semantic_rate']:.0%}  结构 {r['structural']}" + ("" if ok else f"  {r.get('validate_errors')} {r.get('diagnose_patterns')} {r['semantic']}"))
    print("朴素基线（必须全部不通过）")
    for p in sorted((HERE / "朴素基线").glob("*.json")):
        r = grade(load(p), task_of(p))
        ok = not r["semantic_pass"]
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {p.name}  语义 {r['semantic_rate']:.0%}（未通过项 {[k for k, v in r['semantic'].items() if not v]}）")
    print("校准通过" if not bad else f"校准失败 {bad} 项")
    return 1 if bad else 0


def cmd_grade(target: Path) -> list[dict]:
    files = sorted(target.glob("*.json")) if target.is_dir() else [target]
    out = []
    for p in files:
        try:
            r = grade(load(p), task_of(p))
        except Exception as e:  # 无法解析也算失败
            r = {"task": task_of(p), "semantic_pass": False, "structural_pass": False, "semantic_rate": 0.0, "error": str(e)}
        r["file"] = p.name
        r["condition"] = "guided" if p.name.startswith("guided") else "unguided" if p.name.startswith("unguided") else "?"
        out.append(r)
    return out


def cmd_report(target: Path) -> None:
    rows = cmd_grade(target)
    for cond in ("unguided", "guided"):
        rs = [r for r in rows if r["condition"] == cond]
        if not rs:
            continue
        sp = sum(r["semantic_pass"] for r in rs) / len(rs)
        sr = sum(r["semantic_rate"] for r in rs) / len(rs)
        st = sum(r["structural_pass"] for r in rs) / len(rs)
        print(f"{cond:9s} n={len(rs):2d}  任务通过率 {sp:6.0%}  断言通过率 {sr:6.0%}  结构通过率 {st:6.0%}")
    print()
    for r in rows:
        fails = [k for k, v in (r.get("semantic") or {}).items() if not v]
        print(f"{r['file']:32s} mode={r.get('mode','?'):16s} 语义 {r['semantic_rate']:4.0%} 结构 {'通过' if r['structural_pass'] else '未过'}  未过：{fails or '—'}{'  ' + r['error'] if r.get('error') else ''}")
    (target / "评分结果v0.1.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    c = sys.argv[1]
    if c == "calibrate":
        sys.exit(cmd_calibrate())
    if c == "grade":
        print(json.dumps(cmd_grade(Path(sys.argv[2])), ensure_ascii=False, indent=1))
    elif c == "report":
        cmd_report(Path(sys.argv[2]))
