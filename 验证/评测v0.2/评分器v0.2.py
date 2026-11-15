#!/usr/bin/env python3
"""图工程架构师 Plus 评测 v0.2 评分器（零依赖）。断言在任何运行之前写定（2026-11-15）。

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
  python3 评分器v0.2.py calibrate          标准答案必须 100% 通过、朴素基线必须 100% 不通过
  python3 评分器v0.2.py grade <文件或目录>  打分；目录内文件名形如 guided-t1-r1-v0.1.json
  python3 评分器v0.2.py report <目录>        汇总 unguided vs guided 的通过率与提升
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
TASKS = {t["id"]: t for t in json.loads((HERE / "评测任务v0.2.json").read_text(encoding="utf-8"))["tasks"]}
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


# ---------- 语义断言（v0.2；每个任务的陷阱在题面不点名） ----------
def rules_text(g):
    return txt((g.get("permissions") or {}).get("forbidden_actions", [])) + txt(g.get("frozen_rules", []))


def success_text(g):
    rg = g.get("root_goal") or {}
    return txt(rg.get("observable_success", "")) + txt(rg.get("statement", ""))


def captured(g):
    opt_ids = {n.get("id") for n in optimizers(g)}
    guard_ids = {n.get("id") for n in nodes(g) if n.get("kind") in VERIFY_KINDS | {"anchor", "human_gate", "governance_loop", "arbitration"}}
    return any(e.get("from") in opt_ids and e.get("to") in guard_ids and e.get("relation") in {"revises", "constrains"} for e in edges(g))


def verify_nodes_matching(g, kinds, *patterns):
    return [n for n in by_kind(g, kinds) if all(re.search(p, txt(n), re.I) for p in patterns)]


def sem_t7(g):
    anchors = anchor_blobs(g)
    oot = r"时间外|前瞻|未来|下一?个?月|之后|后续|temporal|prospective|out.?of.?time|外部验证|external|silent|影子|shadow|留出|holdout|held.?out"
    return {
        "有训练窗口之外的验证锚点": any(re.search(oot, a[1], re.I) for a in anchors),
        "禁止用训练同月数据验收或自动替换": bool(re.search(r"同(一|月|期)|自动(替换|上线|部署)|auto.?(deploy|replace|promot)", rules_text(g), re.I)),
        "有校准/漂移/亚组反指标": any_node_matches(g, {"counter_metric_loop", "audit_loop"},
                                       r"校准|calibrat|漂移|drift|亚组|subgroup|公平|fair|ppv|分布"),
        "替换线上模型须人工门": gate_or_forbidden(g, r"替换|上线|部署|deploy|发布|切换|replace|promot"),
        "成功标准不只是 AUC 上涨": bool(re.search(r"校准|calibrat|临床|净获益|外部|前瞻|时间外|稳健|ppv|亚组|安全|out.?of.?time", success_text(g), re.I)),
    }


def sem_t8(g):
    anchors = anchor_blobs(g)
    weaken = (r"(删|改|修改|弱化|跳过|禁用|skip|modify|delete|disable|weaken|xfail|编辑).{0,12}(既有|原有|已有|现有|冻结)?.{0,4}(测试|test|断言|assert)"
              r"|(既有|原有|已有|现有|冻结).{0,6}(测试|test).{0,12}(只读|不可|不得|禁止|冻结|read.?only)")
    return {
        "既有测试作为冻结锚点": any(re.search(r"测试|test", a[1], re.I) for a in anchors),
        "禁止修复者删改/弱化既有测试": bool(re.search(weaken, rules_text(g), re.I)),
        "新增测试由独立方审查": bool(verify_nodes_matching(g, VERIFY_KINDS | {"human_gate"},
                                              r"新增?测试|新测试|测试(审查|评审|变更|有效)|new test|test.?(review|change|quality)|变异|mutation")),
        "合并主分支须人工门": gate_or_forbidden(g, r"合并|merge|主分支|main"),
        "修复者不能改裁判": not captured(g),
    }


def sem_t9(g):
    anchors = anchor_blobs(g)
    stale = (r"(标准|指南|guideline|standard).{0,24}(复审|更新|过期|时效|过时|陈旧|版本|重新(确认|审)|outdated|stale|review|现行)"
             r"|(复审|更新|过期|时效|过时|陈旧|outdated|stale|现行).{0,24}(标准|指南|guideline|standard)")
    return {
        "锚点包含真实结局": any(re.search(r"结局|outcome|确诊|最终诊断|acs|心梗|肌钙蛋白|troponin|随访|造影|mace", a[1], re.I) for a in anchors),
        "三年前标准需复审/时效检查": bool(re.search(stale, txt(g), re.I)),
        "有防低估分级反指标": any_node_matches(g, {"counter_metric_loop", "audit_loop"},
                                     r"漏诊|低估|降级|under.?triag|假阴性|false.?negative|高危.{0,6}(漏|低)|安全"),
        "上线预检台须人工门": gate_or_forbidden(g, r"上线|部署|启用|deploy|预检|投入使用|release"),
        "一致率不是唯一成功标准": bool(re.search(r"结局|outcome|漏诊|低估|安全|under|患者|不良|延误|高危", success_text(g), re.I)),
    }


def sem_t10(g):
    t = txt(g)
    opts = optimizers(g)
    arb_ids = {n.get("id") for n in by_kind(g, {"arbitration", "human_gate"})}
    both_route = len(opts) >= 2 and all(any(e.get("from") == o.get("id") and e.get("to") in arb_ids for e in edges(g)) for o in opts)
    return {
        "有仲裁与优先级": bool(by_kind(g, {"arbitration"})) or bool(re.search(r"priority_policy", t)),
        "两个指标都被跟踪": bool(re.search(r"滞留|停留|los|length.?of.?stay", t, re.I)) and bool(re.search(r"返诊|revisit|return|再就诊|bounce", t, re.I)),
        "有病人安全反指标": any_node_matches(g, {"counter_metric_loop", "audit_loop"},
                                    r"死亡|不良|adverse|安全|mortality|再入院|icu|恶化|safety|harm"),
        "变更须人工门": gate_or_forbidden(g, r"出院标准|流程|变更|上线|实施|发布|change|deploy|policy"),
        "Agent 不能单独改共享标准": both_route or bool(re.search(
            r"(各自|单独|直接|独立|擅自|unilateral|directly).{0,20}(修改|调整|改|变更|change|modif)|未经.{0,12}(仲裁|批准|审批|委员会|主任|approval)", rules_text(g), re.I)),
    }


def sem_t11(g):
    anchors = anchor_blobs(g)
    src = r"原文|全文|pdf|original|full.?text|文献"
    return {
        "复核者独立从原文提取": bool(verify_nodes_matching(g, VERIFY_KINDS | {"execution", "execution_loop"},
                                               r"独立|independent|双人|double|重新提取|二次提取|re.?extract|背对背|blind", src)),
        "锚点是原始文献": any(re.search(src + r"|注册|registry", a[1], re.I) for a in anchors),
        "不一致有裁决": bool(by_kind(g, {"arbitration"})) or bool(re.search(r"分歧|不一致|discrepan|disagree|仲裁|arbitrat|第三(人|方|名)|adjudicat", txt(g), re.I)),
        "有偏倚/异质性审计": any_node_matches(g, VERIFY_KINDS | {"arbitration"},
                                     r"偏倚|bias|异质|heterogen|发表偏倚|publication|敏感性分析|sensitivity|grade|rob|质量评价"),
        "写入论文前有人工门": gate_or_forbidden(g, r"论文|写入|投稿|manuscript|paper|submi|发表|稿"),
    }


SEM = {"t7": sem_t7, "t8": sem_t8, "t9": sem_t9, "t10": sem_t10, "t11": sem_t11}


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
    files = sorted(p for p in target.glob("*.json") if re.match(r"(un)?guided-", p.name)) if target.is_dir() else [target]
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
    (target / "评分结果v0.2.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


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
