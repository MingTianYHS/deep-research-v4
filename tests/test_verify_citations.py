#!/usr/bin/env python3
"""verify_citations.py 中文参考文献解析测试（不联网）。"""

import importlib.util
import tempfile
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_citations.py"
SPEC = importlib.util.spec_from_file_location("verify_citations", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class BibliographyParsingTests(unittest.TestCase):
    def _entries(self, text: str):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "研究报告.md"
            report.write_text(text, encoding="utf-8")
            verifier = MODULE.CitationVerifier(report)
            return verifier.extract_bibliography()

    def test_parses_chinese_numbered_markdown_links(self):
        entries = self._entries("""# 报告

## 参考文献

1. [中国汽车工业协会：出口数据](https://www.caam.org.cn/example)
2. [海关总署：进出口统计](https://www.customs.gov.cn/example)
""")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["num"], "1")
        self.assertEqual(entries[0]["title"], "中国汽车工业协会：出口数据")
        self.assertEqual(entries[0]["url"], "https://www.caam.org.cn/example")

    def test_parses_bracket_style(self):
        entries = self._entries("""## Bibliography

[1] Smith, J. (2025). "Test Research Advances". Journal of Testing. https://example.com/paper1
""")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["year"], "2025")
        self.assertEqual(entries[0]["title"], "Test Research Advances")

    def test_chinese_title_similarity(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "研究报告.md"
            report.write_text("## 参考文献\n\n1. [中国新能源汽车出口数据](https://example.com)\n", encoding="utf-8")
            verifier = MODULE.CitationVerifier(report)
        self.assertGreater(verifier.check_title_similarity("中国新能源汽车出口数据", "中国新能源汽车出口数据"), 0.9)


if __name__ == "__main__":
    unittest.main()
