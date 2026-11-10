import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "md_to_html.py"
SPEC = importlib.util.spec_from_file_location("md_to_html", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


SAMPLE = """# 测试研究报告

## 执行摘要

这是执行摘要正文，包含一个引用[1]。

## 正文

| 项目 | 证据 |
|---|---|
| [示例](https://github.com/example/repo) | [代码](https://github.com/example/repo/blob/abc/file.py) |

## 参考文献

1. [示例来源](https://example.com/source)
2. [第二个来源](https://example.com/second)
"""


class MarkdownToHtmlTests(unittest.TestCase):
    def test_figure_pipeline_removed(self):
        self.assertFalse(hasattr(MODULE, '_convert_figures'))
        self.assertFalse(hasattr(MODULE, '_embed_src'))

    def test_repository_link_inside_table_is_clickable(self):
        content, _ = MODULE.convert_markdown_to_html(SAMPLE)
        self.assertIn(
            '<a href="https://github.com/example/repo" target="_blank" rel="noreferrer">示例</a>',
            content,
        )
        self.assertNotIn("[示例](https://github.com/example/repo)", content)

    def test_non_http_scheme_is_not_activated(self):
        markdown = "# 报告\n\n## 执行摘要\n\n[不安全](javascript:alert(1))\n"
        content, _ = MODULE.convert_markdown_to_html(markdown)
        self.assertNotIn('href="javascript:', content)

    def test_chinese_executive_summary_wrapped(self):
        content, _ = MODULE.convert_markdown_to_html(SAMPLE)
        self.assertIn('<div class="executive-summary"><h2 class="section-title">执行摘要</h2>', content)

    def test_bibliography_numbered_list_becomes_entries(self):
        _, bibliography = MODULE.convert_markdown_to_html(SAMPLE)
        self.assertIn('<div class="bib-entry">', bibliography)
        self.assertIn('class="bib-number">[1]</span>', bibliography)
        self.assertIn('href="https://example.com/source"', bibliography)
        self.assertEqual(MODULE.count_bibliography_entries(SAMPLE), 2)

    def test_section_after_bibliography_is_kept_in_content(self):
        markdown = SAMPLE + "\n## 方法论附录\n\n检索范围说明。\n"
        content, bibliography = MODULE.convert_markdown_to_html(markdown)
        self.assertIn('方法论附录', content)
        self.assertNotIn('方法论附录', bibliography)

    def test_render_fills_template_placeholders(self):
        template = """<html><head><title>{{TITLE}}</title></head><body>
<div class="header"><h1>{{TITLE}}</h1><span>{{DATE}}</span><span>{{SOURCE_COUNT}}</span></div>
{{METRICS_DASHBOARD}}
<div class="content">{{CONTENT}}<div class="bibliography">{{BIBLIOGRAPHY}}</div></div>
</body></html>"""
        html = MODULE.render_report_html(SAMPLE, template, "2026-11-11")
        self.assertIn('<h1>测试研究报告</h1>', html)
        self.assertIn('2026-11-11', html)
        self.assertIn('>2<', html)
        self.assertNotIn('{{', html)

    def test_cli_writes_report_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            report = base / "研究报告.md"
            report.write_text(SAMPLE, encoding="utf-8")
            template = base / "template.html"
            template.write_text(
                "<html><body>{{TITLE}}|{{DATE}}|{{SOURCE_COUNT}}|{{METRICS_DASHBOARD}}|{{CONTENT}}|{{BIBLIOGRAPHY}}</body></html>",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(report), "--template", str(template), "--date", "2026-11-11"],
                capture_output=True, text=True, encoding="utf-8",
                env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            output = Path(payload["output"])
            self.assertEqual(output.name, "报告.html")
            self.assertTrue(output.exists())
            html = output.read_text(encoding="utf-8")
            self.assertIn("测试研究报告", html)


if __name__ == "__main__":
    unittest.main()
