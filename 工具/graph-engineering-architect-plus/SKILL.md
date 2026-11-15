---
name: graph-engineering-architect-plus
description: Design, assess, verify, diagnose, and repair grounded graphs of interacting improvement loops. Use for Agent frameworks, research pipelines (manuscripts, pharmacovigilance, model competitions), quality-control systems, long-running automation, self-improving workflows, or multi-agent architectures where several objectives, metrics, cadences, verifiers, approval gates, or feedback loops interact. Also use when a loop is gaming its metric, optimizing the wrong target, conflicting with another loop, trusting decayed measurements, letting the improver rewrite its own judge, or becoming a circular network of mutual confirmation. Do not use for a single bounded action or a simple workflow with one reliable feedback signal.
---

# Graph Engineering Architect Plus v1.3

一句话：多回路系统的问题不在于 Agent 不够多，而在于谁能约束谁、谁拿着独立于优化者的证据。本 Skill 把这些关系写成可校验的图，并让脚本自动找出“系统会骗自己”的结构漏洞。

## 交付前必须答得出的问题

- **结果**：我们到底在改善哪个真实结果？谁对它负责？什么证据算成功？
- **职责**：谁动手、谁检查、谁审计、谁裁决、谁签字？
- **证据流**：每条边上流过的是哪份文件或哪个结论？
- **防作弊**：哪个指标最容易被刷？哪个反指标会拆穿它？
- **扎根**：哪份证据是优化者碰不到、改不了的？
- **冻结**：哪些规则和锚点不允许系统自己改？
- **冲突**：两个回路拉扯时，按什么顺序取舍？
- **收尾**：什么时候停、退、升级、交给谁？

根判断归人。Agent 只能**提议**改目标、锚点、权限和冻结规则，**应用**需要明确批准。

## 选最小够用的架构

- **Direct**：一次有界动作，没有有用的迭代反馈 → 不建图。
- **Single loop**：一个主目标、一个可信验证者、冲突少、重试有意义 → 用单回路（需要持久状态时配合 loop-engineering-co-builder）。
- **Graph of loops**：多个相互作用的目标或速度；指标可被钻空子；需要独立验证或审计；回路会冲突；目标需要受治理地修订；或自我改进会改动机器本身。

步骤多、工具多、Agent 多都不等于需要图。图的理由是**相互作用的控制责任 + 显式治理边**。`geaplus classify` 可做保守分类；找不到执行者无法改写的证据源 → `blocked`。

## 模式

| 模式 | 用途 | 命令 |
|---|---|---|
| assess | direct / loop / graph 哪个够用 | `classify` |
| design | 新建或修订图契约，不执行领域任务 | `init` → 填写 → `validate` → `mermaid` |
| verify | 检查独立性、扎根性、治理与失败覆盖 | `validate` |
| diagnose | 回路“越跑越好看但不对劲” | `diagnose [--run log]` |
| repair | 按修复顺序做最小结构修正 | 改 Spec 后再 `validate` + `diagnose` |

含糊请求默认 assess，新图默认 design。权限、锚点、验收标准、审批门未落定前，不执行领域流程。

## 设计流程

1. **根结果**：一个真实结果、人类 owner、可观察成功标准、明确排除项（out_of_scope）。区分结果指标与代理指标。“更好”无法落到可观察证据 → 停在设计稿。
2. **节点 = 职责**：execution_loop、verification_loop、counter_metric_loop、audit_loop、arbitration、governance_loop、anchor、human_gate、stop_handoff（另兼容 execution、synthesis、reducer）。节点不等于 Agent，可以是人、确定性测试、服务或模型。
3. **边 = 控制含义**：feeds、observes、verifies、constrains、vetoes、escalates、arbitrates、revises、anchors、hands_off，每条边写明 artifact。拒绝“沟通”“协作”这类装饰边。可靠性在于谁能约束或否决谁。
4. **扎根**：至少一个优化回路无法生成、改写或选择性隐藏的现实锚点（执行过的测试、留出数据、真实病例计数、外部登记结果、签字审批、独立来源数据）。记录 source、evidence、owner、freshness_rule、frozen，v1.1 建议加 `max_age_days` + `last_confirmed`。独立性要同时覆盖**评估者**和**数据来源**：另一个 Agent 读同一张坏表不算独立。
5. **分速与授权**：快回路在固定边界内动作；慢回路（审计、治理）审视漂移、取舍和目标有效性。快回路不得改写慢回路的目标、验证者、安全边界或审批规则。冲突发生前就定好仲裁 owner 与 priority_policy。
6. **故障探针**：刷分、优化错目标、局部成功全局受损、测量衰减、共享来源循环互证、元回路削弱测试、快回路搅动慢变量、无独立证据宣告完成。
7. **领域效度**（v1.2）：在 `root_goal.domain` 声明领域（ml_model / evidence_synthesis / clinical_protocol / code_agent / multi_agent_shared / ops_automation），并在 `domain_audits` 把每个必需关注点分给一个有否决/约束/升级权的检查节点。结构正确不等于方法学正确，见 [domain-checklists-v1.2.md](references/domain-checklists-v1.2.md)。
8. **过期锚点**（v1.2）：锚点超过 `max_age_days` 时，不要假装新鲜，也不要只写进说明。设 `revalidation_gate` 指向人工门，并让该门对此锚点喂给的每个检查者都有 vetoes/constrains 边；diagnose 状态为 `pending_revalidation`。还没人确认过的锚点（v1.3）：`last_confirmed` 如实留空，不要编日期；同样设 `revalidation_gate`，diagnose 会判为待首次确认（pending_revalidation），而不是过期。
9. **持久化契约**：`init` 生成 `.graph/<slug>/`（graph.json、graph-spec.md、validation-report.md、handoff.md）。脚手架里的 TODO 会让校验失败，填完才算设计完成。

