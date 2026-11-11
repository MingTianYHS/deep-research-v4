#!/usr/bin/env python3
"""
Report Validation Script
Ensures research reports meet quality standards before delivery
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List

# The run-directory naming rule is owned by citation_manager; import it instead
# of copying the pattern so the gate and the resolver cannot drift apart.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from citation_manager import check_run_dir  # noqa: E402
from _console import setup_console_encoding  # noqa: E402

# 各验证强度的最低总字数硬下限（低于即 error，防止空壳报告通过）
MIN_WORDS = {'direct': 80, 'standard': 200, 'deep': 600}


class ReportValidator:
    """校验研究报告质量"""

    # 章节标题别名：中文为主，保留英文兼容。
    SECTION_ALIASES = {
        "Executive Summary": ["执行摘要", "摘要", "概要", "Executive Summary"],
        "Introduction": ["引言", "导言", "简介", "Introduction"],
        "Main Analysis": ["主要发现", "正文", "分析", "Main Analysis", "Finding"],
        "Synthesis": ["分析综合", "综合分析", "综合", "Synthesis"],
        "Limitations": ["局限与说明", "局限性", "研究局限", "局限", "Limitations"],
        "Recommendations": ["建议", "推荐建议", "Recommendations"],
        "Bibliography": ["参考文献", "参考资料", "References", "Bibliography"],
        "Methodology": ["方法论附录", "方法论", "研究方法", "Appendix: Methodology", "Methodology"],
        "Conclusion": ["结论", "Conclusion"],
        "Decision Guide": ["决策指南", "Decision Guide"],
        "Open-Source Solutions": ["开源方案全景", "Open-Source Solutions Landscape"],
    }

    @classmethod
    def _alias_group(cls, section: str) -> str:
        """Regex alternation matching any accepted spelling of a section name."""
        return "|".join(re.escape(alias) for alias in cls.SECTION_ALIASES.get(section, [section]))

    @classmethod
    def _section_body_pattern(cls, section: str) -> str:
        """Pattern capturing a section body up to the next level-two heading."""
        return rf'##\s*(?:{cls._alias_group(section)})[^\n]*\n(.*?)(?=\n##\s|\Z)'

    @staticmethod
    def _count_words(text: str) -> int:
        """Count Latin tokens and each CJK character for multilingual reports."""
        cjk = len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff]', text))
        latin = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text))
        return cjk + latin

    def __init__(self, report_path: Path, profile: str = 'standard'):
        # 库方式调用（测试/其它脚本 import）也要有编码兜底，不能只靠 main()
        setup_console_encoding()
        self.report_path = report_path
        self.profile = profile if profile in MIN_WORDS else 'standard'
        self.content = self._read_report()
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def _body_without_bibliography(self) -> str:
        """剥离参考文献区块，避免参考文献编号冒充正文引用。"""
        return re.sub(
            self._section_body_pattern("Bibliography"),
            '',
            self.content,
            flags=re.DOTALL | re.IGNORECASE,
        )

    def _read_report(self) -> str:
        """Read report file"""
        try:
            with open(self.report_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"❌ 错误：无法读取报告：{e}")
            sys.exit(1)

    def validate(self) -> bool:
        """执行全部校验。"""
        print(f"\n{'='*60}")
        print(f"正在校验报告：{self.report_path.name}")
        print(f"{'='*60}\n")

        checks = [
            ("执行摘要", self._check_executive_summary),
            ("必需章节", self._check_required_sections),
            ("引用", self._check_citations),
            ("参考文献", self._check_bibliography),
            ("占位符文本", self._check_placeholders),
            ("内容截断", self._check_content_truncation),
            ("字数", self._check_word_count),
            ("来源数量", self._check_source_count),
            ("失效链接", self._check_broken_references),
            ("输出位置", self._check_output_location),
        ]

        for check_name, check_func in checks:
            print(f"⏳ 检查：{check_name}...", end=" ")
            passed = check_func()
            if passed:
                print("✅ PASS")
            else:
                print("❌ FAIL")

        self._print_summary()

        return len(self.errors) == 0

    @staticmethod
    def _bibliography_entries(bib_section: str) -> list[str]:
        """抽取参考文献编号；兼容 [N] 与 N. 两种编号格式。"""
        entries = []
        for line in bib_section.split('\n'):
            stripped = line.strip()
            match = re.match(r'^\[(\d+)\]', stripped) or re.match(r'^(\d+)[.、)）]\s+', stripped)
            if match:
                entries.append(match.group(1))
        return entries

    def _check_executive_summary(self) -> bool:
        """检查执行摘要存在，并给出字数提示。"""
        pattern = self._section_body_pattern("Executive Summary")
        match = re.search(pattern, self.content, re.DOTALL | re.IGNORECASE)

        if not match:
            self.errors.append("缺少「执行摘要」章节")
            return False

        summary = match.group(1).strip()
        word_count = self._count_words(summary)

        if word_count == 0:
            self.errors.append("执行摘要为空（0 字）：空壳报告不得通过")
            return False

        if word_count > 400:
            self.warnings.append(f"执行摘要偏长：{word_count} 字（建议 ≤400）")

        if word_count < 50:
            self.warnings.append(f"执行摘要偏短：{word_count} 字（建议 ≥50）")

        return True

    def _check_required_sections(self) -> bool:
        """检查必需章节是否齐全。"""
        required = [
            "Executive Summary",
            "Introduction",
            "Main Analysis",
            "Synthesis",
            "Limitations",
            "Recommendations",
            "Bibliography",
            "Methodology"
        ]

        # 建议性章节缺省只给警告，不硬失败
        recommended = ["Conclusion"]

        missing = []
        for section in required:
            if not re.search(rf'##.*(?:{self._alias_group(section)})', self.content, re.IGNORECASE):
                missing.append(section)

        if missing:
            self.errors.append(f"缺少章节：{', '.join(missing)}")
            return False

        missing_recommended = []
        for section in recommended:
            if not re.search(rf'##.*(?:{self._alias_group(section)})', self.content, re.IGNORECASE):
                missing_recommended.append(section)

        if missing_recommended:
            self.warnings.append(f"缺少建议章节：{', '.join(missing_recommended)}")

        # 必需章节不仅要有标题，还必须有正文（防「只有标题的空壳」）
        empty_sections = []
        for section in required:
            m = re.search(self._section_body_pattern(section), self.content,
                          re.DOTALL | re.IGNORECASE)
            if m and not m.group(1).strip():
                empty_sections.append(section)
        if empty_sections:
            self.errors.append(f"必需章节正文为空：{', '.join(empty_sections)}")
            return False

        return True

    def _check_citations(self) -> bool:
        """Check citation format and presence（只统计正文，不含参考文献）"""
        body = self._body_without_bibliography()
        citations = re.findall(r'\[(\d+)\]', body)

        if not citations:
            self.errors.append("报告中没有任何引用")
            return False

        unique_citations = set(citations)

        if len(unique_citations) < 10:
            self.warnings.append(f"仅引用 {len(unique_citations)} 个不同来源（建议 ≥10）")

        # Check for consecutive citation numbers
        citation_nums = sorted([int(c) for c in unique_citations])
        if citation_nums:
            max_citation = max(citation_nums)
            expected = set(range(1, max_citation + 1))
            missing = expected - set(citation_nums)

            if missing:
                self.warnings.append(f"引用编号不连续，缺少：{sorted(missing)}")

        return True

    def _check_bibliography(self) -> bool:
        """Check bibliography exists, matches citations, and has no truncation placeholders"""
        pattern = self._section_body_pattern("Bibliography")
        match = re.search(pattern, self.content, re.DOTALL | re.IGNORECASE)

        if not match:
            self.errors.append("缺少「参考文献」章节")
            return False

        bib_section = match.group(1)

        # CRITICAL: Check for truncation placeholders (2025 CiteGuard enhancement)
        truncation_patterns = [
            (r'\[\d+-\d+\]', 'Citation range (e.g., [8-75])'),
            (r'Additional.*citations', 'Phrase "Additional citations"'),
            (r'would be included', 'Phrase "would be included"'),
            (r'\[\.\.\.continue', 'Pattern "[...continue"'),
            (r'\[Continue with', 'Pattern "[Continue with"'),
            (r'etc\.(?!\w)', 'Standalone "etc."'),
            (r'and so on', 'Phrase "and so on"'),
        ]

        for pattern_re, description in truncation_patterns:
            if re.search(pattern_re, bib_section, re.IGNORECASE):
                self.errors.append(f"⚠️ CRITICAL: Bibliography contains truncation placeholder: {description}")
                self.errors.append(f"   This makes the report UNUSABLE - complete bibliography required")
                return False

        # Count bibliography entries [1] or 1.
        bib_entries = self._bibliography_entries(bib_section)

        if not bib_entries:
            self.errors.append("参考文献没有条目")
            return False

        # Check citation number continuity (no gaps)
        bib_nums = sorted([int(n) for n in bib_entries])
        if bib_nums:
            expected = list(range(1, bib_nums[-1] + 1))
            actual = bib_nums
            missing = [n for n in expected if n not in actual]
            if missing:
                self.errors.append(f"参考文献编号不连续：缺少 {missing}")
                return False

        # 每条参考文献必须带可访问链接（无 URL 的条目不得通过）
        no_url = []
        for raw_line in bib_section.split('\n'):
            line = raw_line.strip()
            m = re.match(r'^\[(\d+)\]', line) or re.match(r'^(\d+)[.、)）]\s+', line)
            if m and not re.search(r'https?://', line):
                no_url.append(m.group(1))
        if no_url:
            self.errors.append(f"参考文献条目缺少 URL：{sorted(no_url, key=int)}")
            return False

        # Find citations in text（只算正文，不含参考文献自身）
        text_citations = set(re.findall(r'\[(\d+)\]', self._body_without_bibliography()))
        bib_citations = set(bib_entries)

        # Check all citations have bibliography entries
        missing_in_bib = text_citations - bib_citations
        if missing_in_bib:
            self.errors.append(f"正文引用在参考文献中缺失：{sorted(missing_in_bib)}")
            return False

        # Check for unused bibliography entries
        unused = bib_citations - text_citations
        if unused:
            self.warnings.append(f"参考文献条目未在正文引用：{sorted(unused)}")

        return True

    def _check_placeholders(self) -> bool:
        """Check for placeholder text that shouldn't be in final report"""
        placeholders = [
            'TBD', 'TODO', 'FIXME', 'XXX',
            '[citation needed]', '[needs citation]',
            '[placeholder]', '[TODO]', '[TBD]'
        ]

        found_placeholders = []
        for placeholder in placeholders:
            if placeholder in self.content:
                found_placeholders.append(placeholder)

        if found_placeholders:
            self.errors.append(f"发现占位符文本：{', '.join(found_placeholders)}")
            return False

        return True

    def _check_content_truncation(self) -> bool:
        """Check for content truncation patterns (2025 Progressive Assembly enhancement)"""
        truncation_patterns = [
            (r'Content continues', 'Phrase "Content continues"'),
            (r'Due to length', 'Phrase "Due to length"'),
            (r'would continue', 'Phrase "would continue"'),
            (r'\[Sections \d+-\d+', 'Pattern "[Sections X-Y"'),
            (r'Additional sections', 'Phrase "Additional sections"'),
            (r'comprehensive.*word document that continues', 'Pattern "comprehensive...document that continues"'),
        ]

        for pattern_re, description in truncation_patterns:
            if re.search(pattern_re, self.content, re.IGNORECASE):
                self.errors.append(f"⚠️ CRITICAL: Content truncation detected: {description}")
                self.errors.append(f"   Report is INCOMPLETE and UNUSABLE - regenerate with progressive assembly")
                return False

        return True

    def _check_word_count(self) -> bool:
        """Check overall report length（低于档位硬下限即 error）"""
        word_count = self._count_words(self.content)
        minimum = MIN_WORDS[self.profile]

        if word_count < minimum:
            self.errors.append(
                f"报告过短：{word_count} 字，低于 {self.profile} 档硬下限 {minimum} 字（空壳不得通过）"
            )
            return False

        if word_count < 500:
            self.warnings.append(f"报告偏短：{word_count} 字（建议扩充）")
        # No upper limit warning - progressive assembly supports unlimited lengths

        return True

    def _check_source_count(self) -> bool:
        """Check minimum source count"""
        pattern = self._section_body_pattern("Bibliography")
        match = re.search(pattern, self.content, re.DOTALL | re.IGNORECASE)

        if not match:
            return True  # Already caught in bibliography check

        bib_section = match.group(1)
        bib_entries = self._bibliography_entries(bib_section)

        source_count = len(set(bib_entries))

        # 来源数量是参考值而非 KPI（见 quality-gates）：只警告不硬失败，
        # 避免误挡小型但完整的报告。空壳由空章节/0 字摘要/字数下限拦截。
        if source_count < 10:
            self.warnings.append(f"来源仅 {source_count} 个（建议 ≥10）")

        return True

    def _check_output_location(self) -> bool:
        """Check the report lives in a conventional run directory.

        The path convention is only real if something fails when it is broken.
        A report sitting outside `research/<topic>_研究_<YYYYMMDD>/` still reads
        fine, so without this check a misplaced run would pass silently and the
        next continuation agent would look in the wrong place.

        The naming rule comes from citation_manager.check_run_dir rather than a
        second copy of the pattern here: two copies drift, and then the gate and
        the resolver disagree about what a valid folder looks like.

        This warns rather than errors: users legitimately validate a draft
        before the run folder exists, and a hard failure would block that.
        """
        problems = check_run_dir(self.report_path.parent)
        # A missing folder is already reported as a broken path; only complain
        # about the name here so the message stays actionable.
        problems = [p for p in problems if not p.startswith("run 目录不存在")]

        if problems:
            self.warnings.append(
                "；".join(problems)
                + "。请用以下命令生成规范目录：python scripts/citation_manager.py init-run --query \"...\""
            )

        return True

    def _check_broken_references(self) -> bool:
        """Check for broken internal references"""
        # Find all markdown links [text](./path)
        internal_links = re.findall(r'\[.*?\]\((\.\/.*?)\)', self.content)

        broken = []
        for link in internal_links:
            # Remove anchor if present
            link_path = link.split('#')[0]
            full_path = self.report_path.parent / link_path

            if not full_path.exists():
                broken.append(link)

        if broken:
            self.errors.append(f"内部链接失效：{', '.join(broken)}")
            return False

        return True

    def _print_summary(self):
        """打印校验摘要。"""
        print(f"\n{'='*60}")
        print(f"校验摘要")
        print(f"{'='*60}\n")

        if self.errors:
            print(f"❌ 错误（{len(self.errors)}）：")
            for error in self.errors:
                print(f"   • {error}")
            print()

        if self.warnings:
            print(f"⚠️  警告（{len(self.warnings)}）：")
            for warning in self.warnings:
                print(f"   • {warning}")
            print()

        if not self.errors and not self.warnings:
            print("✅ 全部检查通过，报告符合质量要求！\n")
        elif not self.errors:
            print("✅ 校验通过（有警告）\n")
        else:
            print("❌ 校验失败，请在交付前修复错误\n")


def main():
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(
        description="校验 deep-research 研究报告质量（结构、引用、字数、输出位置）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python validate_report.py --report 研究报告.md
  python validate_report.py -r research/PostgreSQL_vs_Supabase_研究_20261028/研究报告.md
        """
    )

    parser.add_argument(
        '--report', '-r',
        type=str,
        required=True,
        help='研究报告 Markdown 文件路径'
    )
    parser.add_argument(
        '--profile',
        default='standard',
        choices=['direct', 'standard', 'deep'],
        help='验证强度：决定字数/来源数硬下限（默认 standard）'
    )

    args = parser.parse_args()

    report_path = Path(args.report)

    if not report_path.exists():
        print(f"❌ 错误：找不到报告文件：{report_path}")
        sys.exit(1)

    validator = ReportValidator(report_path, profile=args.profile)
    passed = validator.validate()

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()

