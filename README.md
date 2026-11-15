# Graph Engineering Architect Plus v1.1

> 设计会自我改进、但不会学会骗自己的 Agent Graph。

一个 Codex / Claude Code Skill + 单文件零依赖 CLI（`skill/scripts/geaplus-v1.1.py`），五个命令：`classify` `validate` `diagnose` `mermaid` `simulate`。

## 能做什么
1. **validate**：硬约束校验。锚点写保护、验证者必须拿到锚点且有否决权、制造者不能自评、共享来源互证、指标必须配反指标、多检查者需仲裁、高风险动作前置人工门、有界环与出口、可收束、单写者、汇合完整；v1.1 再加反指标/审计必备、装饰图、元回路劫持、快慢节奏搅动、看守剧场、仲裁优先级、TODO 残留。
2. **diagnose**：识别 11 类病灶（刷分、目标错位、回路冲突、测量过期、循环互证、元回路劫持、装饰图、节奏搅动、局部成功全局受损、看守剧场、共识即完成），按修复顺序排序，先修最底层。可读运行日志。
3. **init**：生成 `.graph/<名字>/` 四件套（graph.json、graph-spec.md、validation-report.md、handoff.md），TODO 不填完过不了校验。
4. **simulate**：拓扑批次模拟，反馈边与调度依赖分离；只证明调度与失败传播，永不声明领域完成。
5. **mermaid**：导出拓扑图。
6. **classify**：保守判断 direct / loop / graph。
7. 兼容 `version: 1` 旧格式与 1.0 Spec 字段，自动适配。
8. 示例：FAERS/JADER 药物警戒论文图（正例）、自我确认反例、急诊创伤病历质控图（旧格式；结构字段齐全，但验证者没拿到锚点、回环无上限，附修复版）。
9. 33 个回归测试。

## 快速开始
```bash
T=skill/scripts/geaplus-v1.1.py
python3 $T validate examples/faers-manuscript-graph-v1.1.json
python3 $T diagnose examples/broken-circular-graph-v1.0.json --today 2026-11-15
python3 $T mermaid  examples/faers-manuscript-graph-v1.1.json
python3 tests/test-geaplusv1.1.py -v
python3 $T validate examples/legacy-trauma-audit-graph-v1.1.json          # 字段齐全但有结构漏洞
python3 $T validate examples/legacy-trauma-audit-graph-repaired-v1.1.json
```

## 安装为 Skill
```bash
cp -R skill ~/.codex/skills/graph-engineering-architect-plus     # Codex
cp -R skill ~/.claude/skills/graph-engineering-architect-plus    # Claude Code
```

## 边界
结构校验只证明契约完整，不证明领域结论真实、锚点在现实中独立或任务已完成。投稿、推送、发布、删除等外部动作必须单独授权。

## 致谢
设计思路受 Anita Yin 的 graph-engineering-architect 启发；不变量思想参考 [luxiaolei/graph-engineering](https://github.com/luxiaolei/graph-engineering)（Apache-2.0）。本仓库代码、文档与示例为独立编写。

## 许可证
MIT
