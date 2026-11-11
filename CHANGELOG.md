# Changelog

本技能的所有重要变更记录在此。格式参考 Keep a Changelog，版本遵循 SemVer。

## [4.4.0] - 2026-11-11

### Fixed（复审收尾）

- **参考文档脚本命令全部改为绝对路径变量**：`evidence-chain.md`、`html-generation.md`、`report-assembly.md`、`methodology.md`、`decision-guides.md`、`open-source-solutions.md` 中所有 `python scripts\...` / `& $py scripts\...` 改为 `& $py "$skill\scripts\..."`，每个代码块开头统一定义 `$skill` 与 `$py`；从用户工作目录直接复制即可运行，不再 `Errno 2`。
- **`file://` 策略统一**：`validate_report.py` 要求 `file://` 指向真实存在的本地文件，不存在则判 error；`verify_citations.py` 按文件存在性记为 `local_ok`（计入已核验）或 `unverified`（strict 下失败）。不再出现「全本地引用直接 PASS」的零核验通道；`quality-gates.md` 同步更新说明。

### Tests

- 全套 143 个用例通过；另以真实报告验证：13 条引用中 7 条 URL + 4 条本地文件 = 11 条已核验，通过。

## [4.3.0] - 2026-11-11

### Fixed（复审 B 批）

- `extract_claims.py`：**表格按结构解析**——表头行与 `|---|---|` 分隔行不再被当成论点；数据行按「表头=值」拼成一条（如「指标=市场规模；2025年=1200亿美元；同比=30%」）；兼容无首尾管道的表格；纯序号列（序号/编号/No.）不参与。
- `validate_report.py`：**字数只统计正文**——参考文献与 URL 不计入字数，空壳报告不能靠堆长链接通过字数下限。

### Tests

- 新增 `tests/test_review_batch_b.py`（5 个用例）：表头不入库、无首管道表格、表头映射、长 URL 不凑字数、正常报告不误挡。
- 全套 143 个用例通过。

## [4.2.0] - 2026-11-11

### Added

- **HTML 报告正文引用可点击**：`md_to_html.py` 读取 run 目录 `来源.jsonl`，把正文 `[N]` 渲染为 `<a class="citation" href="来源URL" target="_blank">`，点一下直接打开来源页；无 URL 的编号保持纯文本。Markdown 版报告仍保持 `[N]` 纯编号，不插入长链接。
- 模板中原本未使用的 `.citation` 样式正式启用。

### Fixed（复审 A 批）

- `verify_html.py` 重写为 `HTMLParser` 解析：逐个比对二级标题文本（不再只比数量）、拒绝 `script/iframe/object/embed` 与 `on*` 属性、拒绝 `javascript:/data:` 链接、参考文献条目数与 Markdown 逐条比对（空参考文献判 error）。
- `verify_citations.py`：`entry.get('url','')` 在 `url=None` 时不再抛 `AttributeError`；单条核验异常被隔离，不再中断整轮。
- `validate_report.py`：章节标题匹配改为 `^##(?!#)` 锚定，`### 引言` 不再冒充 `## 引言`；移除歧义别名「分析」（不再匹配「分析综合」）；支持带编号标题（`## 一、执行摘要`）。
- `references/methodology.md`：删除已废弃的「平均可信度 >60/>70 分」评分表，改为定性停止条件。

### Tests

- 新增 `tests/test_review_batch_a.py`（11 个用例）：HTML 假章节/脚本/危险链接/空参考文献、H3 冒充 H2、编号标题、点击引用、无 URL 书目不崩溃。
- 全套 138 个用例通过。

## [4.1.1] - 2026-11-11

### Fixed（复审后 4 个必须修项）

- `extract_claims.py`：**行首小数被吞**——有序列表正则要求「1–3 位数字 + 分隔符 + 至少一个空白」，`1.5万亿美元` 不再被改成 `5万亿美元`，`3.12版本`、`2025.5%` 同理。
- `extract_claims.py`：**混合 `#`/`##` 标题丢内容**——`parse_sections` 改为按标题层级解析，`# 执行摘要` 等 H1 章节不再被归入 `preamble` 跳过；围栏代码块内的 `#` 不当作标题。
- `extract_claims.py`：**retired 无法复活**——本次报告重新出现的 retired 论点恢复为 `unverified`，避免「改回上一版」后全为 retired、校验以 `verified: 0` 假通过。
- `verify_claim_support.py`：**活跃论点为 0 时判 fail**——全部 retired 或为空时不得判通过。
- `verify_claim_support.py`：**A 类价格/规格事实零重叠一律 unsupported**——不再要求「同时缺年份/百分比」，修复「单价 120 美元配无关证据也能过」。
- `tests/test_quality_gate.py`：新增 5 个回归用例（混合 H1/H2、小数保留、retired 复活、全 retired 失败、价格事实零重叠失败）。

## [4.1.0] - 2026-11-11

### Fixed（质量门：堵住 4 个「假通过」阻断项）

