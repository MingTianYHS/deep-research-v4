# Changelog

本技能的所有重要变更记录在此。格式参考 Keep a Changelog，版本遵循 SemVer。

## [4.0.0] - 2026-11-11

### Added

- 融合备份版 `deep-research` v2.9.0 的工程化能力：来源注册、证据存储、论点抽取、论点支撑校验、结构校验、引用校验、决策指南校验、开源方案校验、HTML 报告。
- 新增 `references/quality-gates.md`：A/B/C/D 材料性分级与直查 / 标准研究 / 深研三档证据门槛。
- 新增 `references/evidence-chain.md`：来源、证据、论点、运行清单的数据契约与 CLI 操作示例。
- 新增中文报告模板与中文产物命名：`研究报告.md`、`研究计划.md`、`来源.jsonl`、`证据.jsonl`、`论点.jsonl`、`运行清单.json`、`开源方案.jsonl`、`报告.html`。
- 新增中文测试 fixture 与中文论点支撑用例。

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
