# 超长报告续写协议

**何时读取**：预计报告超过 18000 字、单轮输出接近上限，或需要把剩余章节交给另一个子代理接着写时读取。

**用途**：定义续写状态文件、交接顺序、质量门槛与收尾责任，保证多轮写作后报告结构、文风、引用与证据链连续。

## 触发条件

出现任一情况即启用续写协议：

- 按提纲估算全文超过 18000 字；
- 单次写入接近输出上限，出现截断风险；
- 已收集材料过多，继续在同一上下文中写作会挤压输出空间。

## 续写策略

1. 先按 `references/report-assembly.md` 生成前面若干章节，总量控制在 18000 字以内。
2. 在 run 目录写入 `续写状态.json`，保存进度、产物路径、研究上下文与下一批章节计划。
3. 用 `subagent` 派发续写子代理，`prompt` 指向状态文件与现有报告。
4. 续写子代理读取状态 → 生成下一批章节 → 更新状态。DSH 默认 `maxDepth=1`，续写子代理不能再派下一棒；每批完成后由研究负责人检查状态，再决定是否派下一个子代理。
5. 循环直到全部章节完成，最后由负责人或最后一个续写子代理收尾。

## 续写状态文件

**位置**：`research\<主题>_研究_<YYYYMMDD>\续写状态.json`，与报告放在同一 run 目录。不要把状态写到用户主目录或技能安装目录。

```json
{
  "version": "4.3.0",
  "report_id": "唯一标识",
  "file_path": "research\\<主题>_研究_<YYYYMMDD>\\研究报告.md",
  "query_type": "depth",
  "rigor": "deep",
  "budget": "normal",
  "progress": {
    "sections_completed": ["标题与执行摘要", "背景", "发现 1"],
    "total_planned_sections": 12,
    "chars_so_far": 12000,
    "continuation_count": 1
  },
  "artifacts": {
    "sources_path": "research\\<主题>_研究_<YYYYMMDD>\\来源.jsonl",
    "evidence_path": "research\\<主题>_研究_<YYYYMMDD>\\证据.jsonl",
    "claims_path": "research\\<主题>_研究_<YYYYMMDD>\\论点.jsonl",
    "run_manifest_path": "research\\<主题>_研究_<YYYYMMDD>\\运行清单.json"
  },
  "research_context": {
    "research_question": "原始研究问题",
    "key_themes": ["主题一", "主题二"],
    "main_findings_summary": [
      "发现 1：100 字以内摘要",
      "发现 2：100 字以内摘要"
    ],
    "narrative_arc": "middle"
  },
  "quality_metrics": {
    "avg_chars_per_finding": 1500,
    "citation_density": 5.2,
    "prose_vs_bullets_ratio": "85% 段落",
    "writing_style": "精确、数据驱动、段落为主"
  },
  "next_sections": [
    {"id": 4, "type": "finding", "title": "发现 2", "target_chars": 1500},
    {"id": 5, "type": "synthesis", "title": "分析综合", "target_chars": 1000}
  ]
}
```

## 派发续写子代理

用 `subagent` 发起，`prompt` 使用以下结构并替换方括号内容：

```text
你是深度研究续写子代理（deep-research-continuation），负责继续一份未完成的中文研究报告。

执行步骤：
1. 读取续写状态：[run目录]\续写状态.json
2. 读取现有报告：[file_path]
3. 读取最后 3 个已完成章节，模仿其句式、术语密度、引用位置与段落过渡
4. 加载研究上下文：主题、叙事位置、写作风格
5. 从 artifacts.sources_path 读取来源表，使用稳定 source_id；显示编号用 citation_manager.py 重新生成

任务：生成 next_sections 中的下一批章节，单节不超过 2000 字，追加写入报告文件。

质量门槛：
- 每节字数在 avg_chars_per_finding 的 ±20% 以内
- 引用密度与既有章节相差不超过 0.5 处/千字
- 段落占正文 80% 以上
- 每节必须回扣 key_themes 中的至少一个主题

完成后：更新 续写状态.json；如果还有剩余章节，报告「待续」及下一批章节；如果已完成，生成完整参考文献、运行校验并说明结果。
```

## 续写质量协议

### 上下文加载（关键）

1. 读取 `续写状态.json`，恢复研究问题、主题、进度、产物路径与文风指标。
2. 读取现有 `研究报告.md`，重点看最后 3 个完成章节。
3. 提取可复用的写作特征：句子长度、术语密度、引用插入位置、段落过渡方式。
4. 确认叙事位置：开头、中段还是结尾，避免重复或提前收束。

### 生成前检查

- [ ] 已加载研究问题、核心主题与叙事弧线。
- [ ] 已阅读最后 3 个章节，确认文风与论证进度。
- [ ] 已读取 `来源.jsonl`，按稳定 `source_id` 取来源，不依赖旧编号。
- [ ] 已确认本批章节的目标字数与质量指标。
- [ ] 已确认 `证据.jsonl` 中存在支撑本批论点的证据。

### 每节生成与检查

1. 生成一节内容。
2. 检查：字数 ±20%、引用密度匹配、段落占比 ≥80%、主题关联明确、文风一致。
3. 任一项不达标就重写该节。
4. 通过后追加写入报告并更新 `续写状态.json`。

### 交接判断

计算：当前字数 + 剩余章节数 × 平均每节字数。

- 总量 < 18000 字：一次写完剩余章节并收尾。
- 总量 > 18000 字：只写一部分，更新 `续写状态.json`，由负责人再派下一个续写子代理。

### 最后一批的责任

- 写完剩余章节。
- 生成完整参考文献，覆盖正文所有 `[N]`，不得缺号、截断或写区间。
- 从头通读全文，检查章节衔接与重复。
- 按 `references/quality-gates.md:37-45` 的完整清单重跑校验：`extract_claims.py` → `citation_manager.py link-claims` → `verify_claim_support.py --profile <档位> --strict` → `validate_report.py --profile <档位>` → `verify_citations.py --strict`。
- 运行 `citation_manager.py finalize-run --dir "[run目录]"` 写入完成时间，删除 `续写状态.json`。
- 向用户报告最终文件路径与简要结论。

## 用户沟通

派发续写后，用中文简要说明进度，不要暴露内部调度细节：

```text
报告生成：第 1 部分完成（N 节，约 X 字）
已交给续写子代理继续，下一批：[章节列表]
整体进度：约 X%
```

全部完成后只需报告最终报告路径、核心结论与局限。
