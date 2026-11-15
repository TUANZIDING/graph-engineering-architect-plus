"""Regression tests for geaplus v1.1. Run: python3 -m unittest discover -s tests -p 'test-*.py' -v"""

import copy
import datetime as dt
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("geaplus", ROOT / "工具" / "graph-engineering-architect-plus" / "scripts" / "geaplus-v1.1.py")
gea = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gea)

GOOD = json.loads((ROOT / "示例" / "faers-manuscript-graph-v1.1.json").read_text(encoding="utf-8"))
BAD = json.loads((ROOT / "示例" / "broken-circular-graph-v1.0.json").read_text(encoding="utf-8"))
TODAY = dt.date(2026, 11, 15)


def codes(s):
    return {i["code"] for i in gea.validate(s).errors}


def node(s, nid):
    return next(n for n in s["nodes"] if n["id"] == nid)


class Classify(unittest.TestCase):
    def brief(self, **sig):
        return {"root_goal": {"statement": "x", "human_owner": "h", "observable_success": "y"}, "signals": {"task_clear": True, **sig}}

    def test_missing_goal_blocks(self):
        self.assertEqual(gea.classify({"signals": {"task_clear": True}})["mode"], "blocked")

    def test_no_anchor_blocks(self):
        self.assertEqual(gea.classify(self.brief(reality_anchor_available=False))["mode"], "blocked")

    def test_single_action_is_direct(self):
        self.assertEqual(gea.classify(self.brief(single_bounded_action=True))["mode"], "direct")

    def test_iteration_is_loop(self):
        self.assertEqual(gea.classify(self.brief(requires_iteration=True))["mode"], "loop")

    def test_gameable_independent_is_graph(self):
        self.assertEqual(gea.classify(self.brief(independent_responsibilities=True, requires_independent_verification=True,
                                                 metric_gameable=True, requires_iteration=True))["mode"], "graph_plus_loop")


class Validate(unittest.TestCase):
    def test_good_example_passes(self):
        self.assertEqual(codes(GOOD), set())

    def test_bad_example_flags_circular_and_owner(self):
        c = codes(BAD)
        self.assertIn("E-CIRCULAR", c)
        self.assertIn("E-SAMEOWNER", c)
        self.assertIn("E-GOODHART", c)

    def test_executor_cannot_write_anchor(self):
        s = copy.deepcopy(GOOD)
        s["edges"].append({"from": "signal-analysis", "to": "data-anchor", "relation": "revises", "artifact": "patched-data"})
        self.assertIn("E-ANCHORWRITE", codes(s))

    def test_verifier_without_teeth(self):
        s = copy.deepcopy(GOOD)
        s["edges"] = [e for e in s["edges"] if e["from"] != "independent-rerun"]
        self.assertIn("E-VNOTEETH", codes(s))

    def test_high_risk_needs_gate_upstream(self):
        s = copy.deepcopy(GOOD)
        s["nodes"].append({"id": "submit", "kind": "execution", "responsibility": "投稿", "owner": "bot", "side_effect": "high-risk",
                           "contract": {"inputs": ["x"], "outputs": ["y"]}})
        s["edges"].append({"from": "submit", "to": "stop-handoff", "relation": "hands_off", "artifact": "y"})
        self.assertIn("E-GATEFIRST", codes(s))

    def test_unbounded_cycle(self):
        s = copy.deepcopy(GOOD)
        node(s, "drafting")["kind"] = "synthesis"
        s["edges"].append({"from": "claim-audit", "to": "drafting", "relation": "revises", "artifact": "fixes"})
        node(s, "claim-audit").pop("max_iterations")
        c = codes(s)
        self.assertIn("E-LOOPBOUND", c)
        self.assertIn("E-UNBOUNDED", c)

    def test_parallel_writers(self):
        s = copy.deepcopy(GOOD)
        node(s, "negative-control")["writes"] = ["results/rerun"]
        self.assertIn("E-WRITERS", codes(s))

    def test_ready_needs_approval(self):
        s = copy.deepcopy(GOOD)
        s["state"] = "ready"
        self.assertIn("E-APPROVAL", codes(s))

    def test_completed_needs_reality(self):
        s = copy.deepcopy(GOOD)
        s.update(state="completed", approval={"status": "approved", "approved_by": "Bruce"})
        self.assertIn("E-DONE", codes(s))



class Diagnose(unittest.TestCase):
    def test_good_is_healthy(self):
        self.assertEqual(gea.diagnose(GOOD, TODAY, None)["status"], "healthy")

    def test_bad_finds_three_patterns(self):
        pats = {p["pattern"] for p in gea.diagnose(BAD, TODAY, None)["patterns"]}
        self.assertTrue({"circular_confirmation", "metric_gaming", "decayed_measurement"} <= pats)

    def test_wrong_target(self):
        s = copy.deepcopy(GOOD)
        node(s, "signal-analysis")["optimizes"] = "number_of_signals"
        self.assertIn("wrong_target", {p["pattern"] for p in gea.diagnose(s, TODAY, None)["patterns"]})

    def test_run_log_gaming(self):
        run = {"node_results": [{"node_id": "signal-analysis", "score_history": [3, 6, 11], "anchor_agreement": 0.3}]}
        self.assertIn("metric_gaming", {p["pattern"] for p in gea.diagnose(GOOD, TODAY, run)["patterns"]})