## 自动硬约束（validate）

兼容格式规则（读取 `version: 1` 旧格式时执行，前缀 `O-`）：必填字段、classification.rationale、out_of_scope、每节点 cadence、arbitration.owner/priority_policy、goal_change=human_approval、stop_conditions 四态、independence_statement、checks 指向真实验证者、无 TODO。

v1.0 新增：锚点写保护 · 验证者必须吃到锚点且有否决权 · 制造者不自评 · 共享来源循环互证 · Goodhart 反指标配对 · 多检查者需仲裁 · 高风险副作用前置人工门 · 有界环与出口 · 可收束 · 单写者 · 汇合完整。

v1.1 新增：
- **E-NOCOUNTER / E-ONELOOP**：最小扎根图必须有反指标或审计回路，且至少两种回路。
- **E-DECORATIVE**：没有任何边带 constrains/vetoes/escalates/arbitrates 权力。
- **E-METACAPTURE**：执行者对验证、锚点、审计、治理节点有 revises/constrains 边，即“改进者能改写自己的裁判”。
- **E-CADENCE**：更快节奏的节点 revises/constrains 更慢节奏的节点（可写 `cadence_tier: fast/medium/slow/governance/human`，否则从 cadence 文字推断）。
- **E-THEATER**：验证者只收到执行者递来的东西，没有独立来源。
- **W-PRIORITY**：多个检查者却没有 priority_policy。
- **E-PLACEHOLDER**：残留 TODO / 待实例化 / 待用户指定。

v1.2 新增：
- **E-STALE**：锚点过期且没有人工门挡住它的使用。
- **E-DOMAIN**：声明的领域缺少必需关注点，或关注点落在执行者/没有牙齿的检查者上。
- **W-NODOMAIN**：图模式未声明领域（提醒，不阻断）。

v1.3 修正：从未确认过的锚点（`last_confirmed` 为空）若有能挡住其所有检查者的 `revalidation_gate`，diagnose 判为 `pending_revalidation`；没有这样的门才报 decayed_measurement（"从未确认且没有东西阻止使用"）。

## 诊断与修复顺序（diagnose）

识别 11 类病灶，并按修复顺序给出 `repair_layer`，先修最底层：

1. 根结果与归属（wrong_target）
2. 现实锚点与来源（decayed_measurement、circular_confirmation、completion_by_consensus）
3. 验证者独立性（watcher_theater、meta_loop_capture）
4. 边的权力与仲裁（metric_gaming、loop_conflict、decorative_graph、local_success_global_harm）
5. 节奏分离（cadence_thrashing）
6. 节点实现

结构出问题时，**先修扎根和权力，不要先加 Agent 或重试**。

## 与 Loop Engineering 的分工

本 Skill 管图的分类、拓扑、边语义、扎根、跨回路治理、节奏分离与仲裁；单个有界回路的内部契约（状态、权限、迭代预算、证据、停止、恢复、交接）交给 loop-engineering-co-builder。先设计图，再只为真正需要持久回路的节点实例化。节点级改进回路不得悄悄修改图级目标、锚点、权限、Skill、AGENTS.md、记忆或生产配置。

## 完成规则

不能因为所有节点都跑完或所有报告都同意就判完成。需要：可观察的根结果证据；至少一个独立且新鲜的现实锚点；必需验证通过；冲突与反信号已解决或由人类 owner 明确接受；冻结规则未变（或变更有批准记录）；可用的终态交接。缺任一项，如实报告：designed、blocked、failed、stalled、budget_exhausted。`simulate` 只证明调度与失败传播，永远不声明领域完成。

## 命令

```bash
T=scripts/geaplus-v1.3.py
python3 $T init "<根结果>" --root <项目根> --slug <名字>
python3 $T validate <项目根>/.graph/<名字> [--today 2026-11-15]   # 也接受 json 文件；version:1 旧格式自动适配
python3 $T diagnose graph.json --today 2026-11-15 [--run run-log.json]
python3 $T mermaid  graph.json > graph.mmd
python3 $T simulate graph.json [--fail-node ID]
python3 $T classify brief.json
```

参考：[design-principles-v1.0.md](references/design-principles-v1.0.md)（每条检查背后的理由、锚点五问、反指标配对、快慢分层、故障手册、修复顺序）· [graph-spec-v1.2.md](references/graph-spec-v1.2.md)（字段说明与旧格式映射）· [domain-checklists-v1.2.md](references/domain-checklists-v1.2.md)（各领域必需的效度检查）。

致谢：设计思路受 Anita Yin 的 graph-engineering-architect 启发。
