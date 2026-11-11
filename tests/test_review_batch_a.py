"""A 批复审修复回归：verify_html 重写、书目无 URL、章节匹配、点击引用。"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vr = _load("validate_report")
mh = _load("md_to_html")
vh = _load("verify_html")


def run_script(name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{name}.py"), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


class VerifyHtmlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, name, text):
        p = os.path.join(self.tmp, name)
        Path(p).write_text(text, encoding="utf-8")
        return p

    def _md(self):
        return "# 测试\n\n## 执行摘要\n\n正文 [1]\n\n## 参考文献\n\n1. [a](https://example.com/a)\n"

    def _html(self, heading="执行摘要", extra=""):
        return (
            "<html><head><title>t</title></head><body>"
            '<div class="header"></div>'
            f'<div class="content"><h2 class="section-title">{heading}</h2><p>正文 [1]</p></div>'
            '<div class="bibliography"><div class="bib-entry"><span class="bib-number">[1]</span> a</div></div>'
            f"{extra}</body></html>"
        )

    def test_valid_html_passes(self):
        html = self._write("ok.html", self._html())
        md = self._write("ok.md", self._md())
        self.assertTrue(vh.HTMLVerifier(Path(html), Path(md)).verify())

    def test_wrong_heading_fails(self):
        html = self._write("bad.html", self._html(heading="完全无关的标题"))
        md = self._write("ok.md", self._md())
        self.assertFalse(vh.HTMLVerifier(Path(html), Path(md)).verify())

    def test_script_tag_fails(self):
        html = self._write("xss.html", self._html(extra="<script>alert(1)</script>"))
        md = self._write("ok.md", self._md())
        self.assertFalse(vh.HTMLVerifier(Path(html), Path(md)).verify())

    def test_javascript_href_fails(self):
        html = self._write("js.html", self._html(extra='<a href="javascript:alert(1)">x</a>'))
        md = self._write("ok.md", self._md())
        self.assertFalse(vh.HTMLVerifier(Path(html), Path(md)).verify())

    def test_empty_bibliography_fails(self):
        html = self._write("empty.html",
                           '<html><head><title>t</title></head><body>'
                           '<div class="header"></div><div class="content">'
                           '<h2 class="section-title">执行摘要</h2><p>正文 [1]</p></div>'
                           '<div class="bibliography"></div></body></html>')
        md = self._write("ok.md", self._md())
        self.assertFalse(vh.HTMLVerifier(Path(html), Path(md)).verify())


class HeadingMatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _validate(self, text, profile="direct"):
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(text, encoding="utf-8")
        return vr.ReportValidator(Path(p), profile=profile).validate()

    def test_h3_cannot_impersonate_h2(self):
        text = (
            "# 测试\n\n## 执行摘要\n\n" + "足够长的摘要内容。" * 10 + "\n\n"
            "### 引言\n\n三级标题下的内容。\n\n"
            "## 主要发现\n\n正文 [1]\n\n## 分析综合\n\n综合 [1]\n\n"
            "## 局限与说明\n\n局限 [1]\n\n## 建议\n\n建议 [1]\n\n"
            "## 参考文献\n\n1. [a](https://example.com/a)\n\n## 方法论附录\n\n方法。\n"
        )
        self.assertFalse(self._validate(text))

    def test_numbered_heading_accepted(self):
        text = (
            "# 测试\n\n## 一、执行摘要\n\n" + "足够长的摘要内容。" * 10 + "\n\n"
            "## 二、引言\n\n引言 [1]\n\n## 三、主要发现\n\n正文 [1]\n\n"
            "## 四、分析综合\n\n综合 [1]\n\n## 五、局限与说明\n\n局限 [1]\n\n"
            "## 六、建议\n\n建议 [1]\n\n## 七、参考文献\n\n1. [a](https://example.com/a)\n\n"
            "## 八、方法论附录\n\n方法。\n"
        )
        self.assertTrue(self._validate(text))


class ClickableCitationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_citation_becomes_link(self):
        md = "## 执行摘要\n\n正文 [1]，另见 [2]。\n"
        urls = {1: "https://example.com/a", 2: "https://example.com/b"}
        content, _ = mh.convert_markdown_to_html(md)
        linked = mh.linkify_citations(content, urls)
        self.assertIn('<a class="citation" href="https://example.com/a"', linked)
        self.assertIn('<a class="citation" href="https://example.com/b"', linked)

    def test_missing_url_keeps_plain_text(self):
        md = "## 执行摘要\n\n正文 [1][9]。\n"
        content, _ = mh.convert_markdown_to_html(md)
        linked = mh.linkify_citations(content, {1: "https://example.com/a"})
        self.assertIn('[9]', linked)
        self.assertNotIn('href="https://example.com/a">[9]', linked)

    def test_no_double_wrap_existing_links(self):
        md = "## 执行摘要\n\n[示例](https://example.com/x) [1]\n"
        content, _ = mh.convert_markdown_to_html(md)
        linked = mh.linkify_citations(content, {1: "https://example.com/a"})
        self.assertEqual(linked.count('<a '), 2)


class NoUrlBibliographyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_no_url_entry_does_not_crash(self):
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(
            "# 测试\n\n## 参考文献\n\n1. 作者. 书名. 出版社, 2020.\n", encoding="utf-8")
        r = run_script("verify_citations", "--report", p)
        # 不应出现 Python traceback；应给出结构化结论（suspicious / 0 verified）
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("No DOI or URL", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
