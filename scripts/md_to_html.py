#!/usr/bin/env python3
"""
Markdown → HTML 转换器（只做 Markdown→HTML，不涉及 PDF、图片或图表）。

用法：
  python scripts\\md_to_html.py 研究报告.md
  python scripts\\md_to_html.py 研究报告.md --template templates\\mckinsey_report_template.html --output 报告.html

默认行为：
  - 模板默认使用技能目录下的 templates\\mckinsey_report_template.html；
  - 输出默认写到报告同目录的 报告.html；
  - 填充模板占位符 {{TITLE}}、{{DATE}}、{{SOURCE_COUNT}}、{{METRICS_DASHBOARD}}、
    {{CONTENT}}、{{BIBLIOGRAPHY}}。
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import date
from pathlib import Path
from typing import Tuple


# ---------------------------------------------------------------------------
# 正文转换
# ---------------------------------------------------------------------------

_SECTION_HEADING_RE = re.compile(r'^## (.+)$', re.MULTILINE)
_EXEC_SUMMARY_NAMES = {'执行摘要', '摘要', '概要', 'Executive Summary'}


def convert_markdown_to_html(markdown_text: str) -> Tuple[str, str]:
    """把 Markdown 报告转换为 (正文 HTML, 参考文献 HTML) 两段。

    参考文献章节只取到下一个二级标题为止；参考文献之后的章节（例如
    方法论附录）仍保留在正文中，避免被误当成参考文献内容吞掉。
    """
    heading_re = re.compile(r'##\s*(?:Bibliography|References|参考文献)[^\n]*\n')
    match = heading_re.search(markdown_text)
    if not match:
        return _convert_content_section(markdown_text), ''

    content_before = markdown_text[:match.start()]
    after_heading = markdown_text[match.end():]
    next_section = re.search(r'^##\s+', after_heading, re.MULTILINE)
    if next_section:
        bibliography_md = after_heading[:next_section.start()]
        content_after = after_heading[next_section.start():]
    else:
        bibliography_md = after_heading
        content_after = ''

    content_md = content_before + content_after
    content_html = _convert_content_section(content_md)
    bibliography_html = _convert_bibliography_section(bibliography_md)
    return content_html, bibliography_html


def _convert_content_section(markdown: str) -> str:
    """转换正文部分（去掉第一个二级标题之前的标题与 front matter）。"""
    lines = markdown.split('\n')
    processed_lines = []
    reached_first_section = False

    for line in lines:
        if not reached_first_section:
            if line.startswith('## ') and not line.startswith('### '):
                reached_first_section = True
                processed_lines.append(line)
            continue
        processed_lines.append(line)

    content = '\n'.join(processed_lines)

    # 安全：先把所有文本转义为 HTML 实体，再生成标签。
    # 这样报告正文（含从网页摘录的引文）中的 <script>/<img onerror> 等
    # 原始 HTML 不会被执行；后续只插入本函数生成的可信标签。
    content = html_lib.escape(content, quote=False)

    def _section_tag(match: re.Match) -> str:
        title = match.group(1).strip()
        if title in _EXEC_SUMMARY_NAMES:
            return f'<div class="executive-summary"><h2 class="section-title">{title}</h2>'
        return f'<div class="section"><h2 class="section-title">{title}</h2>'

    content = _SECTION_HEADING_RE.sub(_section_tag, content)
    content = re.sub(r'^### (.+)$', r'<h3 class="subsection-title">\1</h3>', content, flags=re.MULTILINE)
    content = re.sub(r'^#### (.+)$', r'<h4 class="subsubsection-title">\1</h4>', content, flags=re.MULTILINE)

    # 行内格式
    content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
    content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
    content = re.sub(r'`(.+?)`', r'<code>\1</code>', content)

    content = _convert_inline_links(content)
    content = _convert_lists(content)
    content = _convert_tables(content)
    content = _convert_paragraphs(content)
    content = _close_sections(content)
    return content


def _convert_inline_links(html: str) -> str:
    """只激活 HTTP(S) Markdown 链接，其他协议保持惰性文本。

    输入已经过 HTML 转义（& < > 已变成实体），因此：
    - label 不再二次转义（否则 & 会变成 &amp;amp;）；
    - href 先 unescape 还原真实 URL，再按属性转义一次，防止双重转义。
    """
    def repl(m: re.Match) -> str:
        label = m.group(1)
        raw_url = html_lib.unescape(m.group(2))
        url = html_lib.escape(raw_url, quote=True).replace('"', '%22')
        return f'<a href="{url}" target="_blank" rel="noreferrer">{label}</a>'

    return re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', repl, html)


def _convert_bibliography_section(markdown: str) -> str:
    """把参考文献条目转换为 bib-entry 结构；支持 [N] 与 N. 两种编号。"""
    if not markdown.strip():
        return ''

    entries = []
    for raw_line in markdown.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r'^\[(\d+)\]\s*(.+)$', line) or re.match(r'^(\d+)[.、)）]\s*(.+)$', line)
        if not match:
            continue
        number, rest = match.group(1), match.group(2).strip()
        # 安全：条目正文先转义，再识别链接（模板输出为 HTML）
        rest_html = html_lib.escape(rest, quote=False)
        rest_html = _convert_inline_links(rest_html)

        def url_repl(m: re.Match) -> str:
            raw = html_lib.unescape(m.group(1))
            href = html_lib.escape(raw, quote=True).replace('"', '%22')
            return f'<a href="{href}" target="_blank" rel="noreferrer">{m.group(1)}</a>'

        # 纯 URL 也转成可点击链接
        rest_html = re.sub(r'(?<!["\'&gt;])(https?://[^\s<]+)', url_repl, rest_html)
        entries.append(
            f'<div class="bib-entry"><span class="bib-number">[{number}]</span> {rest_html}</div>'
        )

    return '\n'.join(entries)


def count_bibliography_entries(markdown_text: str) -> int:
    """统计参考文献条目数，作为没有 来源.jsonl 时的回退值。

    只统计参考文献章节本身（到下一个二级标题为止），避免把方法论附录等
    后续章节里的编号列表误算进来。
    """
    parts = re.split(r'##\s*(?:Bibliography|References|参考文献)[^\n]*\n', markdown_text, maxsplit=1)
    if len(parts) < 2:
        return 0
    body = re.split(r'^##\s+', parts[1], maxsplit=1, flags=re.MULTILINE)[0]
    count = 0
    for line in body.split('\n'):
        line = line.strip()
        if re.match(r'^\[(\d+)\]', line) or re.match(r'^\d+[.、)）]\s+', line):
            count += 1
    return count


def count_sources_from_manifest_dir(run_dir: Path) -> int | None:
    """从 run 目录的 来源.jsonl 统计唯一来源数；文件不存在时返回 None。"""
    sources_path = run_dir / '来源.jsonl'
    if not sources_path.exists():
        return None
    source_ids = set()
    with open(sources_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            source_id = row.get('source_id')
            if source_id:
                source_ids.add(source_id)
    return len(source_ids)


def load_source_urls(run_dir: Path) -> dict[int, str]:
    """读取 来源.jsonl，按去重登记顺序返回 {显示编号: raw_url}。

    编号规则与 citation_manager.export-bibliography 一致（先按 source_id 去重，
    再按登记顺序从 1 开始）。只有 http/https 链接才返回，用于正文 [N] 点击跳转。
    """
    sources_path = run_dir / '来源.jsonl'
    if not sources_path.exists():
        return {}
    urls: dict[int, str] = {}
    seen: set[str] = set()
    index = 0
    with open(sources_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = row.get('source_id')
            if not sid or sid in seen:
                continue
            seen.add(sid)
            index += 1
            url = (row.get('raw_url') or '').strip()
            if url.startswith(('http://', 'https://')):
                urls[index] = url
    return urls


def linkify_citations(content_html: str, source_urls: dict[int, str]) -> str:
    """把正文里的 [N] 变成可点击链接（点一下打开来源页）。

    - 只处理不在已有 <a> 标签内的 [N]，避免嵌套链接；
    - 没有 URL 的编号保持纯文本；
    - href 做属性转义，防止注入。
    """
    if not source_urls:
        return content_html

    def repl(m: re.Match) -> str:
        num = int(m.group(1))
        url = source_urls.get(num)
        if not url:
            return m.group(0)
        href = html_lib.escape(url, quote=True).replace('"', '%22')
        return (
            f'<a class="citation" href="{href}" target="_blank" '
            f'rel="noreferrer">{m.group(0)}</a>'
        )

    # 先按已有 <a>...</a> 切片，只对非链接片段做替换
    parts = re.split(r'(<a\b[^>]*>.*?</a>)', content_html, flags=re.DOTALL)
    return ''.join(
        part if part.startswith('<a') else re.sub(r'\[(\d+)\]', repl, part)
        for part in parts
    )


def _convert_lists(html: str) -> str:
    """把 Markdown 无序/有序列表转换为 HTML 列表。"""
    lines = html.split('\n')
    result = []
    in_list = False
    list_tag = ''
    list_level = 0

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                result.append('<ul>')
                in_list = True
                list_tag = 'ul'
                list_level = len(line) - len(line.lstrip())
            result.append(f'<li>{stripped[2:]}</li>')

        elif re.match(r'^\d+\.\s', stripped):
            if not in_list:
                result.append('<ol>')
                in_list = True
                list_tag = 'ol'
                list_level = len(line) - len(line.lstrip())
            content = re.sub(r"^[0-9]+[.]\s", "", stripped)
            result.append(f'<li>{content}</li>')

        else:
            if in_list:
                current_level = len(line) - len(line.lstrip())
                if current_level > list_level and stripped:
                    if result[-1].endswith('</li>'):
                        result[-1] = result[-1][:-5] + ' ' + stripped + '</li>'
                    continue
                result.append(f'</{list_tag}>')
                in_list = False
                list_tag = ''
                list_level = 0
            result.append(line)

    if in_list:
        result.append(f'</{list_tag}>')

    return '\n'.join(result)


def _convert_tables(html: str) -> str:
    """把 Markdown 表格转换为 HTML 表格。"""
    lines = html.split('\n')
    result = []
    in_table = False

    for line in lines:
        if '|' in line and line.strip().startswith('|'):
            if not in_table:
                result.append('<table>')
                in_table = True
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                result.append('<thead><tr>')
                for cell in cells:
                    result.append(f'<th>{cell}</th>')
                result.append('</tr></thead>')
                result.append('<tbody>')
            elif '---' in line:
                continue
            else:
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                result.append('<tr>')
                for cell in cells:
                    result.append(f'<td>{cell}</td>')
                result.append('</tr>')
        else:
            if in_table:
                result.append('</tbody></table>')
                in_table = False
            result.append(line)

    if in_table:
        result.append('</tbody></table>')

    return '\n'.join(result)


def _convert_paragraphs(html: str) -> str:
    """把非 HTML 行包进 <p> 标签。"""
    lines = html.split('\n')
    result = []
    in_paragraph = False

    html_starts = ('<h', '<div', '<ul', '<ol', '<li', '<table', '<figure', '</div>', '</ul>', '</ol>')

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_paragraph:
                result.append('</p>')
                in_paragraph = False
            result.append(line)
            continue

        if (stripped.startswith('<') and stripped.endswith('>')) or stripped.startswith('</') \
                or any(token in stripped for token in html_starts):
            if in_paragraph:
                result.append('</p>')
                in_paragraph = False
            result.append(line)
            continue

        if not in_paragraph:
            result.append('<p>' + line)
            in_paragraph = True
        else:
            result.append(line)

    if in_paragraph:
        result.append('</p>')

    return '\n'.join(result)


def _close_sections(html: str) -> str:
    """在每个新的章节块前关闭上一个章节 div。"""
    lines = html.split('\n')
    result = []
    section_open = False

    for line in lines:
        if '<div class="section">' in line or '<div class="executive-summary">' in line:
            if section_open:
                result.append('</div>')
            section_open = True
        result.append(line)

    if section_open:
        result.append('</div>')

    return '\n'.join(result)


# ---------------------------------------------------------------------------
# 模板填充
# ---------------------------------------------------------------------------

def _extract_title(markdown_text: str, fallback: str = '研究报告') -> str:
    for line in markdown_text.split('\n'):
        if line.startswith('# '):
            return line[2:].strip()
    return fallback


def _metrics_dashboard(source_count: int, section_count: int, char_count: int) -> str:
    return (
        '<div class="metrics-dashboard">'
        f'<div class="metric"><span class="metric-number">{section_count}</span>'
        '<span class="metric-label">章节数</span></div>'
        f'<div class="metric"><span class="metric-number">{source_count}</span>'
        '<span class="metric-label">来源数</span></div>'
        f'<div class="metric"><span class="metric-number">{char_count}</span>'
        '<span class="metric-label">正文字数</span></div>'
        '</div>'
    )


def render_report_html(
    markdown_text: str,
    template_text: str,
    report_date: str | None = None,
    source_count: int | None = None,
    source_urls: dict[int, str] | None = None,
) -> str:
    """把 Markdown 报告填入模板，返回完整 HTML 字符串。

    source_urls 非空时，正文里的 [N] 会变成可点击来源链接。
    """
    content_html, bibliography_html = convert_markdown_to_html(markdown_text)
    if source_urls:
        content_html = linkify_citations(content_html, source_urls)
    title = html_lib.escape(_extract_title(markdown_text))
    if source_count is None:
        source_count = count_bibliography_entries(markdown_text)
    section_count = len(re.findall(r'<h2 class="section-title">', content_html))
    char_count = len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]', content_html))
    date_text = report_date or date.today().strftime('%Y-%m-%d')

    replacements = {
        '{{TITLE}}': title,
        '{{DATE}}': date_text,
        '{{SOURCE_COUNT}}': str(source_count),
        '{{METRICS_DASHBOARD}}': _metrics_dashboard(source_count, section_count, char_count),
        '{{CONTENT}}': content_html,
        '{{BIBLIOGRAPHY}}': bibliography_html,
    }
    rendered = template_text
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def main() -> None:
    """CLI 入口：把 Markdown 报告渲染为完整 HTML 文件。"""
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(
        prog='md_to_html',
        description='把 deep-research 的 Markdown 研究报告渲染为 HTML（不含图片、图表与 PDF）',
    )
    parser.add_argument('markdown_file', type=Path, help='Markdown 报告路径（通常是 研究报告.md）')
    parser.add_argument(
        '--template',
        type=Path,
        default=None,
        help='HTML 模板路径；默认使用技能模板 templates\\mckinsey_report_template.html',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help='输出 HTML 路径；默认写到报告同目录的 报告.html',
    )
    parser.add_argument('--date', default=None, help='报告日期（YYYY-MM-DD），默认今天')
    args = parser.parse_args()

    md_file = args.markdown_file
    if not md_file.exists():
        parser.error(f'找不到 Markdown 报告：{md_file}')

    template_path = args.template
    if template_path is None:
        template_path = Path(__file__).resolve().parent.parent / 'templates' / 'mckinsey_report_template.html'
    if not template_path.exists():
        parser.error(f'找不到 HTML 模板：{template_path}')

    markdown_text = md_file.read_text(encoding='utf-8')
    template_text = template_path.read_text(encoding='utf-8')

    # SOURCE_COUNT 优先取 run 目录 来源.jsonl 的唯一来源数，回退到参考文献条目数
    source_count = count_sources_from_manifest_dir(md_file.parent)
    if source_count is None:
        source_count = count_bibliography_entries(markdown_text)

    # 正文 [N] 点击跳转：从同目录 来源.jsonl 建立 编号→URL 映射
    source_urls = load_source_urls(md_file.parent)

    rendered = render_report_html(
        markdown_text, template_text, args.date,
        source_count=source_count, source_urls=source_urls,
    )

    output_path = args.output or (md_file.parent / '报告.html')
    output_path.write_text(rendered, encoding='utf-8')

    print(
        json.dumps({
            'status': 'ok',
            'output': str(output_path),
            'sources': source_count,
            'linked_citations': len(source_urls),
        }, ensure_ascii=False)
    )


if __name__ == '__main__':
    main()
