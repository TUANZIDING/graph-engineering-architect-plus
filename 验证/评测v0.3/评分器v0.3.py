#!/usr/bin/env python3
"""图工程架构师 Plus 评测 v0.3 评分器（零依赖）。断言在任何运行之前写定（2026-11-15）。

三组条件：unguided（无 Skill）、g11（Skill v1.1）、g12（Skill v1.2），每格 3 次。
与 v0.2 的区别：
  - 全新留出任务 t14–t18（v1.2 的规则是看过 v0.2 才写的，不能在原题上复测）。
  - 语义断言中英双语（v0.2 的 t7 因为模型用英文写而误判）；尽量用结构判定而不是关键词。
  - 语义断言不读 domain / domain_audits 字段，避免 v1.2 因为“填了表”而得分。
  - 结构分分别用 geaplus v1.1 与 v1.2 计算，两者都是 Skill 自己的尺子，只作参考。

用法：
  python3 评分器v0.3.py calibrate
  python3 评分器v0.3.py report <目录>      文件名形如 g12-t14-r1-v0.3.json
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
TASKS = {t["id"]: t for t in json.loads((HERE / "评测任务v0.3.json").read_text(encoding="utf-8"))["tasks"]}
GRAPH_MODES = {"graph", "graph_plus_loop"}
TODAY = dt.date(2026, 11, 15)
CONDS = ("unguided", "g11", "g12")


def _load_gea(v):
    s = importlib.util.spec_from_file_location(f"geaplus{v}", ROOT / "工具" / "graph-engineering-architect-plus" / "scripts" / f"geaplus-v{v}.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


GEA = {"v1.1": _load_gea("1.1"), "v1.2": _load_gea("1.2")}
VERIFY = {"verification_loop", "audit_loop", "counter_metric_loop"}
WATCH = {"counter_metric_loop", "audit_loop"}


# ---------- 小工具 ----------
def txt(o) -> str:
    return json.dumps(o, ensure_ascii=False).lower()


def nodes(g):
    return [n for n in (g.get("nodes") or []) if isinstance(n, dict)]


def edges(g):
    return [e for e in (g.get("edges") or []) if isinstance(e, dict)]


def mode(g) -> str:
    return str(g.get("mode") or (g.get("classification") or {}).get("mode") or "").strip().lower()


def by_kind(g, kinds):
    return [n for n in nodes(g) if n.get("kind") in kinds]


def node_text(g, n):
    return txt(n)


def anchor_blobs(g):
    out = []
    for a in g.get("anchors") or []:
        if not isinstance(a, dict):
            continue
        nid = a.get("node_id")
        node = next((n for n in nodes(g) if n.get("id") == nid), {})
        out.append((nid, txt(a) + txt(node)))
    for n in by_kind(g, {"anchor"}):
        if not any(n.get("id") == x[0] for x in out):
            out.append((n.get("id"), txt(n)))
    return out


def rx(p):
    return re.compile(p, re.I)


def any_node(g, kinds, *patterns):
    return any(all(rx(p).search(txt(n)) for p in patterns) for n in by_kind(g, kinds))


def has_teeth(g, nid):
    return any(e.get("from") == nid and e.get("relation") in {"vetoes", "constrains", "escalates"} for e in edges(g))


def any_node_with_teeth(g, kinds, *patterns):
    return any(all(rx(p).search(txt(n)) for p in patterns) and has_teeth(g, n.get("id")) for n in by_kind(g, kinds))


def rules_text(g):
    return txt((g.get("permissions") or {}).get("forbidden_actions", [])) + txt(g.get("frozen_rules", []))


def success_text(g):
    rg = g.get("root_goal") or {}
    return txt(rg.get("observable_success", "")) + txt(rg.get("statement", ""))


def gate(g, pattern):
    """人工门：存在 human_gate 节点提到该动作，或 forbidden_actions 明确禁止自动执行该动作。"""
    if any_node(g, {"human_gate"}, pattern):
        return True
    return bool(rx(pattern).search(rules_text(g)))


def optimizers(g):
    return [n for n in nodes(g) if n.get("optimizes")] or by_kind(g, {"execution_loop", "execution"})


def not_captured(g):
    opt = {n.get("id") for n in optimizers(g)}
    guards = {n.get("id") for n in nodes(g) if n.get("kind") in VERIFY | {"anchor", "human_gate", "governance_loop", "arbitration"}}
    return not any(e.get("from") in opt and e.get("to") in guards and e.get("relation") in {"revises", "constrains"} for e in edges(g))


# ---------- 语义断言（中英双语） ----------
def sem_t14(g):
    t = txt(g)
    outcome = r"确诊|结局|sepsis-?3|血培养|blood culture|抗生素|antibiotic|icu|死亡|mortality|outcome|病历(复核|回顾)|chart.?review|乳酸|lactate|最终诊断|final diagnos|adjudicat"
    missed = r"漏报|漏诊|漏检|敏感|召回|假阴性|sensitiv|recall|miss|false.?negative|under.?detect|延误|delay"
    label_bias = (r"(护士|nurse|误报标记|false.?alarm.?label|label).{0,60}(偏倚|主观|不可靠|不作|不能(直接)?作|不等于|复核|核实|独立|bias|subjective|unreliable|noisy|not .{0,12}(gold|ground|truth|sole)|adjudicat|verif|review)"
                  r"|(病历|chart).{0,8}(复核|回顾|review)|独立(判定|裁定|复核)|adjudicat")
    return {
        "锚点含真实脓毒症结局": any(rx(outcome).search(a[1]) for a in anchor_blobs(g)),
        "有漏报/敏感性反指标且能否决或升级": any_node_with_teeth(g, VERIFY, missed),
        "护士误报标记不当金标准": bool(rx(label_bias).search(t)),
        "阈值变更须人工门": gate(g, r"阈值|threshold|上线|部署|deploy|生效|变更|release|activat"),
        "成功标准不只是误报减半": bool(rx(missed + r"|安全|safety|结局|outcome|死亡|mortality").search(success_text(g))),
    }


def sem_t15(g):
    t = txt(g)
    src = r"原文|全文|pdf|original|full.?text|source (article|paper|document)|primary (report|study)"
    return {
        "复核回到原文且独立": any_node(g, VERIFY | {"arbitration"}, src, r"独立|independent|双人|double|dual|second|背对背|blind|re.?extract|重新提取|二次"),
        "有偏倚/证据确定性评估": any_node(g, VERIFY | {"arbitration", "human_gate"}, r"偏倚|bias|rob\b|rob2|robins|grade|证据(质量|确定性|等级)|certainty|quality of evidence|质量评价"),
        "检查撤稿/重复发表": bool(rx(r"撤稿|撤回|retract|重复发表|重复报告|duplicate|同一(队列|人群|试验)|overlapping (cohort|population|sample)|salami").search(t)),
        "结论/推荐变更须人工门": gate(g, r"结论|推荐|recommend|conclusion|网站|website|发布|publish|公开"),
        "复核不只查格式": any_node(g, VERIFY | {"arbitration"}, r"效应|数据|数值|内容|准确|纳入标准|入选|accura|effect|value|content|eligib|inclusion|correct"),
    }


def sem_t16(g):
    t = txt(g)
    weaken = (r"(删|改|修改|弱化|跳过|禁用|放宽|编辑|skip|modify|delete|remove|disable|weaken|loosen|relax|edit|xfail|alter|change).{0,24}(既有|原有|已有|现有|冻结|existing|frozen|protected)?.{0,8}(测试|test|断言|assert|ci\b|workflow|工作流|配置|config)"
              r"|(既有|原有|已有|现有|冻结|existing|frozen|protected).{0,12}(测试|test|ci\b|workflow).{0,24}(只读|不可|不得|禁止|冻结|read.?only|immutable|must not|may not|cannot)")
    return {
        "既有测试作为冻结锚点": any(rx(r"测试|test").search(a[1]) for a in anchor_blobs(g)),
        "禁止修复者删改测试或 CI 配置": bool(rx(weaken).search(rules_text(g))),
        "发布 PyPI 须人工门": gate(g, r"发布|release|pypi|publish|打 ?tag|\btag\b|上传"),
        "有独立代码/测试审查": any_node(g, VERIFY | {"human_gate"}, r"审查|评审|审阅|review|maintainer|维护者|变异|mutation"),
        "issue 内容视为不可信或须复现确认": bool(rx(r"复现|重现|reproduc|注入|inject|恶意|malicious|不可信|untrusted|adversar|spam|垃圾").search(t)),
        "修复者不能改裁判": not_captured(g),
    }


def sem_t17(g):
    t = txt(g)
    expert = r"专家|教师|带教|主治|教研|faculty|expert|attending|educator|教材|指南|guideline|textbook|blueprint|考纲|大纲"
    goodhart = r"区分度|鉴别|信度|效度|discriminat|reliab|valid|point.?biserial|泄题|泄露|leak|曝光|exposure|线索|cue|题目质量|item quality|内容覆盖|coverage|blueprint|考纲|大纲"
    return {
        "题目与答案由独立专家或权威来源核对": any(rx(expert).search(a[1]) for a in anchor_blobs(g)) or any_node(g, VERIFY | {"human_gate"}, expert),
        "有防刷正确率的反指标且能否决或升级": any_node_with_teeth(g, VERIFY, goodhart),
        "进入正式考试须人工门": gate(g, r"考试|exam|正式|入库|发布|上线|启用|use in|deploy|release"),
        "成功标准不只是 70% 正确率": bool(rx(r"能力|胜任|区分|效度|信度|准确|正确性|覆盖|competen|discrimin|valid|reliab|accura|correct|coverage|blueprint").search(success_text(g))),
        "调整者不能改裁判": not_captured(g),
    }


SEM = {"t14": sem_t14, "t15": sem_t15, "t16": sem_t16, "t17": sem_t17}


def structural(g):
    out, errs, pats = {}, {}, {}
    for v, m in GEA.items():
        try:
            e = m.validate(g, TODAY) if v == "v1.2" else m.validate(g)
            d = m.diagnose(g, TODAY, None)
            ok_status = {"healthy", "pending_revalidation"} if v == "v1.2" else {"healthy"}
            out[v] = (not e.errors) and d["status"] in ok_status
            errs[v] = [i["code"] for i in e.errors]
            pats[v] = [p.get("pattern") for p in d.get("patterns", [])]
        except Exception as ex:
            out[v] = False
            errs[v] = [f"CRASH {type(ex).__name__}: {ex}"]
            pats[v] = []
    return out, errs, pats


def grade(g: dict, task_id: str) -> dict:
    t = TASKS[task_id]
    m = mode(g)
    res = {"task": task_id, "mode": m, "semantic": {}}
    if t["kind"] == "simple":
        res["semantic"] = {f"mode 为 {'/'.join(t['expected_modes'])}": m in t["expected_modes"]}
        res["structural"] = {"v1.1": True, "v1.2": True}
    else:
        res["semantic"]["判为 graph / graph_plus_loop"] = m in GRAPH_MODES
        sem = SEM[task_id](g if m in GRAPH_MODES else {})
        if m not in GRAPH_MODES:
            sem = {k: False for k in sem}
        res["semantic"].update(sem)
        if m in GRAPH_MODES:
            res["structural"], res["errors"], res["patterns"] = structural(g)
        else:
            res["structural"] = {"v1.1": False, "v1.2": False}
        rg = g.get("root_goal") if isinstance(g.get("root_goal"), dict) else {}
        res["declared_domain"] = bool(rg.get("domain"))
    res["semantic_pass"] = all(res["semantic"].values())
    res["semantic_rate"] = sum(res["semantic"].values()) / len(res["semantic"])
    return res


def task_of(p: Path) -> str:
    m = re.search(r"(?:^|-)(t\d+)(?:-|$)", p.stem)
    if not m:
        raise SystemExit(f"文件名里找不到任务号：{p.name}")
    return m.group(1)


def load(p: Path) -> dict:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", p.read_text(encoding="utf-8").strip())
    return json.loads(raw)


def cmd_calibrate() -> int:
    bad = 0
    print("标准答案（语义全过 + v1.1/v1.2 结构全过）")
    for p in sorted((HERE / "标准答案").glob("*.json")):
        r = grade(load(p), task_of(p))
        ok = r["semantic_pass"] and all(r["structural"].values())
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {p.name} 语义 {r['semantic_rate']:.0%} 结构 {r['structural']}" + ("" if ok else f" {r.get('errors')} {r.get('patterns')} {r['semantic']}"))
    print("朴素基线（语义必须不全过）")
    for p in sorted((HERE / "朴素基线").glob("*.json")):
        r = grade(load(p), task_of(p))
        ok = not r["semantic_pass"]
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {p.name} 语义 {r['semantic_rate']:.0%}")
    print("校准通过" if not bad else f"校准失败 {bad} 项")
    return 1 if bad else 0


def cmd_report(target: Path) -> None:
    rows = []
    for p in sorted(target.glob("*.json")):
        c = p.name.split("-")[0]
        if c not in CONDS:
            continue
        try:
            r = grade(load(p), task_of(p))
        except Exception as e:
            r = {"task": task_of(p), "semantic_pass": False, "semantic_rate": 0.0, "structural": {"v1.1": False, "v1.2": False}, "error": str(e)}
        r["file"], r["condition"] = p.name, c
        rows.append(r)
    for c in CONDS:
        rs = [r for r in rows if r["condition"] == c]
        if not rs:
            continue
        cx = [r for r in rs if TASKS[r["task"]]["kind"] != "simple"]
        print(f"{c:9s} n={len(rs):2d} 任务通过 {sum(r['semantic_pass'] for r in rs):2d}/{len(rs)}  断言通过率 {sum(r['semantic_rate'] for r in rs)/len(rs):5.0%}"
              f"  结构 v1.1 {sum(r['structural']['v1.1'] for r in cx)}/{len(cx)}  v1.2 {sum(r['structural']['v1.2'] for r in cx)}/{len(cx)}"
              f"  声明domain {sum(bool(r.get('declared_domain')) for r in cx)}/{len(cx)}")
    print("\n各断言通过数（unguided / g11 / g12）")
    keys = []
    for r in rows:
        for k in r.get("semantic") or {}:
            if (r["task"], k) not in keys:
                keys.append((r["task"], k))
    for tid, k in keys:
        cells = []
        for c in CONDS:
            rs = [r for r in rows if r["condition"] == c and r["task"] == tid]
            cells.append(f"{sum(bool((r.get('semantic') or {}).get(k)) for r in rs)}/{len(rs)}")
        print(f"  {tid} {k:28s} " + "  ".join(cells))
    print()
    for r in rows:
        fails = [k for k, v in (r.get("semantic") or {}).items() if not v]
        print(f"{r['file']:26s} mode={r.get('mode','?'):16s} 语义 {r['semantic_rate']:4.0%} 结构 {r['structural']} 未过 {fails or '—'}{' ' + r['error'] if r.get('error') else ''}")
    (target / "评分结果v0.3.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] == "calibrate":
        sys.exit(cmd_calibrate())
    if sys.argv[1] == "report":
        cmd_report(Path(sys.argv[2]))
