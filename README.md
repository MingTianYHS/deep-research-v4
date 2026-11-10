# deep-research（DSH 技能）

把原 deep-research 插件移植为 DSH 可直接加载的技能包：以「研究负责人」方法论驱动多源检索、交叉验证与带引用研究报告的生成。

## 安装位置

本目录应位于 DSH 技能根目录下，即：

```
C:\Users\Daybreak\.agents\skills\deep-research\
├─ SKILL.md
├─ README.md
└─ references\
   ├─ lead-playbook.md
   ├─ expert-brief.md
   └─ report-template.md
```

DSH 扫描技能根目录，识别包含 `SKILL.md` 且 frontmatter 含 `name` 与 `description` 的目录。本技能 `name` 为 `deep-research`，目录就位后即可被扫描发现。

## 配套技能

中文信息检索依赖同目录下的 `wechat-article-search` 技能（微信公众号文章检索，基于搜狗微信搜索）。本技能在流程中会通过 `skill` 工具加载它；请确保 `C:\Users\Daybreak\.agents\skills\wechat-article-search\` 存在且包含 `SKILL.md` 与 `scripts\sogou_search.py`。

## 使用示例

直接在对话中提出研究需求即可触发，例如：

- 「帮我深度研究一下 AI Agent 的发展趋势，出一份带引用的报告。」
- 「调研 2026 年国内新能源汽车行业的竞争格局，重点看价格战和出海。」
- 「比较三大云厂商在 AI 基础设施上的产品、价格和生态，用表格对比。」
- 「核查这条行业新闻里的数据是否可靠，并给出原始来源。」

技能会先判断是否需要澄清（最多 3 个问题），然后规划研究、并行派发子代理检索、综合撰写报告，最终在当前工作目录生成：

- `research_plan_<topic_slug>.md`：研究计划（过程文件）。
- `research_report_<topic_slug>.md`：最终研究报告。

## 文件说明

- `SKILL.md`：技能入口与路由，说明触发条件、两阶段流程、DSH 工具映射、质量门槛和参考文件加载时机（控制在 7500 字节以内，便于技能加载器完整载入）。
- `references/lead-playbook.md`：完整研究负责人手册，包含澄清规则、查询类型判定（深度优先/广度优先/直接型）、研究计划要求、子代理数量与任务分配、报告结构与引用规范。
- `references/expert-brief.md`：子代理任务简报模板，含 `{TASK}` 占位符，供 `subagent` 的 `prompt` 直接套用。
- `references/report-template.md`：研究报告结构模板与字数区间。

## 约束与说明

- 子代理数量默认：简单 1 个、标准 3 个、复杂最多 5 个（DSH 默认 `maxActiveSubagents=8`、`maxDepth=1`）。
- 报告默认使用小标题和段落，少用项目符号；仅当用户要求列表/排名或结构化对比确有必要时使用列表或表格。
- 所有引用必须来自真实访问过的 URL，禁止编造。
- 计划与报告均写入当前工作目录，不使用平台专属产物目录或模板变量。
