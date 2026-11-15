#!/usr/bin/env python3
"""Graph Engineering Architect Plus v1.1 — single-file, dependency-free CLI.

Subcommands
  classify  <brief.json>                      choose direct/loop/linear_workflow/graph/graph_plus_loop/blocked
  validate  <graph-spec.json> [--json]        structural + control-architecture checks (errors block, warnings advise)
  diagnose  <graph-spec.json> [--today YYYY-MM-DD] [--run run-log.json] [--json]
                                              find the five failure patterns and propose the smallest repair
  mermaid   <graph-spec.json>                 print a Mermaid flowchart of the graph
  simulate  <graph-spec.json> [--fail-node ID] topological batch simulation (no agents, no network, no model)
  init      <root-outcome> --root DIR [--slug S] scaffold .graph/<slug>/ (graph.json, graph-spec.md, validation-report.md, handoff.md)

v1.1: also reads the ORIGINAL graph-engineering-architect schema (version: 1, graph_id, classification, governance,
verification) through an adapter, enforces the original's own rules, and adds cadence / meta-capture / decorative checks.

Acknowledgement: design ideas inspired by Anita Yin's graph-engineering-architect; spec field names kept
compatible with graph-engineering-agent-builder 1.0; invariants (bounded cycles, single writer,
gate-before-side-effect, reach END) from luxiaolei/graph-engineering (Apache-2.0).
Structural validation never proves domain truth, anchor independence in the real world, or completion.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

VERSION = "1.1"
MODES = {"direct", "loop", "linear_workflow", "graph", "graph_plus_loop", "blocked"}
STATES = {"designed", "awaiting_approval", "ready", "executing", "blocked", "failed", "completed", "budget_exhausted"}
NODE_KINDS = {
    "execution", "execution_loop", "verification_loop", "counter_metric_loop", "audit_loop", "arbitration",
    "governance_loop", "anchor", "human_gate", "stop_handoff", "reducer", "synthesis",
}
RELATIONS = {"feeds", "observes", "verifies", "constrains", "vetoes", "escalates", "arbitrates", "revises", "anchors", "hands_off"}
EXECUTORS = {"execution", "execution_loop", "synthesis", "reducer"}
CHECKERS = {"verification_loop", "counter_metric_loop", "audit_loop"}
LOOP_KINDS = {"execution_loop", "verification_loop", "counter_metric_loop", "audit_loop", "governance_loop"}
SIDE_EFFECT_LEVELS = {"none", "internal-reversible", "high-risk"}
# relations through which one node can change what another node holds as truth
MUTATING = {"feeds", "revises"}
FEEDBACK = {"observes", "revises"}


# ----------------------------------------------------------------------------- helpers
def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("top-level JSON must be an object")
    return data


def s(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def as_list(v: Any) -> list:
    return v if isinstance(v, list) else []


class Findings:
    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def add(self, level: str, code: str, msg: str, repair: str = "") -> None:
        self.items.append({"level": level, "code": code, "message": msg, "repair": repair})

    def err(self, code: str, msg: str, repair: str = "") -> None:
        self.add("error", code, msg, repair)

    def warn(self, code: str, msg: str, repair: str = "") -> None:
        self.add("warning", code, msg, repair)

    @property
    def errors(self) -> list[dict[str, str]]:
        return [i for i in self.items if i["level"] == "error"]


class Graph:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.nodes = {n["id"]: n for n in as_list(spec.get("nodes")) if isinstance(n, dict) and s(n.get("id"))}
        self.edges = [e for e in as_list(spec.get("edges")) if isinstance(e, dict)]
        self.out: dict[str, list[dict]] = defaultdict(list)
        self.inc: dict[str, list[dict]] = defaultdict(list)
        for e in self.edges:
            if e.get("from") in self.nodes and e.get("to") in self.nodes:
                self.out[e["from"]].append(e)
                self.inc[e["to"]].append(e)

    def kind(self, nid: str) -> str:
        return self.nodes.get(nid, {}).get("kind", "")

    def of_kind(self, *kinds: str) -> list[str]:
        return [i for i, n in self.nodes.items() if n.get("kind") in kinds]

    def descendants(self, start: str, relations: set[str] | None = None) -> set[str]:
        seen, q = set(), deque([start])
        while q:
            cur = q.popleft()
            for e in self.out[cur]:
                if relations and e.get("relation") not in relations:
                    continue
                if e["to"] not in seen:
                    seen.add(e["to"])
                    q.append(e["to"])
        return seen

    def ancestors(self, start: str, relations: set[str] | None = None) -> set[str]:
        seen, q = set(), deque([start])
        while q:
            cur = q.popleft()
            for e in self.inc[cur]:
                if relations and e.get("relation") not in relations:
                    continue
                if e["from"] not in seen:
                    seen.add(e["from"])
                    q.append(e["from"])
        return seen

    def sccs(self) -> list[list[str]]:
        """Tarjan; returns strongly connected components with a real cycle."""
        index, low, on, stack, out, counter = {}, {}, set(), [], [], [0]

        def visit(v: str) -> None:
            index[v] = low[v] = counter[0]
            counter[0] += 1
            stack.append(v)
            on.add(v)
            for e in self.out[v]:
                w = e["to"]
                if w not in index:
                    visit(w)
                    low[v] = min(low[v], low[w])
                elif w in on:
                    low[v] = min(low[v], index[w])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1 or any(e["to"] == v for e in self.out[v]):
                    out.append(sorted(comp))

        sys.setrecursionlimit(10000)
        for v in self.nodes:
            if v not in index:
                visit(v)
        return out

    def sources_of(self, nid: str) -> set[str]:
        return set(as_list(self.nodes.get(nid, {}).get("evidence_sources")))



# ----------------------------------------------------------------------------- original-schema adapter
CADENCE_TIERS = {"fast": 1, "medium": 2, "slow": 3, "governance": 4, "human": 5}
_CADENCE_WORDS = [
    (5, ("human", "人工", "owner decision")),
    (4, ("quarter", "annual", "year", "季度", "年度", "governance", "治理")),
    (3, ("month", "weekly", "week", "月", "周")),
    (2, ("daily", "day", "release", "per candidate", "per release", "日", "每版", "每个候选")),
    (1, ("per revision", "per iteration", "per step", "continuous", "real-time", "每次迭代", "每轮", "实时")),
]


def cadence_rank(node: dict[str, Any]) -> int | None:
    tier = node.get("cadence_tier")
    if tier in CADENCE_TIERS:
        return CADENCE_TIERS[tier]
    c = str(node.get("cadence", "")).lower()
    if not c:
        return None
    for rank, words in _CADENCE_WORDS:
        if any(w in c for w in words):
            return rank
    return None


def is_original(spec: dict[str, Any]) -> bool:
    return spec.get("version") == 1 and "graph_id" in spec and "schema_version" not in spec


def normalize(spec: dict[str, Any]) -> dict[str, Any]:
    """Map the original graph-engineering-architect schema onto the internal one. Non-destructive."""
    if not is_original(spec):
        return spec
    rg = spec.get("root_goal") if isinstance(spec.get("root_goal"), dict) else {}
    gov = spec.get("governance") if isinstance(spec.get("governance"), dict) else {}
    stops = gov.get("stop_conditions") if isinstance(gov.get("stop_conditions"), dict) else {}
    nodes = []
    for n in as_list(spec.get("nodes")):
        if not isinstance(n, dict):
            continue
        m = dict(n)
        m.setdefault("contract", {"inputs": as_list(n.get("inputs")), "outputs": as_list(n.get("outputs"))})
        if m.get("kind") == "verification_loop":
            m.setdefault("context_scope", "fresh-independent" if s((spec.get("verification") or {}).get("independence_statement")) else "")
        nodes.append(m)
    anchors = [dict(a, evidence_form=a.get("evidence_form", a.get("evidence"))) for a in as_list(spec.get("anchors")) if isinstance(a, dict)]
    owner = rg.get("owner", "")
    approval = spec.get("approval") if isinstance(spec.get("approval"), dict) else {"status": "pending"}
    return {
        "schema_version": "1.0",
        "_original": True,
        "title": spec.get("graph_id"),
        "mode": (spec.get("classification") or {}).get("mode", "graph"),
        "state": spec.get("state", "designed"),
        "root_goal": {"statement": rg.get("statement"), "human_owner": owner,
                      "observable_success": rg.get("success_definition"), "metrics": as_list(rg.get("metrics"))},
        "permissions": {"human_owner": owner, "allowed_actions": [], "forbidden_actions": as_list(rg.get("out_of_scope"))},
        "frozen_rules": as_list(gov.get("frozen_items")),
        "approval": approval,
        "budget": spec.get("budget") or {"max_agents": max(1, len(nodes)), "max_concurrency": 1, "max_retries": 0, "max_cost_units": 1},
        "failure_policy": {k: v for k, v in stops.items() if k != "success"} or {},
        "stop_handoff": {"owner": owner, "conditions": [v for v in stops.values() if s(v)], "artifact": "terminal handoff"},
        "execution_contract": spec.get("execution_contract") or {"external_execution": False},
        "governance": gov,
        "verification": spec.get("verification"),
        "external_inputs": as_list(spec.get("external_inputs")),
        "anchors": anchors,
        "nodes": nodes,
        "edges": as_list(spec.get("edges")),
    }


def original_rules(spec: dict[str, Any], f: Findings) -> None:
    """The original validate_graph.py rules, kept so an original-format graph is judged by its own standard too."""
    for k in ("version", "graph_id", "classification", "root_goal", "nodes", "edges", "anchors", "governance", "verification"):
        if k not in spec:
            f.err("O-FIELD", f"original schema: {k} is required")
    cl = spec.get("classification") if isinstance(spec.get("classification"), dict) else {}
    if not s(cl.get("rationale")):
        f.err("O-RATIONALE", "classification.rationale must explain why a graph is justified")
    rg = spec.get("root_goal") if isinstance(spec.get("root_goal"), dict) else {}
    if not as_list(rg.get("out_of_scope")):
        f.err("O-SCOPE", "root_goal.out_of_scope must be a non-empty list")
    for i, n in enumerate(as_list(spec.get("nodes"))):
        if isinstance(n, dict) and not s(n.get("cadence")):
            f.err("O-CADENCE", f"nodes[{i}] ({n.get('id')}): cadence is required")
    gov = spec.get("governance") if isinstance(spec.get("governance"), dict) else {}
    arb = gov.get("arbitration") if isinstance(gov.get("arbitration"), dict) else {}
    if not (s(arb.get("owner")) and s(arb.get("priority_policy"))):
        f.err("O-ARB", "governance.arbitration needs owner and priority_policy")
    if gov.get("goal_change") != "human_approval":
        f.err("O-GOAL", "governance.goal_change must be human_approval")
    if not as_list(gov.get("approval_required")):
        f.err("O-APPROVALREQ", "governance.approval_required must be a non-empty list")
    st = gov.get("stop_conditions") if isinstance(gov.get("stop_conditions"), dict) else {}
    for k in ("success", "failed", "blocked", "budget_exhausted"):
        if not s(st.get(k)):
            f.err("O-STOP", f"governance.stop_conditions.{k} is required")
    ver = spec.get("verification") if isinstance(spec.get("verification"), dict) else {}
    if not s(ver.get("independence_statement")):
        f.err("O-INDEP", "verification.independence_statement is required")
    kinds = {n.get("id"): n.get("kind") for n in as_list(spec.get("nodes")) if isinstance(n, dict)}
    checks = as_list(ver.get("checks"))
    if not checks:
        f.err("O-CHECKS", "verification.checks must be a non-empty list")
    for i, c in enumerate(checks):
        if not isinstance(c, dict) or kinds.get(c.get("verifier_node")) != "verification_loop":
            f.err("O-CHECKS", f"verification.checks[{i}].verifier_node must reference a verification_loop")
        elif not all(s(c.get(k)) for k in ("criterion", "evidence", "failure_signal")):
            f.err("O-CHECKS", f"verification.checks[{i}] needs criterion, evidence, failure_signal")


def placeholder_check(spec: Any, f: Findings, path: str = "") -> None:
    """Reject scaffolding left in place (original rule: any TODO is not meaningful)."""
    if isinstance(spec, dict):
        for k, v in spec.items():
            placeholder_check(v, f, f"{path}.{k}" if path else k)
    elif isinstance(spec, list):
        for i, v in enumerate(spec):
            placeholder_check(v, f, f"{path}[{i}]")
    elif isinstance(spec, str) and ("TODO" in spec.upper() or "待实例化" in spec or "待用户指定" in spec):
        f.err("E-PLACEHOLDER", f"{path} still holds a placeholder: {spec[:40]!r}", "the human owner fills this before review")


# ----------------------------------------------------------------------------- classify
def classify(brief: dict[str, Any]) -> dict[str, str]:
    rg = brief.get("root_goal") if isinstance(brief.get("root_goal"), dict) else {}
    sig = brief.get("signals") if isinstance(brief.get("signals"), dict) else {}
    missing = [k for k in ("statement", "human_owner", "observable_success") if not s(rg.get(k))]
    if missing:
        return {"mode": "blocked", "why": f"root_goal missing {', '.join(missing)}; humans own the goal, do not guess"}
    if not sig.get("task_clear"):
        return {"mode": "blocked", "why": "task not clear; ask the owner before designing"}
    if not sig.get("reality_anchor_available", True):
        return {"mode": "blocked", "why": "no evidence source the executor cannot rewrite; define one first"}
    if sig.get("single_bounded_action") and not sig.get("requires_iteration"):
        return {"mode": "direct", "why": "one bounded action; governance costs more than it saves"}
    gameable = sig.get("metric_gameable") or sig.get("conflicting_objectives")
    independent = sig.get("independent_responsibilities") and sig.get("requires_independent_verification")
    if sig.get("interacting_loops") or (independent and gameable):
        mode = "graph_plus_loop" if sig.get("requires_iteration") else "graph"
        return {"mode": mode, "why": "several control responsibilities interact or the metric can be gamed"}
    if independent:
        return {"mode": "graph", "why": "two truly independent responsibilities plus independent verification"}
    if sig.get("requires_iteration"):
        return {"mode": "loop", "why": "one objective, one trusted verifier, bounded retries"}
    if sig.get("sequential_dependencies"):
        return {"mode": "linear_workflow", "why": "steps depend on each other but nothing checks or vetoes anything"}
    return {"mode": "direct", "why": "no interacting control responsibility found"}


# ----------------------------------------------------------------------------- validate
def validate(raw: dict[str, Any]) -> Findings:
    f = Findings()
    placeholder_check(raw, f)
    if is_original(raw):
        original_rules(raw, f)
    spec = normalize(raw)
    g = Graph(spec)
    mode, state = spec.get("mode"), spec.get("state")

    # --- envelope (agent-builder 1.0 compatible field names)
    if spec.get("schema_version") not in {"1.0", "1.1"}:
        f.err("E-SCHEMA", "schema_version must be 1.0 or 1.1 (or use the original version:1 schema)")
    if not s(spec.get("title")):
        f.err("E-TITLE", "title is required")
    if mode not in MODES:
        f.err("E-MODE", f"mode must be one of {sorted(MODES)}")
    if state not in STATES:
        f.err("E-STATE", f"state must be one of {sorted(STATES)}")
    rg = spec.get("root_goal")
    if not (isinstance(rg, dict) and all(s(rg.get(k)) for k in ("statement", "human_owner", "observable_success"))):
        f.err("E-ROOT", "root_goal needs statement, human_owner, observable_success", "the human owner writes these")

    # --- nodes
    raw_nodes = as_list(spec.get("nodes"))
    if not raw_nodes:
        f.err("E-NODES", "nodes must be a non-empty list")
    seen = set()
    for i, n in enumerate(raw_nodes):
        if not isinstance(n, dict) or not s(n.get("id")):
            f.err("E-NODE", f"nodes[{i}] needs an id")
            continue
        nid = n["id"]
        if nid in seen:
            f.err("E-DUP", f"duplicate node id {nid}")
        seen.add(nid)
        if n.get("kind") not in NODE_KINDS:
            f.err("E-KIND", f"{nid}: kind must be one of {sorted(NODE_KINDS)}")
        for k in ("responsibility", "owner"):
            if not s(n.get(k)):
                f.err("E-NODEFIELD", f"{nid}: {k} is required")
        c = n.get("contract")
        if not (isinstance(c, dict) and all(as_list(c.get(k)) and all(s(x) for x in c[k]) for k in ("inputs", "outputs"))):
            f.err("E-CONTRACT", f"{nid}: contract.inputs and contract.outputs must be non-empty string lists")
        se = n.get("side_effect", "none")
        if se not in SIDE_EFFECT_LEVELS:
            f.err("E-SIDEEFFECT", f"{nid}: side_effect must be none / internal-reversible / high-risk")
        if n.get("kind") in LOOP_KINDS and n.get("kind") != "governance_loop":
            mi = n.get("max_iterations")
            if not (isinstance(mi, int) and not isinstance(mi, bool) and mi >= 1):
                (f.err if spec.get("schema_version") == "1.1" else f.warn)("E-LOOPBOUND" if spec.get("schema_version") == "1.1" else "W-LOOPBOUND", f"{nid}: loop node needs integer max_iterations >= 1", "add max_iterations (2-3 is typical)")

    # --- edges
    for i, e in enumerate(g.edges):
        if e.get("from") not in g.nodes or e.get("to") not in g.nodes:
            f.err("E-EDGEREF", f"edges[{i}] references an unknown node")
        if e.get("relation") not in RELATIONS:
            f.err("E-REL", f"edges[{i}] relation must be one of {sorted(RELATIONS)} (vague 'collaborates' is not a control contract)")
        if not s(e.get("artifact")):
            f.err("E-ARTIFACT", f"edges[{i}] must name the artifact or evidence it carries")
        if e.get("from") == e.get("to"):
            f.err("E-SELF", f"edges[{i}] is a self-loop; put iteration inside the node with max_iterations")

    # --- governance envelope
    perms = spec.get("permissions")
    if not (isinstance(perms, dict) and s(perms.get("human_owner"))):
        f.err("E-PERM", "permissions.human_owner is required")
    elif set(as_list(perms.get("allowed_actions"))) & set(as_list(perms.get("forbidden_actions"))):
        f.err("E-PERMCONFLICT", "allowed_actions and forbidden_actions overlap")
    if not (as_list(spec.get("frozen_rules")) and all(s(x) for x in spec["frozen_rules"])):
        f.err("E-FROZEN", "frozen_rules must be a non-empty list")
    b = spec.get("budget") if isinstance(spec.get("budget"), dict) else {}
    for k in ("max_agents", "max_concurrency", "max_cost_units"):
        if not (isinstance(b.get(k), int) and b[k] > 0):
            f.err("E-BUDGET", f"budget.{k} must be a positive integer")
    if isinstance(b.get("max_agents"), int) and isinstance(b.get("max_concurrency"), int) and b["max_concurrency"] > b["max_agents"]:
        f.err("E-BUDGET", "max_concurrency cannot exceed max_agents")
    if not (isinstance(b.get("max_retries"), int) and b["max_retries"] >= 0):
        f.err("E-BUDGET", "budget.max_retries must be a non-negative integer")
    ap = spec.get("approval") if isinstance(spec.get("approval"), dict) else {}
    if ap.get("status") not in {"pending", "approved", "rejected"}:
        f.err("E-APPROVAL", "approval.status must be pending / approved / rejected")
    if state in {"ready", "executing", "completed"} and not (ap.get("status") == "approved" and s(ap.get("approved_by"))):
        f.err("E-APPROVAL", f"state {state} requires a human approval with approved_by")
    if ap.get("status") == "rejected" and state != "blocked":
        f.err("E-APPROVAL", "rejected approval means state must be blocked")
    ec = spec.get("execution_contract") if isinstance(spec.get("execution_contract"), dict) else {}
    if not isinstance(ec.get("external_execution"), bool):
        f.err("E-EXEC", "execution_contract.external_execution must be boolean (default false)")
    if state == "executing" and ec.get("external_execution") is not True:
        f.err("E-EXEC", "executing requires explicit external_execution=true for an authorised scope")
    if not (isinstance(spec.get("failure_policy"), dict) and spec["failure_policy"]):
        f.err("E-FAIL", "failure_policy is required")
    sh = spec.get("stop_handoff") if isinstance(spec.get("stop_handoff"), dict) else {}
    if not (s(sh.get("owner")) and as_list(sh.get("conditions")) and s(sh.get("artifact"))):
        f.err("E-HANDOFF", "stop_handoff needs owner, conditions, artifact")
    if not g.of_kind("human_gate"):
        f.err("E-GATE", "a human_gate node is required")
    if not g.of_kind("stop_handoff"):
        f.err("E-STOP", "a stop_handoff node is required")
    if state == "completed" and not as_list(spec.get("reality_evidence")):
        f.err("E-DONE", "completed needs reality_evidence; agent agreement is not completion")

    if mode in {"graph", "graph_plus_loop"}:
        graph_checks(g, spec, f)
        governance_checks(g, spec, f)
    common_topology_checks(g, spec, f)
    return f


def governance_checks(g: Graph, spec: dict[str, Any], f: Findings) -> None:
    """v1.1: rules distilled from the original graph-model.md and patterns-and-failures.md."""
    kinds = {n.get("kind") for n in g.nodes.values()}
    # minimum grounded graph: a counter-metric or audit loop, and at least two loop kinds
    if not kinds & {"counter_metric_loop", "audit_loop"}:
        f.err("E-NOCOUNTER", "graph has no counter_metric_loop or audit_loop; cheap wins go unseen",
              "add a counter-metric paired with the executor's proxy (e.g. throughput <-> reproducibility)")
    if len(kinds & LOOP_KINDS) < 2:
        f.err("E-ONELOOP", "fewer than two loop kinds; this is a single loop, not a graph", "reclassify as loop or add the missing responsibility")
    # decorative graph: no edge carries authority
    if not any(e.get("relation") in {"constrains", "vetoes", "escalates", "arbitrates"} for e in g.edges):
        f.err("E-DECORATIVE", "no edge constrains, vetoes, escalates or arbitrates; arrows without authority",
              "collapse duplicate nodes and name the authority each remaining edge carries")
    # meta-loop capture: non-human nodes revising the machinery that judges them
    protected = {"verification_loop", "anchor", "governance_loop", "human_gate", "audit_loop", "counter_metric_loop"}
    for e in g.edges:
        src, dst = g.kind(e.get("from", "")), g.kind(e.get("to", ""))
        if e.get("relation") in {"revises", "constrains"} and src in EXECUTORS and dst in protected:
            f.err("E-METACAPTURE", f"{e['from']} ({src}) {e['relation']} {e['to']} ({dst}): the improver can rewrite its own judge",
                  "route the proposed change through a human_gate; executors may only propose")
        if e.get("relation") == "revises" and dst == "governance_loop" and src != "human_gate":
            f.err("E-METACAPTURE", f"{e['from']} revises governance loop {e['to']}; only a human gate may change targets")
    # cadence separation: a faster loop must not revise or constrain a slower one's variables
    for e in g.edges:
        if e.get("relation") not in {"revises", "constrains"}:
            continue
        a, b = g.nodes.get(e.get("from"), {}), g.nodes.get(e.get("to"), {})
        ra, rb = cadence_rank(a), cadence_rank(b)
        if ra is not None and rb is not None and ra < rb and a.get("kind") not in {"human_gate", "arbitration"} \
                and a.get("kind") not in CHECKERS:
            f.err("E-CADENCE", f"{e['from']} (faster) {e['relation']} {e['to']} (slower): fast loop thrashing a slow variable",
                  "let the fast loop feed/escalate; give the change to the slower owner with a minimum observation window")
    # arbitration policy declared before conflicts
    checkers = g.of_kind(*CHECKERS)
    gov = spec.get("governance") if isinstance(spec.get("governance"), dict) else {}
    arb = gov.get("arbitration") if isinstance(gov.get("arbitration"), dict) else {}
    if len(checkers) >= 2 and not s(arb.get("priority_policy")) and not any(
            s(n.get("priority_policy")) for n in g.nodes.values() if n.get("kind") == "arbitration"):
        f.warn("W-PRIORITY", "several checkers but no declared priority_policy; arbitration will be ad hoc",
               "write governance.arbitration.priority_policy (e.g. 'safety > accuracy > speed')")
    # watcher theater: verifier whose only incoming artefacts come from the executor it checks
    for v in g.of_kind("verification_loop"):
        froms = {e["from"] for e in g.inc[v]}
        if froms and all(g.kind(x) in EXECUTORS for x in froms) and not g.sources_of(v):
            f.err("E-THEATER", f"{v} only receives what the executor hands it; it can just restate the executor's report",
                  "give it independently produced evidence (anchor edge, own sample, executed tests)")
    # verification.checks must name real verifiers
    ver = spec.get("verification") if isinstance(spec.get("verification"), dict) else {}
    for i, c in enumerate(as_list(ver.get("checks"))):
        if isinstance(c, dict) and g.kind(c.get("verifier_node", "")) != "verification_loop":
            f.err("E-CHECKREF", f"verification.checks[{i}] names {c.get('verifier_node')!r}, which is not a verification_loop")


def graph_checks(g: Graph, spec: dict[str, Any], f: Findings) -> None:
    verifiers = g.of_kind("verification_loop")
    anchors_nodes = set(g.of_kind("anchor"))
    if not verifiers:
        f.err("E-VERIFIER", "graph mode needs a verification_loop")
    for v in verifiers:
        if g.nodes[v].get("context_scope") != "fresh-independent":
            f.err("E-INDEP", f"{v}: verifier must use context_scope=fresh-independent")
    if not anchors_nodes:
        f.err("E-ANCHOR", "graph mode needs an anchor node")
    anchors = [a for a in as_list(spec.get("anchors")) if isinstance(a, dict)]
    good = [a for a in anchors if a.get("node_id") in anchors_nodes and a.get("frozen") is True
            and all(s(a.get(k)) for k in ("source", "evidence_form", "owner", "freshness_rule"))]
    if not good:
        f.err("E-ANCHOR", "need at least one complete frozen anchor (node_id, source, evidence_form, owner, freshness_rule, frozen:true)")
    if not any(e.get("relation") == "anchors" and e.get("from") in anchors_nodes for e in g.edges):
        f.err("E-ANCHOR", "need an 'anchors' edge leaving an anchor node")

    # NEW 1: anchor write-protection — nothing the executors produce may flow into an anchor
    for a in anchors_nodes:
        for e in g.inc[a]:
            if g.kind(e["from"]) != "human_gate":
                f.err("E-ANCHORWRITE", f"{e['from']} -> {a} ({e.get('relation')}): only a human_gate may touch an anchor",
                      "remove the edge or route the change through the human gate")
    # NEW 2: every anchors edge must land on a checker (or arbitration/human), not on the executor it should judge
    for e in g.edges:
        if e.get("relation") == "anchors" and g.kind(e.get("to", "")) in EXECUTORS and not any(
                x.get("relation") == "anchors" and g.kind(x["to"]) in CHECKERS for x in g.out[e["from"]]):
            f.warn("W-ANCHORTARGET", f"anchor {e['from']} only informs executor {e['to']}; the verifier must also receive it",
                   "add an anchors edge to the verifier")
    # NEW 3: verifier must receive an anchor and have the power to stop something
    for v in verifiers:
        if not any(e.get("relation") == "anchors" for e in g.inc[v]):
            f.err("E-VNOANCHOR", f"{v}: verifier receives no anchor; it can only re-read the executor's view",
                  "add anchors edge from a frozen anchor")
        if not any(e.get("relation") in {"constrains", "vetoes", "escalates"} for e in g.out[v]):
            f.err("E-VNOTEETH", f"{v}: verifier has no constrains/vetoes/escalates edge, so its verdict changes nothing",
                  "add a vetoes or constrains edge to the next stage")
    # NEW 4: owner independence
    for v in verifiers:
        checked = {e["from"] for e in g.inc[v] if e.get("relation") in {"feeds", "verifies"}}
        same = [c for c in checked if g.nodes[c].get("owner") == g.nodes[v].get("owner")]
        if same:
            f.err("E-SAMEOWNER", f"{v} shares an owner with {same}; a maker cannot grade itself")
    # NEW 5: circular confirmation through shared evidence sources
    for v in verifiers:
        vs = g.sources_of(v)
        if not vs:
            f.warn("W-NOSOURCES", f"{v}: evidence_sources not declared; independence cannot be checked",
                   "list the sources this verifier reads")
            continue
        for e in g.inc[v]:
            if e.get("relation") != "feeds":
                continue
            overlap = vs & g.sources_of(e["from"])
            anchor_srcs = {a.get("source") for a in anchors}
            for an in anchors_nodes:  # sharing the frozen anchor itself is intended
                anchor_srcs |= set(as_list((g.nodes[an].get("contract") or {}).get("outputs")))
            overlap -= anchor_srcs
            if overlap:
                f.err("E-CIRCULAR", f"{v} and {e['from']} both rely on {sorted(overlap)} → mutual confirmation, not verification",
                      "give the verifier a source the executor never saw, or make the shared source a frozen anchor")
    # NEW 6: Goodhart pairing — every optimised metric needs a counter-signal watching it
    for nid, n in g.nodes.items():
        if s(n.get("optimizes")):
            watchers = [e["from"] for e in g.inc[nid] if e.get("relation") in {"observes", "verifies", "vetoes"}
                        and g.kind(e["from"]) in CHECKERS]
            watchers += [e["to"] for e in g.out[nid] if e.get("relation") in {"feeds", "observes"}
                         and g.kind(e["to"]) in {"counter_metric_loop", "audit_loop"}]
            if not any(g.kind(w) in {"counter_metric_loop", "audit_loop"} for w in watchers):
                f.err("E-GOODHART", f"{nid} optimises '{n['optimizes']}' with no counter_metric_loop/audit_loop watching it",
                      "add a counter-metric node that observes the same output with a metric it cannot game")
    # NEW 7: conflicts need an arbiter
    checkers = g.of_kind(*CHECKERS)
    if len(checkers) >= 2 and not g.of_kind("arbitration", "human_gate"):
        f.err("E-ARBITER", "two or more checkers but no arbitration/human_gate to settle conflicts")


def common_topology_checks(g: Graph, spec: dict[str, Any], f: Findings) -> None:
    gates = set(g.of_kind("human_gate"))
    stops = set(g.of_kind("stop_handoff"))
    # NEW 8: high-risk side effects must be dominated by a human gate (an ancestor via constrains)
    for nid, n in g.nodes.items():
        if n.get("side_effect") == "high-risk":
            if not (g.ancestors(nid) & gates):
                f.err("E-GATEFIRST", f"{nid} is high-risk but no human_gate lies upstream of it",
                      "add human_gate -> node (constrains, artifact approval-record)")
            if not any(e["from"] in gates and e.get("relation") == "constrains" for e in g.inc[nid]):
                f.warn("W-GATEDIRECT", f"{nid} is high-risk; prefer a direct constrains edge from the human gate")
    # NEW 9: bounded cycles
    for comp in g.sccs():
        bounded = any(isinstance(g.nodes[c].get("max_iterations"), int) for c in comp)
        exits = any(e["to"] not in comp for c in comp for e in g.out[c])
        if not bounded:
            f.err("E-UNBOUNDED", f"cycle {comp} has no node with max_iterations", "bound the cycle or cut the back edge")
        if not exits:
            f.err("E-TRAP", f"cycle {comp} has no exit edge", "add an escalates/hands_off edge out of the cycle")
    # NEW 10: every non-terminal node can reach stop_handoff
    if stops:
        for nid in g.nodes:
            if nid in stops:
                continue
            if not (g.descendants(nid) & stops) and g.kind(nid) not in {"anchor", "human_gate"}:
                f.err("E-DEADEND", f"{nid} cannot reach a stop_handoff; its result has nowhere to go",
                      "add a hands_off or escalates edge toward stop_handoff")
    # NEW 11: orphan nodes
    for nid in g.nodes:
        if not g.inc[nid] and not g.out[nid]:
            f.err("E-ORPHAN", f"{nid} has no edges")
    # NEW 12: single writer per resource among nodes that could run concurrently
    writers: dict[str, list[str]] = defaultdict(list)
    for nid, n in g.nodes.items():
        for r in as_list(n.get("writes")):
            writers[r].append(nid)
    order = Graph(dict(spec, edges=[e for e in g.edges if e.get("relation") not in FEEDBACK]))
    for r, ws in writers.items():
        for i in range(len(ws)):
            for j in range(i + 1, len(ws)):
                a, b = ws[i], ws[j]
                if b not in order.descendants(a) and a not in order.descendants(b):
                    f.err("E-WRITERS", f"{a} and {b} may write '{r}' in parallel", "serialize them or give each its own resource")
    # NEW 13: join completeness — each declared input must come from an edge artifact or declared external input
    external = set(as_list(spec.get("external_inputs")))
    for nid, n in g.nodes.items():
        c = n.get("contract") if isinstance(n.get("contract"), dict) else {}
        arriving = [str(e.get("artifact", "")).lower() for e in g.inc[nid]]
        ext = [str(x).lower() for x in external]

        def delivered(x: str) -> bool:
            x = str(x).lower()
            return any(x == a or x in a or a in x for a in arriving + ext if a)
        missing = [x for x in as_list(c.get("inputs")) if not delivered(x)]
        if missing and g.kind(nid) not in {"anchor", "human_gate"}:
            f.warn("W-JOIN", f"{nid} expects {missing} but no edge delivers them and they are not external_inputs",
                   "add the edge, or list them under external_inputs")
    # NEW 14: concurrency sanity
    b = spec.get("budget") if isinstance(spec.get("budget"), dict) else {}
    agents = len(g.of_kind(*EXECUTORS, *CHECKERS, "arbitration"))
    if isinstance(b.get("max_agents"), int) and agents > b["max_agents"]:
        f.warn("W-AGENTS", f"{agents} agent-like nodes exceed budget.max_agents={b['max_agents']}; some nodes must share or wait")


# ----------------------------------------------------------------------------- diagnose
REPAIR_LAYER = {  # original repair order: fix the earliest broken layer first
    "wrong_target": 1, "decayed_measurement": 2, "circular_confirmation": 2, "watcher_theater": 3,
    "meta_loop_capture": 3, "metric_gaming": 4, "loop_conflict": 4, "decorative_graph": 4,
    "local_success_global_harm": 4, "cadence_thrashing": 5, "completion_by_consensus": 2,
}
LAYER_NAMES = {1: "root outcome & ownership", 2: "reality anchors & provenance", 3: "verifier independence",
               4: "edge authority & arbitration", 5: "cadence separation", 6: "node implementation"}
PATTERNS = {
    "meta_loop_capture": "the improver can lower thresholds, edit tests or redefine success",
    "decorative_graph": "many arrows, none carry veto, constraint, evidence or escalation",
    "cadence_thrashing": "a fast loop keeps rewriting slow targets or definitions",
    "local_success_global_harm": "each node hits its target while the root outcome is not anchored",
    "watcher_theater": "the verifier only restates the executor's report or sample",
    "completion_by_consensus": "success declared from agreement, without executed evidence",
    "metric_gaming": "a loop is optimising its own score instead of the goal",
    "wrong_target": "the optimised metric is not tied to the root goal's observable success",
    "loop_conflict": "two loops push the same artifact in opposite directions with no arbiter",
    "decayed_measurement": "an anchor or measurement is older than its freshness rule allows",
    "circular_confirmation": "checkers agree because they read the same source, not because it is true",
}


def diagnose(raw: dict[str, Any], today: dt.date, run: dict[str, Any] | None) -> dict[str, Any]:
    spec = normalize(raw)
    g = Graph(spec)
    f = validate(raw)
    hits: list[dict[str, str]] = []
    code_to_pattern = {"E-GOODHART": "metric_gaming", "E-NOCOUNTER": "metric_gaming", "E-CIRCULAR": "circular_confirmation",
                       "E-ARBITER": "loop_conflict", "W-PRIORITY": "loop_conflict", "E-VNOANCHOR": "watcher_theater",
                       "E-THEATER": "watcher_theater", "E-SAMEOWNER": "watcher_theater", "E-ANCHORWRITE": "meta_loop_capture",
                       "E-METACAPTURE": "meta_loop_capture", "E-DECORATIVE": "decorative_graph", "E-VNOTEETH": "decorative_graph",
                       "E-CADENCE": "cadence_thrashing", "E-DONE": "completion_by_consensus"}
    for i in f.items:
        if i["code"] in code_to_pattern:
            hits.append({"pattern": code_to_pattern[i["code"]], "evidence": i["message"], "repair": i["repair"]})
    # wrong target: optimised metric must be named in root goal's tracked metrics
    root_metrics = set(as_list((spec.get("root_goal") or {}).get("metrics")))
    for nid, n in g.nodes.items():
        m = n.get("optimizes")
        if s(m) and root_metrics and m not in root_metrics:
            hits.append({"pattern": "wrong_target", "evidence": f"{nid} optimises '{m}', root goal tracks {sorted(root_metrics)}",
                         "repair": "map the node metric to a root metric or demote it to a diagnostic"})
    # decayed measurement
    for a in as_list(spec.get("anchors")):
        if not isinstance(a, dict):
            continue
        md, lc = a.get("max_age_days"), a.get("last_confirmed")
        if isinstance(md, int) and s(lc):
            try:
                age = (today - dt.date.fromisoformat(lc)).days
            except ValueError:
                hits.append({"pattern": "decayed_measurement", "evidence": f"anchor {a.get('node_id')} last_confirmed not ISO date",
                             "repair": "record last_confirmed as YYYY-MM-DD"})
                continue
            if age > md:
                hits.append({"pattern": "decayed_measurement", "evidence": f"anchor {a.get('node_id')} is {age} days old (limit {md})",
                             "repair": "owner re-confirms the anchor before the next run; block verification until then"})
        elif a.get("frozen"):
            hits.append({"pattern": "decayed_measurement", "evidence": f"anchor {a.get('node_id')} lacks max_age_days/last_confirmed",
                         "repair": "add both so staleness is checkable"})
    # loop conflict: two checkers revising/vetoing the same target with no arbitration edge into it
    by_target: dict[str, list[str]] = defaultdict(list)
    for e in g.edges:
        if e.get("relation") in {"revises", "vetoes", "constrains"} and g.kind(e.get("from", "")) in CHECKERS | {"governance_loop"}:
            by_target[e["to"]].append(e["from"])
    for t, srcs in by_target.items():
        if g.kind(t) in {"human_gate", "arbitration"}:
            continue  # the target itself is the arbiter
        if len(set(srcs)) >= 2 and not any(g.kind(e["from"]) in {"arbitration", "human_gate"} for e in g.inc[t]):
            hits.append({"pattern": "loop_conflict", "evidence": f"{sorted(set(srcs))} all steer {t} with no arbiter on it",
                         "repair": "add arbitration -> target (arbitrates) or a priority rule in frozen_rules"})
    # run-log signals
    if run:
        for r in as_list(run.get("node_results")):
            if not isinstance(r, dict):
                continue
            hist = as_list(r.get("score_history"))
            if len(hist) >= 3 and all(isinstance(x, (int, float)) for x in hist):
                if hist[-1] > hist[0] and r.get("anchor_agreement") is not None and r["anchor_agreement"] < 0.5:
                    hits.append({"pattern": "metric_gaming", "evidence": f"{r.get('node_id')} score rose {hist[0]}→{hist[-1]} while anchor agreement is {r['anchor_agreement']}",
                                 "repair": "freeze the metric, re-check against the anchor, add a counter-metric"})
            if r.get("verifier_agreed_without_anchor"):
                hits.append({"pattern": "circular_confirmation", "evidence": f"{r.get('node_id')} passed with no anchor evidence in the report",
                             "repair": "reject passes that cite no anchor evidence"})
    # local success, global harm: no anchor reaches the terminal path (the root outcome is never re-checked)
    final_path = set(g.of_kind("human_gate", "stop_handoff"))
    gates_fed = any(e.get("relation") in {"anchors", "constrains", "vetoes"} and g.kind(e["from"]) in {"anchor"} | CHECKERS
                    and e["to"] in final_path for e in g.edges)
    if g.of_kind("anchor") and not gates_fed and spec.get("mode") in {"graph", "graph_plus_loop"}:
        hits.append({"pattern": "local_success_global_harm",
                     "evidence": "no anchor or checker constrains the final gate; nodes can each pass while the root outcome goes unchecked",
                     "repair": "add a system-level outcome check that constrains or vetoes the final human gate"})
    seen, uniq = set(), []
    for h in hits:
        key = (h["pattern"], h["evidence"])
        if key not in seen:
            seen.add(key)
            h["repair_layer"] = REPAIR_LAYER.get(h["pattern"], 6)
            h["layer_name"] = LAYER_NAMES[h["repair_layer"]]
            uniq.append(h)
    hits = sorted(uniq, key=lambda h: h["repair_layer"])
    status = "healthy" if not hits and not f.errors else ("blocked" if f.errors else "at_risk")
    return {"version": VERSION, "status": status, "patterns": hits,
            "repair_order_note": "fix the lowest repair_layer first; do not add agents or retries before grounding and authority are repaired",
            "validation_errors": f.errors, "validation_warnings": [i for i in f.items if i["level"] == "warning"],
            "legend": PATTERNS}


# ----------------------------------------------------------------------------- mermaid
SHAPES = {"anchor": ("[(", ")]"), "human_gate": ("{{", "}}"), "stop_handoff": ("([", "])"),
          "verification_loop": ("[/", "/]"), "counter_metric_loop": ("[/", "/]"), "audit_loop": ("[/", "/]"),
          "arbitration": ("{", "}")}


def mermaid(raw: dict[str, Any]) -> str:
    g = Graph(normalize(raw))
    lines = ["flowchart LR"]
    for nid, n in g.nodes.items():
        a, b = SHAPES.get(n.get("kind", ""), ("[", "]"))
        label = f"{nid}<br/><small>{n.get('kind')}</small>".replace('"', "'")
        lines.append(f'  {nid.replace("-", "_")}{a}"{label}"{b}')
    for e in g.edges:
        arrow = "-.->" if e.get("relation") in {"observes", "anchors"} else ("--x" if e.get("relation") == "vetoes" else "-->")
        lines.append(f'  {e["from"].replace("-", "_")} {arrow}|{e.get("relation")}: {e.get("artifact")}| {e["to"].replace("-", "_")}')
    return "\n".join(lines)


# ----------------------------------------------------------------------------- simulate
def simulate(raw: dict[str, Any], fail_node: str | None) -> dict[str, Any]:
    f = validate(raw)
    spec = normalize(raw)
    pre = [i["message"] for i in f.errors]
    if spec.get("state") != "ready":
        pre.append("simulate only accepts state=ready")
    if (spec.get("execution_contract") or {}).get("external_execution") is not False:
        pre.append("simulate requires external_execution=false")
    if pre:
        return {"status": "rejected", "errors": pre, "domain_completion_claimed": False}
    full = Graph(spec)
    # feedback edges (observes / revises) carry signals back; they are not scheduling dependencies
    sched = dict(spec, edges=[e for e in full.edges if e.get("relation") not in FEEDBACK])
    g = Graph(sched)
    cyc = {n for comp in g.sccs() for n in comp}
    def blocking(e: dict) -> bool:
        return not (e["from"] in cyc and e["to"] in cyc)
    indeg = {n: 0 for n in g.nodes}
    for e in g.edges:
        if blocking(e):
            indeg[e["to"]] += 1
    batches, ready = [], sorted(n for n, d in indeg.items() if d == 0)
    status: dict[str, str] = {}
    while ready:
        batches.append(ready)
        nxt = []
        for n in ready:
            ups = [e["from"] for e in g.inc[n] if blocking(e)]
            vetoed = any(e.get("relation") == "vetoes" and status.get(e["from"]) == "failed" for e in g.inc[n])
            if n == fail_node:
                status[n] = "failed"
            elif g.kind(n) == "stop_handoff":
                status[n] = "handed_off" if vetoed or any(v in {"failed", "skipped"} for v in status.values()) else "passed"
            elif any(status.get(u) in {"failed", "skipped"} for u in ups):
                status[n] = "skipped"
            else:
                status[n] = "passed"
            for e in g.out[n]:
                if not blocking(e):
                    continue
                indeg[e["to"]] -= 1
                if indeg[e["to"]] == 0:
                    nxt.append(e["to"])
        ready = sorted(set(nxt))
    overall = "simulated_success" if all(v == "passed" for v in status.values()) else "simulated_failure_handed_off"
    unreached = sorted(set(g.nodes) - set(status))
    if unreached:
        overall = "rejected"
    return {"status": overall, "batches": batches, "node_status": status,
            "cycles_collapsed": sorted(cyc), "unreached": unreached, "feedback_edges_ignored_for_scheduling": sorted(FEEDBACK), "domain_completion_claimed": False,
            "note": "synthetic run; proves scheduling and failure propagation only"}



# ----------------------------------------------------------------------------- init
def init_graph(outcome: str, root: Path, slug: str | None) -> Path:
    import re
    gid = re.sub(r"[^a-z0-9]+", "-", (slug or outcome).lower()).strip("-") or "graph"
    d = root.expanduser().resolve() / ".graph" / gid
    if d.exists():
        raise FileExistsError(f"target already exists: {d}")
    d.mkdir(parents=True)
    todo = "TODO"
    spec = {
        "schema_version": "1.1", "title": gid, "mode": "graph", "state": "designed",
        "root_goal": {"statement": outcome, "human_owner": f"{todo}: named human", "observable_success": f"{todo}: observable acceptance",
                      "out_of_scope": [f"{todo}: explicit exclusion"], "metrics": []},
        "classification_rationale": f"{todo}: why a direct workflow or single loop is insufficient",
        "permissions": {"human_owner": f"{todo}", "allowed_actions": [], "forbidden_actions": []},
        "frozen_rules": [f"{todo}: anchors, protected tests, safety boundary"],
        "approval": {"status": "pending"},
        "budget": {"max_agents": 4, "max_concurrency": 2, "max_retries": 1, "max_cost_units": 10},
        "failure_policy": {"failed": todo, "blocked": todo, "budget_exhausted": todo},
        "stop_handoff": {"owner": todo, "conditions": [todo], "artifact": "handoff.md"},
        "execution_contract": {"external_execution": False},
        "governance": {"arbitration": {"owner": todo, "priority_policy": todo}, "goal_change": "human_approval",
                       "approval_required": ["Root-goal change", "Anchor change", "Permission expansion"]},
        "verification": {"independence_statement": f"{todo}: evaluator AND data provenance differ from execution", "checks": []},
        "external_inputs": [], "anchors": [], "nodes": [], "edges": [],
    }
    (d / "graph.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sections = ("为什么单回路不够", "职责节点", "证据流与权力边", "现实锚点与冻结项", "节奏与仲裁", "故障演练")
    (d / "graph-spec.md").write_text(f"# 图规格：{gid}\n\n## 根结果\n\n{outcome}\n\n"
                                     + "".join(f"## {h}\n\nTODO\n\n" for h in sections), encoding="utf-8")
    (d / "validation-report.md").write_text("# 校验记录\n\n状态：未运行\n\n## validate\n\nTODO\n\n## diagnose\n\nTODO\n\n## 领域证据\n\nTODO\n", encoding="utf-8")
    (d / "handoff.md").write_text("# 交接\n\n状态：designed\n\n## 已有证据\n\n暂无\n\n## 下一步\n\n填完 graph.json，跑 validate 和 diagnose。\n\n## 待批准事项\n\nTODO\n", encoding="utf-8")
    return d


# ----------------------------------------------------------------------------- cli
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="geaplus", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    ip = sub.add_parser("init")
    ip.add_argument("outcome")
    ip.add_argument("--root", required=True, type=Path)
    ip.add_argument("--slug")
    for name in ("classify", "validate", "diagnose", "mermaid", "simulate"):
        sp = sub.add_parser(name)
        sp.add_argument("path", type=Path)
        sp.add_argument("--json", action="store_true")
        if name == "diagnose":
            sp.add_argument("--today", default=dt.date.today().isoformat())
            sp.add_argument("--run", type=Path)
        if name == "simulate":
            sp.add_argument("--fail-node")
    a = p.parse_args(argv)
    if a.cmd == "init":
        try:
            print(init_graph(a.outcome, a.root, a.slug))
            return 0
        except FileExistsError as ex:
            print(ex, file=sys.stderr)
            return 2
    if a.path.is_dir():
        a.path = a.path / "graph.json"
    try:
        data = load(a.path)
    except (OSError, ValueError) as ex:
        print(f"cannot read {a.path}: {ex}", file=sys.stderr)
        return 2
    if a.cmd == "classify":
        print(json.dumps(classify(data), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "mermaid":
        print(mermaid(data))
        return 0
    if a.cmd == "simulate":
        r = simulate(data, a.fail_node)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["status"] != "rejected" else 1
    if a.cmd == "diagnose":
        run = load(a.run) if a.run else None
        r = diagnose(data, dt.date.fromisoformat(a.today), run)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["status"] == "healthy" else 1
    f = validate(data)
    if a.json:
        print(json.dumps({"ok": not f.errors, "findings": f.items}, ensure_ascii=False, indent=2))
    else:
        for i in f.items:
            tag = "ERROR" if i["level"] == "error" else "warn "
            print(f"[{tag}] {i['code']}: {i['message']}" + (f"\n         fix: {i['repair']}" if i["repair"] else ""))
        print("PASS (structure only; does not prove domain truth or real-world anchor independence)" if not f.errors
              else f"FAIL: {len(f.errors)} error(s)")
    return 0 if not f.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
