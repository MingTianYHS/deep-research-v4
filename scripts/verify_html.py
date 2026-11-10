#!/usr/bin/env python3
"""
HTML 报告校验脚本
校验 HTML 报告是否完整呈现 Markdown 报告的全部章节。
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple


class HTMLVerifier:
    """校验 HTML 研究报告"""

    def __init__(self, html_path: Path, md_path: Path):
        self.html_path = html_path
        self.md_path = md_path
        self.errors = []
        self.warnings = []

    def verify(self) -> bool:
        """执行全部校验，全部通过返回 True。"""
        print(f"\n{'='*60}")
        print(f"HTML 报告校验")
        print(f"{'='*60}\n")

        print(f"HTML 文件：{self.html_path}")
        print(f"Markdown 文件：{self.md_path}\n")

        try:
            html_content = self.html_path.read_text(encoding='utf-8')
            md_content = self.md_path.read_text(encoding='utf-8')
        except Exception as e:
            self.errors.append(f"读取文件失败：{e}")
            return False

        self._check_sections(html_content, md_content)
        self._check_no_placeholders(html_content)
        self._check_no_emojis(html_content)
        self._check_structure(html_content)
        self._check_citations(html_content, md_content)
        self._check_bibliography(html_content, md_content)

        self._print_results()

        return len(self.errors) == 0

    def _check_sections(self, html: str, md: str):
        """Verify all markdown sections are present in HTML"""
        # Extract section headings from markdown
        md_sections = re.findall(r'^## (.+)$', md, re.MULTILINE)

        # Extract sections from HTML
        html_sections = re.findall(r'<h2 class="section-title">(.+?)</h2>', html)

        # Check if we have placeholder sections like <div class="section">#</div>
        placeholder_sections = re.findall(r'<div class="section">#</div>', html)

        if placeholder_sections:
            self.errors.append(
                f"Found {len(placeholder_sections)} placeholder sections (empty '#' divs) - content not converted properly"
            )

        # Compare section counts
        if len(md_sections) > len(html_sections) + 1:  # +1 for bibliography which is separate
            self.errors.append(
                f"Section count mismatch: MD has {len(md_sections)} sections, HTML has only {len(html_sections)} + bibliography"
            )
            missing = set(md_sections) - set(html_sections)
            if missing:
                self.errors.append(f"Missing sections in HTML: {missing}")

        # 校验执行摘要存在
        if any(name in md for name in ('执行摘要', 'Executive Summary')):
            if not any(name in html for name in ('执行摘要', 'Executive Summary')):
                self.errors.append("HTML 缺少执行摘要")

    def _check_no_placeholders(self, html: str):
        """Check for common placeholders that shouldn't be in final report"""
        placeholders = [
            '{{TITLE}}', '{{DATE}}', '{{CONTENT}}', '{{BIBLIOGRAPHY}}',
            '{{METRICS_DASHBOARD}}', '{{SOURCE_COUNT}}', 'TODO', 'TBD',
            'PLACEHOLDER', 'FIXME'
        ]

        found = []
        for placeholder in placeholders:
            if placeholder in html:
                found.append(placeholder)

        if found:
            self.errors.append(f"Found unreplaced placeholders: {', '.join(found)}")

    def _check_no_emojis(self, html: str):
        """Verify no emojis are present in HTML"""
        # Common emoji patterns
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002600-\U000026FF"  # misc symbols
            "\U00002700-\U000027BF"  # dingbats
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA70-\U0001FAFF"  # extended pictographs
            "\U0001F170-\U0001F251"  # enclosed characters
            "]+",
            flags=re.UNICODE
        )

        emojis = emoji_pattern.findall(html)
        if emojis:
            unique_emojis = set(emojis)
            self.errors.append(f"Found {len(emojis)} emojis in HTML (should be none): {unique_emojis}")

    def _check_structure(self, html: str):
        """Verify HTML has proper structure"""
        required_elements = [
            ('<html', 'HTML tag'),
            ('<head', 'head tag'),
            ('<body', 'body tag'),
            ('<title>', 'title tag'),
            ('class="header"', 'header section'),
            ('class="content"', 'content section'),
            ('class="bibliography"', 'bibliography section'),
        ]

        for element, name in required_elements:
            if element not in html:
                self.errors.append(f"Missing {name} in HTML")

        # Check for unclosed tags (basic check)
        open_divs = html.count('<div')
        close_divs = html.count('</div>')

        if abs(open_divs - close_divs) > 2:  # Allow small discrepancy
            self.warnings.append(
                f"Possible unclosed divs: {open_divs} opening tags, {close_divs} closing tags"
            )

    def _check_citations(self, html: str, md: str):
        """Verify citations are present"""
        # Extract citations from markdown
        md_citations = set(re.findall(r'\[(\d+)\]', md))

        # Extract citations from HTML (excluding bibliography)
        html_content = html.split('class="bibliography"')[0] if 'class="bibliography"' in html else html
        html_citations = set(re.findall(r'\[(\d+)\]', html_content))

        if len(md_citations) > 0 and len(html_citations) == 0:
            self.errors.append("No citations found in HTML content (but present in MD)")

        if len(md_citations) > len(html_citations) * 1.5:  # Allow some variation
            self.warnings.append(
                f"Fewer citations in HTML ({len(html_citations)}) than MD ({len(md_citations)})"
            )

    def _check_bibliography(self, html: str, md: str):
        """校验参考文献在 HTML 中存在且格式正确。"""
        if re.search(r'##\s*(?:参考文献|References|Bibliography)', md):
            if 'class="bibliography"' not in html:
                self.errors.append("HTML 缺少参考文献区块")
            elif 'class="bib-entry"' not in html:
                self.warnings.append("参考文献存在，但条目可能未正确格式化")

    def _print_results(self):
        """打印校验结果。"""
        print(f"\n{'-'*60}")
        print("校验结果")
        print(f"{'-'*60}\n")

        if self.errors:
            print(f"❌ 错误（{len(self.errors)}）：")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
            print()

        if self.warnings:
            print(f"⚠️  警告（{len(self.warnings)}）：")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
            print()

        if not self.errors and not self.warnings:
            print("✅ 全部检查通过，HTML 报告有效。")
            print()

        print(f"{'-'*60}\n")


def main():
    """命令行入口。"""
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(description='校验 HTML 研究报告与 Markdown 报告的一致性')
    parser.add_argument('--html', type=Path, required=True, help='HTML 报告路径')
    parser.add_argument('--md', type=Path, required=True, help='Markdown 报告路径')

    args = parser.parse_args()

    if not args.html.exists():
        print(f"错误：找不到 HTML 文件：{args.html}")
        return 1

    if not args.md.exists():
        print(f"错误：找不到 Markdown 文件：{args.md}")
        return 1

    verifier = HTMLVerifier(args.html, args.md)
    success = verifier.verify()

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
