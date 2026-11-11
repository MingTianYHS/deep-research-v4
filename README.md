# deep-research（DSH 深度研究技能）

融合版深度研究技能：以「研究负责人」方法论驱动多源检索、交叉验证与带引用中文报告生成，内置来源 / 证据 / 论点三级证据链与自动校验脚本。

## 安装位置

本目录应位于 DSH 技能根目录下（实际路径以安装位置为准）：

```
<DSH 技能根目录>\deep-research\
├─ SKILL.md
├─ README.md
├─ CHANGELOG.md
├─ references\
│  ├─ lead-playbook.md
│  ├─ expert-brief.md
│  ├─ report-template.md
│  ├─ quality-gates.md
│  ├─ evidence-chain.md
│  ├─ methodology.md
│  ├─ report-assembly.md
│  ├─ html-generation.md
│  ├─ decision-guides.md
│  ├─ open-source-solutions.md
│  └─ continuation.md
├─ scripts\
│  ├─ _console.py
│  ├─ _json_input.py
│  ├─ _jsonl.py
│  ├─ citation_manager.py
│  ├─ evidence_store.py
│  ├─ extract_claims.py
│  ├─ verify_claim_support.py
│  ├─ validate_report.py
│  ├─ verify_citations.py
│  ├─ validate_decision_guide.py
│  ├─ validate_open_source_solutions.py
│  ├─ md_to_html.py
│  └─ verify_html.py
├─ templates\
└─ tests\
```

## 版本与来源

- 版本：4.2.0（复审 A 批：HTML 校验与点击引用）
- 基线：当前 DSH 版 `deep-research` 的「研究负责人」流程 + 备份版 `deep-research` v2.9.0 的工程化工具链
- 许可证：MIT

## Git 回滚

本目录是独立 Git 仓库。`main` 分支保存升级前基线，`merge-deep-research` 分支保存融合版；发布标签为 `v4.0.0`。

```powershell
git log --oneline --decorate
git switch main                    # 查看/回到升级前基线
git switch --detach baseline-before-merge   # 只读查看该基线（推荐）
git switch merge-deep-research     # 回到融合版
```

> `git reset --hard baseline-before-merge` 会**丢弃工作区所有未提交修改**。执行前先 `git status` 确认并备份；需要保留本地改动时用 `git reset --keep`。

## 核心特性

- **两维研究路径**：查询形态（直接型 / 深度优先 / 广度优先）× 验证强度（标准 / 深研），不再使用四档模式。
- **证据链落盘**：`来源.jsonl` → `证据.jsonl` → `论点.jsonl` → `研究报告.md`，可审计、可续写。
- **中文优先**：报告、run 目录、产物文件名全部中文。
- **并行子代理**：标准 3 个、复杂最多 5 个，自包含任务简报。
- **自动校验**：结构、引用、来源、论点支撑、决策指南、开源方案。
- **HTML 报告**：Markdown 转 McKinsey 风格自包含 HTML。
- **无图表 / 无 PDF**：本版本不包含富媒体与 PDF 生成链路。

## 使用示例

直接在对话中提出研究需求即可触发，例如：

- 「帮我深度研究一下 AI Agent 的发展趋势，出一份带引用的报告。」
- 「调研 2026 年国内新能源汽车行业的竞争格局，重点看价格战和出海。」
- 「比较三大云厂商在 AI 基础设施上的产品、价格和生态。」
- 「核查这条行业新闻里的数据是否可靠，并给出原始来源。」

技能会先判断是否需要澄清（最多 3 个问题），然后判定查询形态与验证强度，规划研究、并行派发子代理、写入证据链，最终在当前工作目录生成：

```
research/<主题>_研究_<YYYYMMDD>/
├─ 研究计划.md
├─ 研究报告.md
├─ 来源.jsonl
├─ 证据.jsonl
├─ 论点.jsonl
├─ 运行清单.json
├─ 开源方案.jsonl      # 适用时
└─ 报告.html           # 可选
```

## 运行脚本

核心脚本只依赖 Python 3.9+ 标准库。**始终以用户工作目录为 cwd**，用 `--out-dir` 显式指定 run 目录，不要把产物写进技能安装目录。DSH 中若 `python` 不在 PATH，使用：

```powershell
$skill = "<DSH 技能根目录>\deep-research"
$py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\citation_manager.py" init-run --query "研究问题" --mode <direct|standard|deep> --out-dir "<工作目录>\research\<主题>_研究_<YYYYMMDD>"
```

常用命令见 `references/evidence-chain.md` 第 3 节与 `SKILL.md`「执行流程」第 3、8 步，完整数据契约见 `references/evidence-chain.md`。

## 研究路径

| 实际路径 | 组合 | 适用场景 | 子代理 | 来源预算 |
|---|---|---|---|---|
| 直查 | 直接型 × standard | 单事实、定义、简单核对 | 1 个 | 3–5 |
| 标准研究 | 深度/广度 × standard | 大多数研究请求 | 3 个 | 10–15 |
| 深研 | 深度/广度 × deep | 关键决策、争议大、对比选型、尽调 | 3–5 个 | 20–30 |

`ultradeep` 仅作为深研的 `budget=extended` 参数，不是独立档位。

## 证据门槛摘要

- 所有引用来源必须登记到 `来源.jsonl`。
- A 类硬事实（数字、日期、价格、法规、规格、直接引语）必须有 `证据.jsonl` 原文记录。
- 每条主要结论至少 2 个独立来源簇（标准）/ 3 个（深研）；同一通稿转载算一个簇。
- 交付前运行完整校验链：`extract_claims.py` → `citation_manager.py link-claims` → `verify_claim_support.py --profile <档位> --strict` → `validate_report.py --profile <档位>` → `verify_citations.py --strict`，通过后 `citation_manager.py finalize-run`。
- 详细规则见 `references/quality-gates.md`。

## 约束与说明

- 子代理数量默认：直查 1 个、标准 3 个、复杂最多 5 个（DSH 默认 `maxActiveSubagents=8`、`maxDepth=1`）。
- 报告默认使用中文、小标题加段落，少用项目符号；禁止 emoji。
- 所有引用必须来自真实访问过的 URL，禁止编造。
- 计划、报告与证据文件均写入当前工作目录的 run 目录，不使用平台专属产物目录或模板变量。
- 本版本不生成图表与 PDF；HTML 报告可选生成。

## 测试

测试为 `unittest` 风格，无需安装 pytest：

```powershell
$py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py -m unittest discover -s tests -p "test_*.py" -v
```

若已安装 pytest，`& $py -m pytest tests -q` 同样可用。
