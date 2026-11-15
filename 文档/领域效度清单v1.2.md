# 领域效度清单 v1.2

结构对了不等于方法学对了。v0.2 评测显示：带不带本 Skill，模型都常漏掉领域专属的效度检查（例如 meta 分析的偏倚/异质性审计）。所以 v1.2 让你声明领域，并把每个关注点钉到一个有否决权的检查节点上。

## ml_model（预测模型重训/上线）
- **temporal_holdout**：验收只用训练窗口之后的数据，留足结局成熟期；训练方读不到。
- **calibration**：校准斜率/截距、Brier；AUC 涨不代表概率可用。
- **subgroup_performance**：预先指定亚组，任何亚组明显下降即否决。
- **drift**：输入分布与结局率漂移监测，漂移超阈值暂停自动重训。

## evidence_synthesis（meta 分析、系统综述、数据提取）
- **independent_extraction**：两人/两个 Agent 各自**从原文**提取，再比对；复核者读提取表不算独立。
- **risk_of_bias**：RoB 2 / ROBINS-I / NOS 等，按研究打分并做敏感性分析。
- **heterogeneity**：I²、τ²、预测区间，预先指定亚组/元回归。
- **publication_bias**：漏斗图、Egger 等（研究数足够时），或说明不做的理由。

## clinical_protocol（分诊、临床路径、提示词优化用于临床）
- **guideline_currency**：参照标准有日期与复审周期；过期即走 revalidation_gate。
- **under_triage_safety**：低估分级（高危判低危）单独计数，设硬上限，超限否决。
- **real_outcome_anchor**：锚定真实结局（如 30 天 MACE、ICU 转入），不只与旧标准的一致率。

## code_agent（自动修复、自动合并）
- **test_integrity**：既有测试只读；删除/弱化/跳过测试即否决。
- **independent_test_review**：新增测试由修复者之外的人或节点审查。

## multi_agent_shared（多个 Agent 改同一资源）
- **shared_resource_arbitration**：共享标准/清单只有一个写者或由仲裁节点合并，优先级预先写好。
- **safety_counter_metric**：至少一个安全反指标（如 72 小时返诊、死亡、投诉）可否决任一 Agent 的变更。

## ops_automation（备份、定时任务）
通常不需要图；如确需图，无必需关注点。

## 过期锚点
锚点有 `max_age_days` 与 `last_confirmed`。过期时不要假装它新鲜：设 `revalidation_gate` 指向一个人工门，并让这个门对该锚点喂给的每个检查者都有 vetoes/constrains 边。设计可以交付，状态是 `pending_revalidation`，在人工复审前任何验收都被挡住。
