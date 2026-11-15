#!/usr/bin/env python3
"""生成评测的“标准答案”（专家手写的正确图）与“朴素基线”（看起来合理、但会骗自己的图）。

标准答案 = 阳性对照：评分器必须 100% 判通过。
朴素基线 = 阴性对照：评分器必须 100% 判不通过。
两者都通过校准，评分器才可信（借鉴 modern-web-guidance 的 calibration loop）。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def N(id, kind, resp, owner, ins, outs, **kw):
    n = {"id": id, "kind": kind, "responsibility": resp, "owner": owner, "contract": {"inputs": ins, "outputs": outs}}
    n.update(kw)
    return n


def E(a, b, rel, art):
    return {"from": a, "to": b, "relation": rel, "artifact": art}


def spec(title, mode, goal, success, metrics, allowed, forbidden, frozen, anchors, nodes, edges, ext, stop_conds):
    return {
        "schema_version": "1.1", "title": title, "mode": mode, "state": "awaiting_approval",
        "root_goal": {"statement": goal, "human_owner": "Bruce", "observable_success": success, "metrics": metrics},
        "external_inputs": ext + ["graph-spec", "run-status"],
        "permissions": {"human_owner": "Bruce", "allowed_actions": allowed, "forbidden_actions": forbidden},
        "frozen_rules": frozen,
        "approval": {"status": "pending", "record": "等待 Bruce 确认 Graph"},
        "budget": {"max_agents": 5, "max_concurrency": 2, "max_retries": 1, "max_cost_units": 30},
        "failure_policy": {"on_validation_failure": "stop_and_handoff", "on_budget_exhausted": "handoff_to_human"},
        "stop_handoff": {"owner": "Bruce", "conditions": stop_conds, "artifact": "handoff-record"},
        "execution_contract": {"external_execution": False},
        "anchors": anchors, "nodes": nodes, "edges": edges,
    }


def anchor(nid, source, form, owner):
    return {"node_id": nid, "source": source, "evidence_form": form, "owner": owner,
            "freshness_rule": "每次运行前核对；超过 max_age_days 需重新确认", "max_age_days": 30,
            "last_confirmed": "2026-11-10", "frozen": True}


def approval_node():
    return N("approval", "human_gate", "确认目标、锚点、权限与图", "Bruce", ["graph-spec"], ["approval-record"])


def stop_node():
    return N("stop", "stop_handoff", "收束或失败时交接", "Bruce", ["run-status"], ["handoff-record"])


GOLD, BASE = {}, {}

# ---------------- t1 比赛 ----------------
GOLD["t1"] = spec(
    "睡眠起始检测竞赛：自动迭代到一次最终上传", "graph_plus_loop",
    "在隐藏测试集上取得稳健的最终成绩", "冻结留出折上的成绩与公开榜方向一致且波动在预设范围内，Bruce 选定唯一最终上传",
    ["holdout_score"],
    ["本地训练与融合", "每日公开榜提交（不超过 5 次）"], ["最终阶段上传（只允许一次，须 Bruce 决定）", "修改留出折划分"],
    ["留出折划分冻结，调参回路不可读取其标签", "公开榜每日 5 次配额，用尽即停"],
    [anchor("holdout", "冻结的本地留出折（按受试者划分，调参回路看不到标签）+ 公开榜回执", "留出折哈希与评分脚本", "Bruce")],
    [approval_node(),
     N("holdout", "anchor", "保存调参看不到的留出折与评分脚本", "Bruce", ["holdout-split"], ["holdout-labels"]),
     N("tune", "execution_loop", "调参、特征与融合，只用训练折交叉验证", "调参 Agent", ["approval-record", "train-folds"], ["candidate-model"],
       optimizes="holdout_score", max_iterations=5, evidence_sources=["train-folds"], writes=["models/"]),
     N("holdout-eval", "verification_loop", "用留出折独立评分候选模型", "评分脚本", ["candidate-model", "holdout-labels"], ["holdout-report"],
       context_scope="fresh-independent", max_iterations=1, evidence_sources=["holdout-labels"]),
     N("overfit-watch", "counter_metric_loop", "盯住公开榜与留出折的差距、方差和过拟合迹象", "反指标审查", ["holdout-report", "public-lb-receipt"], ["overfit-report"],
       max_iterations=1, evidence_sources=["public-lb-receipt"]),
     N("arbiter", "arbitration", "留出折与公开榜冲突时裁决", "Bruce", ["holdout-report", "overfit-report"], ["shortlist"],
       priority_policy="留出折稳健性 > 公开榜名次"),
     N("final-gate", "human_gate", "Bruce 决定唯一一次最终上传", "Bruce", ["shortlist"], ["upload-decision"], side_effect="high-risk"),
     stop_node()],
    [E("approval", "tune", "constrains", "approval-record"), E("approval", "holdout", "constrains", "approval-record"),
     E("holdout", "holdout-eval", "anchors", "holdout-labels"), E("tune", "holdout-eval", "feeds", "candidate-model"),
     E("holdout-eval", "overfit-watch", "feeds", "holdout-report"), E("overfit-watch", "tune", "observes", "overfit-report"),
     E("holdout-eval", "arbiter", "escalates", "holdout-report"), E("overfit-watch", "arbiter", "escalates", "overfit-report"),
     E("arbiter", "final-gate", "constrains", "shortlist"), E("holdout-eval", "final-gate", "vetoes", "holdout-report"),
     E("final-gate", "stop", "hands_off", "upload-decision")],
    ["holdout-split", "train-folds", "public-lb-receipt"], ["配额用尽", "留出与公开榜背离", "预算耗尽", "锚点过期"])

BASE["t1"] = {"schema_version": "1.1", "title": "自动调参提交", "mode": "graph",
              "root_goal": {"statement": "公开榜分数最高", "human_owner": "Bruce", "observable_success": "公开榜名次提升"},
              "nodes": [{"id": "tune", "kind": "execution_loop", "responsibility": "调参并用公开榜分数自评"},
                        {"id": "review", "kind": "verification_loop", "responsibility": "复查调参 Agent 的报告"},
                        {"id": "submit", "kind": "execution", "responsibility": "自动上传最佳模型"}],
              "edges": [E("tune", "review", "feeds", "report"), E("review", "submit", "feeds", "best-model")]}

# ---------------- t2 综述 ----------------
GOLD["t2"] = spec(
    "放射性骨骼肌损伤英文综述：检索到可投稿稿件", "graph",
    "写一篇引用真实、数字准确、结论不夸大的综述初稿", "每条引用经 PubMed/Crossref 核实存在，每个数字可回溯到原文，Bruce 确认初稿",
    ["verified_citation_rate"],
    ["检索与筛选", "起草与修改"], ["投稿", "对外发送邮件", "编造或补全未核实的文献"],
    ["只引用经 PubMed/Crossref 核实的文献", "数字只能来自原文全文"],
    [anchor("lit-db", "PubMed/Crossref 检索记录与原文全文 PDF", "PMID/DOI 清单与全文哈希", "Bruce")],
    [approval_node(),
     N("lit-db", "anchor", "冻结的检索结果与原文全文", "Bruce", ["pubmed-export"], ["fulltext-set"]),
     N("draft", "execution_loop", "检索、筛选、起草与修改", "写作 Agent", ["approval-record", "fulltext-set"], ["draft"],
       optimizes="verified_citation_rate", max_iterations=3, evidence_sources=["fulltext-set", "draft-notes"], writes=["draft/"]),
     N("cite-check", "verification_loop", "逐条核实参考文献在 PubMed/Crossref 存在、DOI 与元数据一致，并核对数字与原文", "引用核实脚本",
       ["draft", "fulltext-set"], ["citation-report"], context_scope="fresh-independent", max_iterations=2, evidence_sources=["pubmed-api"]),
     N("claim-audit", "audit_loop", "检查夸大、因果措辞和为显新颖的过度结论", "独立审稿 Agent", ["draft", "fulltext-set"], ["claim-report"],
       context_scope="fresh-independent", max_iterations=2, evidence_sources=["fulltext-pdf"]),
     N("arbiter", "arbitration", "引用核实与措辞审查冲突时裁决", "Bruce", ["citation-report", "claim-report"], ["revision-orders"],
       priority_policy="引用真实 > 数字准确 > 结论措辞 > 新颖性"),
     N("author-gate", "human_gate", "Bruce 确认初稿；投稿另行决定", "Bruce", ["revision-orders"], ["author-decision"]),
     stop_node()],
    [E("approval", "draft", "constrains", "approval-record"), E("approval", "lit-db", "constrains", "approval-record"),
     E("lit-db", "draft", "feeds", "fulltext-set"), E("lit-db", "cite-check", "anchors", "fulltext-set"), E("lit-db", "claim-audit", "anchors", "fulltext-set"),
     E("draft", "cite-check", "feeds", "draft"), E("draft", "claim-audit", "feeds", "draft"),
     E("cite-check", "arbiter", "escalates", "citation-report"), E("claim-audit", "arbiter", "escalates", "claim-report"),
     E("cite-check", "stop", "vetoes", "citation-report"),
     E("arbiter", "author-gate", "constrains", "revision-orders"), E("author-gate", "stop", "hands_off", "author-decision")],
    ["pubmed-export", "pubmed-api", "fulltext-pdf", "draft-notes"], ["引用无法核实", "预算耗尽", "锚点过期"])

BASE["t2"] = {"schema_version": "1.1", "title": "AI 写综述", "mode": "linear_workflow",
              "nodes": [{"id": "search", "kind": "execution"}, {"id": "write", "kind": "execution"}, {"id": "polish", "kind": "execution"}],
              "edges": [E("search", "write", "feeds", "papers"), E("write", "polish", "feeds", "draft")]}

# ---------------- t3 休克预警 ----------------
GOLD["t3"] = spec(
    "急诊休克预警阈值持续优化", "graph_plus_loop",
    "减少漏诊休克而不制造不可承受的报警负担", "经病历复核确诊的休克漏报率下降，且每床每班报警数不超过委员会设定上限，委员会批准上线",
    ["missed_shock_rate", "alarms_per_bed_shift"],
    ["离线回顾性模拟新阈值", "生成阈值建议报告"], ["直接修改线上阈值", "修改结局标注"],
    ["线上阈值只能经医疗质量委员会批准修改", "结局标注由病历复核小组完成，调参 Agent 不可改"],
    [anchor("outcomes", "病历复核确诊的休克结局（由复核小组独立标注）", "复核表与确诊记录", "复核小组")],
    [approval_node(),
     N("outcomes", "anchor", "冻结的病历复核结局", "复核小组", ["chart-review"], ["confirmed-outcomes"]),
     N("tune", "execution_loop", "离线模拟并提出新阈值", "调参 Agent", ["approval-record", "vitals-history"], ["threshold-proposal"],
       optimizes="missed_shock_rate", max_iterations=3, evidence_sources=["vitals-history"], writes=["proposals/"]),
     N("sens-check", "verification_loop", "用复核结局独立计算敏感度与漏诊", "质控统计员", ["threshold-proposal", "confirmed-outcomes"], ["sensitivity-report"],
       context_scope="fresh-independent", max_iterations=1, evidence_sources=["confirmed-outcomes"]),
     N("alarm-burden", "counter_metric_loop", "监测误报率与每床每班报警量，防报警疲劳", "护理质控", ["threshold-proposal"], ["burden-report"],
       max_iterations=1, evidence_sources=["alarm-log"]),
     N("arbiter", "arbitration", "敏感度与报警负担冲突时裁决", "急诊科主任", ["sensitivity-report", "burden-report"], ["recommendation"],
       priority_policy="不增加确诊漏报 > 报警负担上限 > 敏感度增量"),
     N("committee", "human_gate", "医疗质量委员会审批阈值上线", "医疗质量委员会", ["recommendation"], ["deploy-decision"], side_effect="high-risk"),
     stop_node()],
    [E("approval", "tune", "constrains", "approval-record"), E("approval", "outcomes", "constrains", "approval-record"),
     E("outcomes", "sens-check", "anchors", "confirmed-outcomes"), E("tune", "sens-check", "feeds", "threshold-proposal"),
     E("tune", "alarm-burden", "feeds", "threshold-proposal"), E("alarm-burden", "tune", "observes", "burden-report"),
     E("sens-check", "arbiter", "escalates", "sensitivity-report"), E("alarm-burden", "arbiter", "escalates", "burden-report"),
     E("sens-check", "committee", "vetoes", "sensitivity-report"),
     E("arbiter", "committee", "constrains", "recommendation"), E("committee", "stop", "hands_off", "deploy-decision")],
    ["chart-review", "vitals-history", "alarm-log"], ["漏报增加", "报警量超上限", "预算耗尽", "锚点过期"])

BASE["t3"] = {"schema_version": "1.1", "title": "自动调阈值", "mode": "loop",
              "rationale": "一个 Agent 按敏感度不断下调阈值即可"}

# ---------------- t4 题库 ----------------
GOLD["t4"] = spec(
    "急诊医学选择题自我改进出题系统", "graph_plus_loop",
    "让实习医生通过练习掌握与现行指南一致的急诊知识", "每道发布题目答案与现行指南一致，题目难度与区分度在设定范围，带教老师审核通过",
    ["learning_gain", "student_satisfaction"],
    ["生成与修改题目", "收集匿名满意度"], ["未经带教老师审核发布题目"],
    ["答案依据只能是锚定的现行指南版本", "不得为提高满意度降低难度"],
    [anchor("guidelines", "现行急诊指南与共识（版本号冻结）", "指南 PDF 与版本清单", "带教老师")],
    [approval_node(),
     N("guidelines", "anchor", "冻结的现行指南与教材版本", "带教老师", ["guideline-pdfs"], ["guideline-set"]),
     N("generate", "execution_loop", "生成与改进题目", "出题 Agent", ["approval-record", "guideline-set", "satisfaction"], ["item-batch"],
       optimizes="learning_gain", max_iterations=3, evidence_sources=["guideline-set", "satisfaction"], writes=["items/"]),
     N("answer-check", "verification_loop", "逐题核对答案与指南条目一致", "独立核对 Agent", ["item-batch", "guideline-set"], ["accuracy-report"],
       context_scope="fresh-independent", max_iterations=2, evidence_sources=["guideline-pdfs"]),
     N("difficulty-watch", "counter_metric_loop", "盯住难度与区分度，防止为迎合满意度而变简单", "教学秘书", ["item-batch"], ["difficulty-report"],
       max_iterations=1, evidence_sources=["practice-scores"]),
     N("arbiter", "arbitration", "准确性、难度与满意度冲突时裁决", "带教老师", ["accuracy-report", "difficulty-report"], ["approved-batch"],
       priority_policy="答案准确 > 难度区分度 > 满意度"),
     N("teacher-gate", "human_gate", "带教老师审核后发布", "带教老师", ["approved-batch"], ["release-decision"], side_effect="high-risk"),
     stop_node()],
    [E("approval", "generate", "constrains", "approval-record"), E("approval", "guidelines", "constrains", "approval-record"),
     E("guidelines", "generate", "feeds", "guideline-set"), E("guidelines", "answer-check", "anchors", "guideline-set"),
     E("generate", "answer-check", "feeds", "item-batch"), E("generate", "difficulty-watch", "feeds", "item-batch"),
     E("difficulty-watch", "generate", "observes", "difficulty-report"),
     E("answer-check", "arbiter", "escalates", "accuracy-report"), E("difficulty-watch", "arbiter", "escalates", "difficulty-report"),
     E("answer-check", "teacher-gate", "vetoes", "accuracy-report"),
     E("arbiter", "teacher-gate", "constrains", "approved-batch"), E("teacher-gate", "stop", "hands_off", "release-decision")],
    ["guideline-pdfs", "satisfaction", "practice-scores"], ["答案与指南不一致", "预算耗尽", "锚点过期"])

BASE["t4"] = {"schema_version": "1.1", "title": "满意度驱动出题", "mode": "graph",
              "root_goal": {"statement": "提高学生满意度", "human_owner": "Bruce", "observable_success": "满意度评分上升"},
              "nodes": [{"id": "gen", "kind": "execution_loop", "responsibility": "出题", "optimizes": "满意度"},
                        {"id": "self-check", "kind": "verification_loop", "responsibility": "出题 Agent 自查格式"},
                        {"id": "pub", "kind": "execution", "responsibility": "自动发布"}],
              "edges": [E("gen", "self-check", "feeds", "items"), E("self-check", "pub", "feeds", "items")]}

# ---------------- t5 / t6 简单任务 ----------------
GOLD["t5"] = {"mode": "loop", "rationale": "单一目标、单一可信反馈（检索结果与表格生成），每周重复；不需要多回路图。"}
BASE["t5"] = {"mode": "graph", "rationale": "多个 Agent 分别检索、翻译、审核、仲裁、推送"}
GOLD["t6"] = {"mode": "direct", "rationale": "一次有界转换，无迭代反馈。"}
BASE["t6"] = {"mode": "graph_plus_loop", "rationale": "设计校验回路与审计回路保证格式"}

if __name__ == "__main__":
    for tid, g in GOLD.items():
        (HERE / "标准答案" / f"golden-{tid}-v0.1.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    for tid, g in BASE.items():
        (HERE / "朴素基线" / f"naive-{tid}-v0.1.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {len(GOLD)} 份标准答案、{len(BASE)} 份朴素基线")
