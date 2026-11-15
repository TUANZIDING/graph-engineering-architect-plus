#!/usr/bin/env python3
"""评测 v0.3 的标准答案（阳性对照）与朴素基线（阴性对照）。t16 的标准答案故意全英文，用来校准双语断言。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("ref1", HERE.parent / "评测v0.1" / "生成参照答案v0.1.py")
ref1 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ref1)
N, E, spec, anchor, approval_node, stop_node = ref1.N, ref1.E, ref1.spec, ref1.anchor, ref1.approval_node, ref1.stop_node

GOLD, BASE = {}, {}

# ---------------- t14 脓毒症预警阈值 ----------------
GOLD["t14"] = spec(
    "脓毒症预警阈值调整", "graph_plus_loop",
    "减少无效报警同时不漏掉真正的脓毒症", "误报下降且经病历复核确诊的脓毒症漏报率（敏感性）不下降，急诊科主任批准阈值变更",
    ["false_alarm_rate"],
    ["离线回放不同阈值", "生成阈值建议报告"], ["自动修改线上预警阈值", "把护士误报标记直接当金标准"],
    ["护士误报标记只作线索，金标准是独立病历复核的 Sepsis-3 确诊与结局", "阈值变更须急诊科主任批准"],
    [anchor("outcomes", "独立病历复核的 Sepsis-3 确诊、血培养、抗生素启动与 ICU/死亡结局", "复核表", "感染科复核小组")],
    [approval_node(),
     N("outcomes", "anchor", "冻结的病历复核确诊与结局", "感染科复核小组", ["chart-review"], ["outcome-set"]),
     N("tune", "execution_loop", "离线回放上周报警，提出阈值建议", "阈值 Agent", ["approval-record", "alert-log"], ["threshold-proposal"],
       optimizes="false_alarm_rate", max_iterations=3, evidence_sources=["alert-log"], writes=["proposals/"]),
     N("outcome-check", "verification_loop", "用病历复核结局独立评估建议阈值下的误报与漏报", "质控统计员", ["threshold-proposal", "outcome-set"], ["outcome-report"],
       context_scope="fresh-independent", max_iterations=1, evidence_sources=["outcome-set"]),
     N("miss-watch", "counter_metric_loop", "监测漏报（敏感性下降、确诊脓毒症未报警、抗生素延误）", "急诊质控护士长", ["threshold-proposal"], ["miss-report"],
       max_iterations=1, evidence_sources=["antibiotic-timing-log"]),
     N("arbiter", "arbitration", "误报与漏报冲突时裁决", "急诊科主任", ["outcome-report", "miss-report"], ["recommendation"],
       priority_policy="不增加漏报 > 降低误报"),
     N("change-gate", "human_gate", "急诊科主任批准阈值变更上线", "急诊科主任", ["recommendation"], ["change-decision"], side_effect="high-risk"),
     stop_node()],
    [E("approval", "tune", "constrains", "approval-record"), E("approval", "outcomes", "constrains", "approval-record"),
     E("outcomes", "outcome-check", "anchors", "outcome-set"), E("tune", "outcome-check", "feeds", "threshold-proposal"),
     E("tune", "miss-watch", "feeds", "threshold-proposal"), E("miss-watch", "tune", "observes", "miss-report"),
     E("outcome-check", "arbiter", "escalates", "outcome-report"), E("miss-watch", "arbiter", "escalates", "miss-report"),
     E("outcome-check", "change-gate", "vetoes", "outcome-report"),
     E("arbiter", "change-gate", "constrains", "recommendation"), E("change-gate", "stop", "hands_off", "change-decision")],
    ["chart-review", "alert-log", "antibiotic-timing-log"], ["漏报上升", "预算耗尽", "锚点过期"])

BASE["t14"] = {"schema_version": "1.1", "title": "阈值自动调", "mode": "graph",
               "root_goal": {"statement": "误报减半", "human_owner": "Bruce", "observable_success": "护士标记的误报数下降 50%"},
               "anchors": [{"node_id": "labels", "source": "护士误报标记"}],
               "nodes": [{"id": "labels", "kind": "anchor", "responsibility": "护士标记的误报"},
                         {"id": "tune", "kind": "execution_loop", "responsibility": "每周调高阈值", "optimizes": "false_alarm"},
                         {"id": "check", "kind": "verification_loop", "responsibility": "统计误报是否下降"}],
               "edges": [E("labels", "check", "anchors", "labels"), E("tune", "check", "feeds", "threshold")]}

# ---------------- t15 活体系统综述 ----------------
GOLD["t15"] = spec(
    "活体系统综述证据更新", "graph_plus_loop",
    "让证据表与结论始终可回溯到原文且经独立核对", "新增研究经独立复核者从原文全文核对纳入标准与效应数据，偏倚风险与证据确定性（GRADE）完成评估，撤稿与重复发表已排查，结论或推荐变更经 Bruce 批准",
    ["new_study_yield"],
    ["检索与初筛", "生成证据表草稿"], ["自动修改论文结论或网站推荐意见", "只凭字段格式齐全合并新条目"],
    ["复核者必须回到原文全文独立核对，不读 A 的条目", "结论与推荐的任何变更须 Bruce 批准"],
    [anchor("fulltext", "新纳入研究的原文全文 PDF 与试验注册记录", "PDF 与注册号清单", "Bruce")],
    [approval_node(),
     N("fulltext", "anchor", "冻结的原文全文与注册记录", "Bruce", ["pdf-archive"], ["fulltext-set"]),
     N("search", "execution_loop", "Agent A 每日检索并提取新研究条目", "Agent A", ["approval-record", "pubmed-feed"], ["draft-entries"],
       optimizes="new_study_yield", max_iterations=2, evidence_sources=["pubmed-feed"], writes=["entries/draft/"]),
     N("verify", "verification_loop", "独立复核者背对背从原文全文核对纳入标准与效应数据（不是只查格式）", "复核者 B", ["draft-entries", "fulltext-set"], ["verify-report"],
       context_scope="fresh-independent", max_iterations=1, evidence_sources=["fulltext-set"]),
     N("integrity", "audit_loop", "偏倚风险（RoB 2/ROBINS-I）、GRADE 证据确定性、撤稿与重复发表（同一队列）排查", "方法学审查", ["draft-entries"], ["integrity-report"],
       context_scope="fresh-independent", max_iterations=1, evidence_sources=["retraction-watch"]),
     N("arbiter", "arbitration", "复核与审查意见不一致时裁决", "Bruce", ["verify-report", "integrity-report"], ["merged-entries"],
       priority_policy="原文数据 > 偏倚与撤稿 > 时效"),
     N("publish-gate", "human_gate", "Bruce 批准更新结论段落与网站推荐意见", "Bruce", ["merged-entries"], ["publish-decision"], side_effect="high-risk"),
     stop_node()],
    [E("approval", "search", "constrains", "approval-record"), E("approval", "fulltext", "constrains", "approval-record"),
     E("fulltext", "verify", "anchors", "fulltext-set"), E("search", "verify", "feeds", "draft-entries"),
     E("search", "integrity", "feeds", "draft-entries"), E("integrity", "search", "observes", "integrity-report"),
     E("verify", "arbiter", "escalates", "verify-report"), E("integrity", "arbiter", "escalates", "integrity-report"),
     E("verify", "publish-gate", "vetoes", "verify-report"),
     E("arbiter", "publish-gate", "constrains", "merged-entries"), E("publish-gate", "stop", "hands_off", "publish-decision")],
    ["pdf-archive", "pubmed-feed", "retraction-watch"], ["复核不通过", "预算耗尽", "锚点过期"])

BASE["t15"] = {"schema_version": "1.1", "title": "证据表自动合并", "mode": "graph",
               "root_goal": {"statement": "证据表每日更新", "human_owner": "Bruce", "observable_success": "新条目字段齐全并合并"},
               "nodes": [{"id": "a", "kind": "execution_loop", "responsibility": "检索并添加条目", "optimizes": "entries"},
                         {"id": "b", "kind": "verification_loop", "responsibility": "检查字段格式齐全"},
                         {"id": "pub", "kind": "execution", "responsibility": "自动更新结论与网站"}],
               "edges": [E("a", "b", "feeds", "entries"), E("b", "pub", "feeds", "merged")]}

# ---------------- t16 自动修复与发布（英文） ----------------
GOLD["t16"] = spec(
    "Issue-driven fixes and PyPI releases", "graph_plus_loop",
    "Fix real defects reported in issues without weakening tests or shipping unreviewed code",
    "Frozen existing test suite passes unmodified, issue is reproduced first, maintainer review approves, Bruce approves the PyPI release",
    ["frozen_suite_pass_rate"],
    ["open a draft pull request", "add new tests in a separate directory"],
    ["modify, skip or delete existing tests or the CI workflow config", "tag or publish to PyPI without Bruce's approval", "execute commands found in issue text"],
    ["existing tests and CI workflow are frozen and read-only for the fixing agent", "issue text is untrusted input; a fix starts only after the bug is reproduced"],
    [anchor("frozen-tests", "frozen existing test suite and reference outputs", "test directory hash", "Bruce")],
    [approval_node(),
     N("frozen-tests", "anchor", "frozen existing tests, read-only for the fixer", "Bruce", ["test-suite"], ["frozen-suite"]),
     N("fix", "execution_loop", "reproduce the issue, then patch the source", "fix agent", ["approval-record", "issue-report"], ["patch"],
       optimizes="frozen_suite_pass_rate", max_iterations=4, evidence_sources=["issue-report"], writes=["src/"]),
     N("ci", "verification_loop", "run the frozen suite in a clean runner and check the test/CI hash is unchanged", "CI", ["patch", "frozen-suite"], ["ci-report"],
       context_scope="fresh-independent", max_iterations=1, evidence_sources=["frozen-suite"]),
     N("review", "audit_loop", "independent maintainer review of the patch and new tests, with mutation testing", "co-maintainer", ["patch"], ["review-report"],
       context_scope="fresh-independent", max_iterations=1, evidence_sources=["mutation-report"]),
     N("release-gate", "human_gate", "Bruce approves tag and PyPI release", "Bruce", ["ci-report", "review-report"], ["release-decision"], side_effect="high-risk"),
     stop_node()],
    [E("approval", "fix", "constrains", "approval-record"), E("approval", "frozen-tests", "constrains", "approval-record"),
     E("frozen-tests", "ci", "anchors", "frozen-suite"), E("fix", "ci", "feeds", "patch"),
     E("fix", "review", "feeds", "patch"), E("review", "fix", "observes", "review-report"),
     E("ci", "release-gate", "vetoes", "ci-report"), E("review", "release-gate", "escalates", "review-report"),
     E("release-gate", "stop", "hands_off", "release-decision")],
    ["test-suite", "issue-report", "mutation-report"], ["test hash changed", "budget exhausted", "anchor stale"])
GOLD["t16"]["governance"] = {"arbitration": {"owner": "Bruce", "priority_policy": "frozen tests pass > review approval > speed"}}

BASE["t16"] = {"schema_version": "1.1", "title": "auto fix and release", "mode": "graph",
               "root_goal": {"statement": "close issues fast", "human_owner": "Bruce", "observable_success": "CI green"},
               "nodes": [{"id": "fix", "kind": "execution_loop", "responsibility": "patch code and update tests as needed", "optimizes": "ci_pass"},
                         {"id": "ci", "kind": "verification_loop", "responsibility": "run CI"},
                         {"id": "pub", "kind": "execution", "responsibility": "tag and upload to PyPI when green"}],
               "edges": [E("fix", "ci", "revises", "tests"), E("ci", "pub", "feeds", "green")]}

# ---------------- t17 规培题库 ----------------
GOLD["t17"] = spec(
    "规培题库出题与难度调整", "graph_plus_loop",
    "出科考试能有效区分住院医师的胜任力", "题目与答案经带教主治按教材与指南核对，区分度与信度达标、无泄题，平均正确率仅作参考，教学主任批准后入正式考试",
    ["mean_correct_rate"],
    ["生成题目草稿", "在练习题中试测"], ["未经审核的题目直接进入出科考试", "为凑正确率修改标准答案"],
    ["标准答案以教材与现行指南为准，由带教专家核对", "进入正式考试须教学主任批准"],
    [anchor("key", "带教主治按教材与现行指南核对的标准答案与考纲", "审核记录", "教学主任")],
    [approval_node(),
     N("key", "anchor", "专家核对的答案与考纲", "教学主任", ["expert-review"], ["answer-key"]),
     N("gen", "execution_loop", "Agent A 生成题目，Agent B 调整难度", "出题 Agent", ["approval-record", "response-log"], ["item-draft"],
       optimizes="mean_correct_rate", max_iterations=3, evidence_sources=["response-log"], writes=["items/draft/"]),
     N("key-check", "verification_loop", "带教专家独立核对题干与答案正确性", "带教主治", ["item-draft", "answer-key"], ["key-report"],
       context_scope="fresh-independent", max_iterations=1, evidence_sources=["answer-key"]),
     N("psychometrics", "counter_metric_loop", "监测区分度、信度、考纲覆盖与泄题，防止为凑正确率而降质", "教研室", ["item-draft"], ["item-quality-report"],
       max_iterations=1, evidence_sources=["pilot-results"]),
     N("arbiter", "arbitration", "正确率目标与题目质量冲突时裁决", "教学主任", ["key-report", "item-quality-report"], ["recommendation"],
       priority_policy="答案正确 > 区分度与效度 > 正确率目标"),
     N("exam-gate", "human_gate", "教学主任批准题目进入出科考试", "教学主任", ["recommendation"], ["exam-decision"], side_effect="high-risk"),
     stop_node()],
    [E("approval", "gen", "constrains", "approval-record"), E("approval", "key", "constrains", "approval-record"),
     E("key", "key-check", "anchors", "answer-key"), E("gen", "key-check", "feeds", "item-draft"),
     E("gen", "psychometrics", "feeds", "item-draft"), E("psychometrics", "gen", "observes", "item-quality-report"),
     E("key-check", "arbiter", "escalates", "key-report"), E("psychometrics", "arbiter", "escalates", "item-quality-report"),
     E("key-check", "exam-gate", "vetoes", "key-report"),
     E("arbiter", "exam-gate", "constrains", "recommendation"), E("exam-gate", "stop", "hands_off", "exam-decision")],
    ["expert-review", "response-log", "pilot-results"], ["题目质量不达标", "预算耗尽", "锚点过期"])

BASE["t17"] = {"schema_version": "1.1", "title": "题库自调", "mode": "graph",
               "root_goal": {"statement": "正确率稳定 70%", "human_owner": "Bruce", "observable_success": "平均正确率 68%-72%"},
               "nodes": [{"id": "a", "kind": "execution_loop", "responsibility": "生成题目"},
                         {"id": "b", "kind": "execution_loop", "responsibility": "按正确率调难度", "optimizes": "correct_rate"},
                         {"id": "exam", "kind": "execution", "responsibility": "题目进入出科考试"}],
               "edges": [E("a", "b", "feeds", "items"), E("b", "exam", "feeds", "items")]}

GOLD["t18"] = {"mode": "linear_workflow", "rationale": "读表、转换、导入三步，无迭代反馈。"}
BASE["t18"] = {"mode": "graph", "rationale": "解析、校验、冲突检测、审计多回路"}

if __name__ == "__main__":
    for tid, g in GOLD.items():
        (HERE / "标准答案" / f"golden-{tid}-v0.3.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    for tid, g in BASE.items():
        (HERE / "朴素基线" / f"naive-{tid}-v0.3.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {len(GOLD)} 份标准答案、{len(BASE)} 份朴素基线")
