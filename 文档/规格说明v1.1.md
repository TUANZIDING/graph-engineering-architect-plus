# Graph Spec v1.1 字段（向下兼容 agent-builder 的 1.0）

## 顶层
| 字段 | 必填 | 说明 |
|---|---|---|
| schema_version | ✓ | `1.0`（兼容，loop 缺 max_iterations 仅警告）或 `1.1`（严格） |
| title, mode, state | ✓ | mode ∈ direct/loop/linear_workflow/graph/graph_plus_loop/blocked |
| root_goal | ✓ | statement, human_owner, observable_success；**新增可选 metrics[]**（字符串列表，只写指标名）用于目标错位检查；写成对象会报 E-METRICS |
| permissions | ✓ | human_owner, allowed_actions[], forbidden_actions[]（不得重叠） |
| frozen_rules | ✓ | 非空字符串数组 |
| approval | ✓ | status ∈ pending/approved/rejected；approved 需 approved_by |
| budget | ✓ | max_agents, max_concurrency(≤agents), max_retries(≥0), max_cost_units |
| failure_policy, stop_handoff | ✓ | stop_handoff: owner, conditions[], artifact |
| execution_contract | ✓ | external_execution: bool（默认 false） |
| anchors | graph 必填 | node_id, source, evidence_form, owner, freshness_rule, frozen:true；**新增 max_age_days, last_confirmed(YYYY-MM-DD)** |
| external_inputs | 可选（新增） | 由外部提供、无需边送达的输入名 |
| reality_evidence | completed 必填 | 现实证据列表 |

## 节点
必填：id, kind, responsibility, owner, contract.inputs[], contract.outputs[]

kind ∈ execution, execution_loop, verification_loop, counter_metric_loop, audit_loop, arbitration, governance_loop, anchor, human_gate, stop_handoff, reducer, synthesis

新增可选字段：
| 字段 | 作用 |
|---|---|
| max_iterations | loop 节点上限（1.1 必填） |
| context_scope | 验证者必须 `fresh-independent` |
| evidence_sources[] | 该节点读取的证据来源；用于循环互证检测 |
| optimizes | 该节点优化的指标名；触发 Goodhart 配对与目标错位检查 |
| side_effect | none / internal-reversible / high-risk |
| writes[] | 写入的资源；用于单写者检查 |

## 边
from, to, relation, artifact。relation ∈ feeds, observes, verifies, constrains, vetoes, escalates, arbitrates, revises, anchors, hands_off。
`observes`、`revises` 为反馈边：参与环检测，不参与调度依赖与并行写判断。

## 运行日志（diagnose --run，可选）
```json
{"node_results": [{"node_id": "x", "score_history": [3, 6, 11], "anchor_agreement": 0.3, "verifier_agreed_without_anchor": false}]}
```

## 旧格式（version: 1）自动适配
| 旧格式字段 | 内部字段 |
|---|---|
| graph_id | title |
| classification.mode / rationale | mode（rationale 由 O-RATIONALE 检查） |
| root_goal.owner / success_definition / out_of_scope | human_owner / observable_success / permissions.forbidden_actions |
| node.inputs / outputs / cadence | contract.inputs / outputs；cadence 用于 E-CADENCE |
| anchors.evidence | evidence_form |
| governance.frozen_items | frozen_rules |
| governance.stop_conditions | failure_policy + stop_handoff.conditions |
| verification.independence_statement | 存在时验证者视为 fresh-independent |

旧格式文件可原样交给 `validate`/`diagnose`/`mermaid`；旧格式规则以 `O-` 前缀报告，v1.x 规则以 `E-`/`W-` 报告。
新增可选：`cadence_tier`（fast / medium / slow / governance / human），arbitration 节点的 `priority_policy`。