class Simulate(unittest.TestCase):
    def ready(self):
        s = copy.deepcopy(GOOD)
        s.update(state="ready", approval={"status": "approved", "approved_by": "Bruce"})
        return s

    def test_success_never_claims_domain_completion(self):
        r = gea.simulate(self.ready(), None)
        self.assertEqual(r["status"], "simulated_success")
        self.assertFalse(r["domain_completion_claimed"])

    def test_verifier_failure_hands_off(self):
        r = gea.simulate(self.ready(), "independent-rerun")
        self.assertEqual(r["node_status"]["drafting"], "skipped")
        self.assertEqual(r["node_status"]["stop-handoff"], "handed_off")

    def test_rejects_unapproved(self):
        self.assertEqual(gea.simulate(GOOD, None)["status"], "rejected")



ORIG = json.loads((ROOT / "示例" / "legacy-trauma-audit-graph-v1.1.json").read_text(encoding="utf-8"))
REPAIRED = json.loads((ROOT / "示例" / "legacy-trauma-audit-graph-repaired-v1.1.json").read_text(encoding="utf-8"))


class V11(unittest.TestCase):
    def test_legacy_schema_is_read(self):
        n = gea.normalize(ORIG)
        self.assertEqual(n["root_goal"]["human_owner"], "急诊科质控主任")
        self.assertEqual(node(n, "fill")["contract"]["inputs"], ["质控模板", "原始护理与检验记录"])

    def test_legacy_example_has_watcher_theater(self):
        c = codes(ORIG)
        self.assertIn("E-THEATER", c)
        self.assertIn("E-VNOANCHOR", c)

    def test_repaired_legacy_is_healthy(self):
        self.assertEqual(codes(REPAIRED), set())
        self.assertEqual(gea.diagnose(REPAIRED, TODAY, None)["status"], "healthy")

    def test_legacy_rules_enforced(self):
        s = copy.deepcopy(REPAIRED)
        s["governance"]["goal_change"] = "agent"
        s["verification"]["checks"][0]["verifier_node"] = "fill"
        c = codes(s)
        self.assertIn("O-GOAL", c)
        self.assertIn("O-CHECKS", c)

    def test_placeholder_rejected(self):
        s = copy.deepcopy(GOOD)
        s["root_goal"]["observable_success"] = "TODO later"
        self.assertIn("E-PLACEHOLDER", codes(s))

    def test_meta_capture(self):
        s = copy.deepcopy(GOOD)
        s["edges"].append({"from": "signal-analysis", "to": "negative-control", "relation": "revises", "artifact": "looser threshold"})
        self.assertIn("E-METACAPTURE", codes(s))

    def test_cadence_thrashing(self):
        s = copy.deepcopy(REPAIRED)
        s["nodes"].append({"id": "gov", "kind": "governance_loop", "responsibility": "review targets", "owner": "board",
                           "cadence": "Quarterly", "inputs": ["x"], "outputs": ["targets"]})
        s["edges"].append({"from": "gov", "to": "close", "relation": "hands_off", "artifact": "targets"})
        s["edges"].append({"from": "fill", "to": "gov", "relation": "constrains", "artifact": "new target"})
        pats = {p["pattern"] for p in gea.diagnose(s, TODAY, None)["patterns"]}
        self.assertIn("cadence_thrashing", pats)

    def test_decorative(self):
        s = copy.deepcopy(GOOD)
        for e in s["edges"]:
            if e["relation"] in {"constrains", "vetoes", "escalates", "arbitrates"}:
                e["relation"] = "feeds"
        self.assertIn("E-DECORATIVE", codes(s))

    def test_no_counter_metric(self):
        s = copy.deepcopy(BAD)
        node(s, "claim-audit")["kind"] = "verification_loop"
        self.assertIn("E-NOCOUNTER", codes(s))

    def test_repair_order_sorted(self):
        layers = [p["repair_layer"] for p in gea.diagnose(BAD, TODAY, None)["patterns"]]
        self.assertEqual(layers, sorted(layers))

    def test_init_scaffold_fails_until_filled(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = gea.init_graph("可复现的结论", Path(d), "demo")
            for f in ("graph.json", "graph-spec.md", "validation-report.md", "handoff.md"):
                self.assertTrue((out / f).exists())
            spec = json.loads((out / "graph.json").read_text(encoding="utf-8"))
            self.assertIn("E-PLACEHOLDER", codes(spec))


if __name__ == "__main__":
    unittest.main()
