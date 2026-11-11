"""B 批复审修复回归：表格结构化解析、字数只统计正文。"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{name}.py"), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def read_claims(directory):
    p = os.path.join(directory, "论点.jsonl")
    if not os.path.exists(p):
        return []
    import json
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TableExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_header_and_separator_not_claims(self):
        md = (
            "## 主要发现\n\n"
            "| 指标 | 2025年 | 同比 |\n"
            "|---|---|---|\n"
            "| 市场规模 | 1200亿美元 | 30% |\n"
        )
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(md, encoding="utf-8")
        r = run_script("extract_claims", "extract", "--report", p, "--dir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        texts = [c["text"] for c in read_claims(self.tmp)]
        joined = " ".join(texts)
        self.assertNotIn("指标，2025年，同比", joined)
        self.assertIn("1200亿美元", joined)
        self.assertIn("30%", joined)

    def test_table_without_leading_pipe(self):
        md = (
            "## 主要发现\n\n"
            "指标 | 数值\n"
            "--- | ---\n"
            "市场规模 | 1200亿美元\n"
        )
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(md, encoding="utf-8")
        r = run_script("extract_claims", "extract", "--report", p, "--dir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        joined = " ".join(c["text"] for c in read_claims(self.tmp))
        self.assertIn("1200亿美元", joined)

    def test_table_data_maps_header_to_value(self):
        md = (
            "## 主要发现\n\n"
            "| 指标 | 数值 |\n"
            "|---|---|\n"
            "| 市场规模 | 1200亿美元 |\n"
        )
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(md, encoding="utf-8")
        run_script("extract_claims", "extract", "--report", p, "--dir", self.tmp)
        texts = [c["text"] for c in read_claims(self.tmp)]
        self.assertTrue(any("指标=市场规模" in t and "数值=1200亿美元" in t for t in texts), texts)


class TableCitationInheritanceTests(unittest.TestCase):
    """表格行不带 [N]，应继承本节最近一次引用，避免必然 unsupported。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_table_rows_inherit_section_citation(self):
        md = (
            "## 主要发现\n\n"
            "据公开来源，2026 年该市场规模达到 1200 亿美元，同比增长 30%。[1]\n\n"
            "| 指标 | 数值 |\n"
            "|---|---|\n"
            "| 市场规模 | 1200亿美元 |\n"
        )
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(md, encoding="utf-8")
        r = run_script("extract_claims", "extract", "--report", p, "--dir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        claims = read_claims(self.tmp)
        table_claims = [c for c in claims if "=" in c["text"]]
        self.assertTrue(table_claims, claims)
        for c in table_claims:
            self.assertEqual(c["_citation_numbers"], [1], c["text"])


class WordCountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _validate(self, text, profile="direct"):
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(text, encoding="utf-8")
        r = run_script("validate_report", "--report", p, "--profile", profile)
        return r

    def test_long_bibliography_urls_do_not_inflate_word_count(self):
        urls = "\n".join(
            f"{i}. [来源{i}](https://example.com/{'x' * 80}/{i})" for i in range(1, 9)
        )
        text = (
            "# 空壳\n\n## 执行摘要\n\n略。\n\n## 引言\n\n略。\n\n## 主要发现\n\n略。\n\n"
            "## 分析综合\n\n略。\n\n## 局限与说明\n\n略。\n\n## 建议\n\n略。\n\n"
            f"## 参考文献\n\n{urls}\n\n## 方法论附录\n\n略。\n"
        )
        r = self._validate(text)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("报告过短", r.stdout)

    def test_normal_report_still_passes(self):
        body = "这是一段足够长的正文内容，用于验证字数统计不会误挡正常报告。" * 8
        urls = "\n".join(
            f"{i}. [来源{i}](https://example.com/{i})" for i in range(1, 4)
        )
        text = (
            f"# 测试\n\n## 执行摘要\n\n{body}[1]\n\n## 引言\n\n{body}[1]\n\n"
            f"## 主要发现\n\n{body}[1]\n\n## 分析综合\n\n{body}[1]\n\n"
            f"## 局限与说明\n\n{body}[1]\n\n## 建议\n\n{body}[1]\n\n"
            f"## 参考文献\n\n{urls}\n\n## 方法论附录\n\n{body}\n"
        )
        r = self._validate(text, profile="direct")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