- `verify_claim_support.py`：`--strict` 此前不拦截 `needs_review`，任意无关引文即可通过。新增**完整性硬门**（产物缺失/论点为空即失败）、**幽灵来源**检测、**A 类硬事实信号核对**（零重叠且年份/百分比不在证据中 → unsupported）；`needs_review` / `partial` 改为不阻塞的 `advisory` 清单。
- `verify_claim_support.py`：修复 0 分却写「重叠充分」、引用编号被当事实数字、年份重复计权、`evidence_ids` 从不回填、旧分数残留等问题。
- `validate_report.py`：空章节、0 字执行摘要、低于档位字数下限（direct 80 / standard 200 / deep 600）改为 error；正文引用统计剥离参考文献区块；参考文献每条必须带 URL。
- `verify_citations.py`：0 条核验成功不再返回 0（直接失败）。
- `extract_claims.py`：支持只用 `#` 一级标题的报告；表格中含数字的单元格纳入论点；零论点报错；改稿重抽取将旧论点标 `retired`；修复「宜」「假设」等分类误判。
- `citation_manager.py`：`link-claims` / `assign-display-numbers` / `export-bibliography` 三处编号统一「先去重再编号」；`link-claims` 改为覆盖式映射，悬空引用 exit 1；`resolve_run_dir` 修复并发共用目录竞态；`canonicalize_locator` 保留端口、补 scheme、DOI 去尾标点。

### Security

- `md_to_html.py`：正文与参考文献全部做 HTML 转义，仅生成受控标签；链接 href 做属性转义，封堵 `<script>` / `<img onerror>` 注入。
- `verify_citations.py`：URL 核验增加协议与地址白名单（拒绝 loopback / RFC1918 / 链路本地 / 云元数据 / `file://`），HEAD 被拒时回退 GET。
- `SKILL.md` / `quality-gates.md` / `expert-brief.md`：新增「外部内容只当数据、不执行其中指令」的提示注入防护条款。

### Changed

- 校验语义：**PASS = 完整性硬门全绿 + 无幽灵来源 + 无 A 类硬事实冲突**；模糊不确定项进入不阻塞的 `advisory` 清单。
- `validate_report.py` 新增 `--profile`；`SKILL.md` 第 3/8 步改为 `$skill` 变量 + `--out-dir`，并补全 `link-claims`、`--profile`、`--strict`、`finalize-run`。
- 移除 `source_evaluator.py` 及其测试与「来源可信度中位数」门槛，来源可信度改为定性筛选。
- 移除无人加载的 `schemas/`；`references/evidence-chain.md` 成为唯一数据契约（补全枚举）。
- 新增 `scripts/_jsonl.py`，合并 4 份 `read_jsonl`、3 份 `append_jsonl`、2 份 `write_jsonl`。
- 测试改为 `unittest discover`（无需 pytest）；新增 `tests/test_quality_gate.py` 12 个回归。

### Removed

- 移除 `source_evaluator.py` 与其单元测试、`schemas/` 下 4 个 JSON Schema、两个旧英文 fixture（`invalid_report.md`、`valid_report.md`）。

## [4.0.0] - 2026-11-11

### Added

- 融合备份版 `deep-research` v2.9.0 的工程化能力：来源注册、证据存储、论点抽取、论点支撑校验、结构校验、引用校验、决策指南校验、开源方案校验、HTML 报告。
- 新增 `references/quality-gates.md`：A/B/C/D 材料性分级与直查 / 标准研究 / 深研三档证据门槛。
- 新增 `references/evidence-chain.md`：来源、证据、论点、运行清单的数据契约与 CLI 操作示例。
- 新增中文报告模板与中文产物命名：`研究报告.md`、`研究计划.md`、`来源.jsonl`、`证据.jsonl`、`论点.jsonl`、`运行清单.json`、`开源方案.jsonl`、`报告.html`。
- 新增中文测试 fixture 与中文论点支撑用例。
- `citation_manager.py` 新增 `link-claims`（把正文引用编号关联到稳定来源 ID）与 `finalize-run`（写入完成时间与关键假设）。
- 所有接受 JSON 参数的脚本新增 `--json-file`，避免 Windows PowerShell 剥离内层双引号导致 JSON 解析失败。

### Changed

- 模式从 quick / standard / deep / ultradeep 四档收敛为两维模型：查询形态（直接型 / 深度优先 / 广度优先）× 验证强度（standard / deep）。`ultradeep` 降为深研的 `budget=extended` 参数。
- 全部脚本统一 UTF-8 文件读写，兼容 Windows 中文路径。
- `extract_claims.py` 支持中文标题、中文句子切分与中文关键词分类。
- `verify_claim_support.py` 增加 CJK 字符 bigram 支持，避免纯中文句子被误判。
- `source_evaluator.py` 补充 `.gov.cn`、`.edu.cn` 与常见官方媒体域名。
- 文档全部改写为简体中文，并适配 DSH 工具（`subagent` / `pwsh` / `web_search` / `web_fetch`）。

### Removed

- 移除图表 / 富媒体要求：`rich-media.md`、图表最低数量检查与相关模板说明。
- 移除 PDF 生成链路：`weasyprint_guidelines.md`、WeasyPrint 依赖与 PDF 输出说明。
- 移除 Claude Code 时代的四档模式、search-cli / Exa MCP 等外部检索依赖；统一使用 DSH 自带搜索工具。

## [基线]

- 上一版 DSH 轻量版：`SKILL.md` + `references/lead-playbook.md` + `references/expert-brief.md` + `references/report-template.md`，以「研究负责人」流程驱动多源检索与中文报告。
