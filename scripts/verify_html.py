#!/usr/bin/env python3
"""HTML 报告校验脚本。

用 HTMLParser 解析真实标签与标题文本，而不是正则数数量：
- 逐个比对 Markdown 与 HTML 的二级标题（不是只比个数）；
- 拒绝 script/iframe/object/embed、on* 事件属性、javascript:/data: 链接；
- 参考文献条目数与 Markdown 逐条比对，空参考文献判 error。
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _console import setup_console_encoding  # noqa: E402


# 危险标签与危险链接协议
DANGEROUS_TAGS = {'script', 'iframe', 'object', 'embed', 'form'}
DANGEROUS_PROTOCOLS = ('javascript:', 'data:', 'vbscript:')


class _HTMLAudit(HTMLParser):
    """一次遍历收集：h2 文本、bib-entry 数、危险标签与危险链接。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h2_texts: list[str] = []
        self.bib_entries = 0
        self.dangerous_tags: list[str] = []
        self.dangerous_attrs: list[str] = []
        self.dangerous_links: list[str] = []
        self._h2_buf: list[str] | None = None
        self._in_bibliography = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr_map = {k.lower(): (v or '') for k, v in attrs}
        classes = attr_map.get('class', '').split()

        if tag in DANGEROUS_TAGS:
            self.dangerous_tags.append(tag)
        for key in attr_map:
            if key.startswith('on'):
                self.dangerous_attrs.append(f'{tag}[{key}]')
        if tag == 'a':
            href = attr_map.get('href', '').strip().lower()
            if href.startswith(DANGEROUS_PROTOCOLS):
                self.dangerous_links.append(href[:60])
        if tag == 'h2':
            self._h2_buf = []
        if 'bibliography' in classes:
            self._in_bibliography = True
        if 'bib-entry' in classes:
            self.bib_entries += 1

    def handle_endtag(self, tag):
        if tag.lower() == 'h2' and self._h2_buf is not None:
            self.h2_texts.append(''.join(self._h2_buf).strip())
            self._h2_buf = None

    def handle_data(self, data):
        if self._h2_buf is not None:
            self._h2_buf.append(data)


def _normalize_heading(text: str) -> str:
    """去掉编号前缀与空白，便于比较。"""
    text = re.sub(r'^\s*(?:[一二三四五六七八九十百]+|\d+)[、.．)）]\s*', '', text.strip())
    return re.sub(r'\s+', '', text)


def _md_h2(md: str) -> list[str]:
    """只取真正的二级标题（## 后不能紧跟 #），排除 ### 与正文。"""
    return [m.strip() for m in re.findall(r'^##(?!#)\s+(.+?)\s*$', md, re.MULTILINE)]


def _count_md_bib_entries(md: str) -> int:
    parts = re.split(r'^##(?!#)\s*(?:参考文献|参考资料|References|Bibliography)[^\n]*\n',
                     md, maxsplit=1, flags=re.MULTILINE)
    if len(parts) < 2:
        return 0
    body = re.split(r'^##(?!#)\s+', parts[1], maxsplit=1, flags=re.MULTILINE)[0]
    count = 0
    for line in body.split('\n'):
        line = line.strip()
        if re.match(r'^\[(\d+)\]', line) or re.match(r'^\d+[.、)）]\s+', line):
            count += 1
    return count


class HTMLVerifier:
    """校验 HTML 研究报告"""

    def __init__(self, html_path: Path, md_path: Path):
        setup_console_encoding()
        self.html_path = html_path
        self.md_path = md_path
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def verify(self) -> bool:
        print(f"\n{'='*60}")
        print("HTML 报告校验")
        print(f"{'='*60}\n")
        print(f"HTML 文件：{self.html_path}")
        print(f"Markdown 文件：{self.md_path}\n")

        try:
            html_content = self.html_path.read_text(encoding='utf-8')
            md_content = self.md_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as e:
            self.errors.append(f"读取文件失败：{e}")
            self._print_results()
            return False

        audit = _HTMLAudit()
        try:
            audit.feed(html_content)
        except Exception as e:  # HTMLParser 对极端畸形输入可能抛错
            self.errors.append(f"HTML 解析失败：{e}")

        self._check_sections(audit, md_content)
        self._check_dangerous(audit)
        self._check_placeholders(html_content)
        self._check_structure(html_content)
        self._check_citations(html_content, md_content)
        self._check_bibliography(audit, md_content)

        self._print_results()
        return len(self.errors) == 0

    def _check_sections(self, audit: _HTMLAudit, md: str):
        md_titles = _md_h2(md)
        html_titles = audit.h2_texts

        md_norm = [_normalize_heading(t) for t in md_titles]
        html_norm = [_normalize_heading(t) for t in html_titles]

        # 参考文献通常渲染成独立区块，不要求出现在 h2 列表里
        md_body = [t for t in md_norm
                   if t not in ('参考文献', '参考资料', 'references', 'bibliography')]

        missing = [t for t in md_body if t not in html_norm]
        if missing:
            self.errors.append(f"HTML 缺少章节标题：{missing}")

        if len(html_norm) < len(md_body):
            self.errors.append(
                f"章节数量不足：Markdown 有 {len(md_body)} 个正文二级标题，HTML 只有 {len(html_norm)} 个"
            )

    def _check_dangerous(self, audit: _HTMLAudit):
        if audit.dangerous_tags:
            self.errors.append(f"HTML 含危险标签：{sorted(set(audit.dangerous_tags))}")
        if audit.dangerous_attrs:
            self.errors.append(f"HTML 含内联事件属性：{sorted(set(audit.dangerous_attrs))}")
        if audit.dangerous_links:
            self.errors.append(f"HTML 含危险链接协议：{sorted(set(audit.dangerous_links))}")

    def _check_placeholders(self, html: str):
        placeholders = [
            '{{TITLE}}', '{{DATE}}', '{{CONTENT}}', '{{BIBLIOGRAPHY}}',
            '{{METRICS_DASHBOARD}}', '{{SOURCE_COUNT}}', 'TODO', 'TBD',
            'PLACEHOLDER', 'FIXME',
        ]
        found = [p for p in placeholders if p in html]
        if found:
            self.errors.append(f"发现未替换占位符：{', '.join(found)}")

    def _check_structure(self, html: str):
        required = [
            ('<html', 'HTML 标签'),
            ('<head', 'head 标签'),
            ('<body', 'body 标签'),
            ('<title>', 'title 标签'),
            ('class="header"', '页头区块'),
            ('class="content"', '内容区块'),
            ('class="bibliography"', '参考文献区块'),
        ]
        for token, name in required:
            if token not in html:
                self.errors.append(f"HTML 缺少{name}")

        open_divs = html.count('<div')
        close_divs = html.count('</div>')
        if abs(open_divs - close_divs) > 2:
            self.warnings.append(
                f"div 可能未闭合：{open_divs} 个开始标签，{close_divs} 个结束标签"
            )

    def _check_citations(self, html: str, md: str):
        # Markdown 正文引用（排除参考文献区块）
        md_body = re.split(r'^##(?!#)\s*(?:参考文献|参考资料|References|Bibliography)[^\n]*\n',
                           md, maxsplit=1, flags=re.MULTILINE)[0]
        md_citations = set(re.findall(r'\[(\d+)\]', md_body))
        if not md_citations:
            return

        html_body = html.split('class="bibliography"')[0]
        html_citations = set(re.findall(r'\[(\d+)\]', html_body))
        missing = md_citations - html_citations
        if missing:
            self.errors.append(f"HTML 正文缺少引用编号：{sorted(missing, key=int)}")

    def _check_bibliography(self, audit: _HTMLAudit, md: str):
        md_entries = _count_md_bib_entries(md)
        if md_entries == 0:
            return
        if audit.bib_entries == 0:
            self.errors.append("HTML 参考文献区块没有条目（空参考文献不得通过）")
        elif audit.bib_entries < md_entries:
            self.errors.append(
                f"HTML 参考文献条目不足：Markdown 有 {md_entries} 条，HTML 只有 {audit.bib_entries} 条"
            )

    def _print_results(self):
        print(f"{'-'*60}")
        print("校验结果")
        print(f"{'-'*60}\n")
        if self.errors:
            print(f"❌ 错误（{len(self.errors)}）：")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
            print()
        if self.warnings:
            print(f"⚠️ 警告（{len(self.warnings)}）：")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
            print()
        if not self.errors and not self.warnings:
            print("✅ 全部检查通过，HTML 报告有效。\n")
        elif not self.errors:
            print("✅ 校验通过（有警告）\n")
        else:
            print("❌ 校验失败，请修复后重试。\n")


def main():
    parser = argparse.ArgumentParser(description="校验 HTML 报告是否完整、安全地呈现 Markdown 报告")
    parser.add_argument("--html", type=Path, required=True, help="HTML 报告路径")
    parser.add_argument("--md", type=Path, required=True, help="对应 Markdown 报告路径")
    args = parser.parse_args()

    for p, label in ((args.html, "HTML"), (args.md, "Markdown")):
        if not p.exists():
            print(f"错误：找不到{label}文件：{p}", file=sys.stderr)
            sys.exit(1)

    verifier = HTMLVerifier(args.html, args.md)
    passed = verifier.verify()
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
