"""质量门回归测试：锁住四个「假通过」阻断项，防止复发。

对应审查发现：
  阻断1 --strict 不拦截 needs_review / 无关引文
  阻断2 缺失/空产物被当作空数组成功
  阻断3 空壳报告通过 validate_report
  阻断4 verify_citations 全部 URL 失败仍返回 0
以及配套：H1-only 抽取、表格抽取、link-claims 悬空引用。
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vcs = _load("verify_claim_support")
vr = _load("validate_report")
ec = _load("extract_claims")
cm = _load("citation_manager")
vc = _load("verify_citations")


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_script(name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{name}.py"), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


class BlockingGateRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_empty_dir_verify_fails(self):
        r = run_script("verify_claim_support", "verify", "--dir", self.tmp,
                       "--profile", "deep", "--strict")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("fail", r.stdout)

    def test_empty_claims_file_fails(self):
        write_jsonl(os.path.join(self.tmp, "论点.jsonl"), [])
        write_jsonl(os.path.join(self.tmp, "来源.jsonl"), [{"source_id": "s1"}])
        write_jsonl(os.path.join(self.tmp, "证据.jsonl"), [{"evidence_id": "e1", "source_id": "s1", "quote": "x"}])
        r = run_script("verify_claim_support", "verify", "--dir", self.tmp, "--strict")
        self.assertNotEqual(r.returncode, 0)

    def test_irrelevant_evidence_hard_fact_fails_under_strict(self):
        write_jsonl(os.path.join(self.tmp, "来源.jsonl"), [{"source_id": "s1"}])
        write_jsonl(os.path.join(self.tmp, "证据.jsonl"), [
            {"evidence_id": "e1", "source_id": "s1", "quote": "香蕉富含钾元素，对人体健康有益。"},
        ])
        write_jsonl(os.path.join(self.tmp, "论点.jsonl"), [
            {"claim_id": "c1", "section_id": "finding_1",
             "text": "2025年全球人工智能市场规模达到1200亿美元，同比增长30%。",
             "claim_type": "factual", "materiality": "A",
             "cited_source_ids": ["s1"], "evidence_ids": [], "support_status": "unverified"},
        ])
        r = run_script("verify_claim_support", "verify", "--dir", self.tmp,
                       "--profile", "deep", "--strict")
        self.assertNotEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertGreaterEqual(out["hard_fact_conflicts"], 1)

    def test_ghost_source_fails_under_strict(self):
        write_jsonl(os.path.join(self.tmp, "来源.jsonl"), [{"source_id": "s1"}])
        write_jsonl(os.path.join(self.tmp, "证据.jsonl"), [
            {"evidence_id": "e1", "source_id": "ghost", "quote": "some quote about 2025 and 30%"},
        ])
        write_jsonl(os.path.join(self.tmp, "论点.jsonl"), [
            {"claim_id": "c1", "section_id": "finding_1", "text": "出口增长30%。",
             "claim_type": "factual", "cited_source_ids": ["ghost"],
             "evidence_ids": [], "support_status": "unverified"},
        ])
        r = run_script("verify_claim_support", "verify", "--dir", self.tmp,
                       "--profile", "deep", "--strict")
        self.assertNotEqual(r.returncode, 0)

    def test_empty_shell_report_fails(self):
        shell = "# 空壳\n\n## 执行摘要\n\n[1][2][3]\n\n## 引言\n\n## 主要发现\n\n" \
                "## 分析综合\n\n## 局限与说明\n\n## 建议\n\n## 参考文献\n\n" \
                "1. [a](https://example.com/1)\n2. [b](https://example.com/2)\n3. [c](https://example.com/3)\n\n" \
                "## 方法论附录\n"
        p = os.path.join(self.tmp, "研究报告.md")
        Path(p).write_text(shell, encoding="utf-8")
        validator = vr.ReportValidator(Path(p))
        self.assertFalse(validator.validate())
        self.assertTrue(validator.errors)

    def test_bibliography_without_url_fails(self):
        text = "# t\n\n## 执行摘要\n\n正文内容足够长以满足字数下限要求，这里重复一些文字以确保超过两百字。" \
               "正文内容足够长以满足字数下限要求，这里重复一些文字以确保超过两百字。" \
               "正文内容足够长以满足字数下限要求，这里重复一些文字以确保超过两百字。[1]\n\n" \
               "## 引言\n\nx\n\n## 主要发现\n\nx\n\n## 分析综合\n\nx\n\n## 局限与说明\n\nx\n\n" \
               "## 建议\n\nx\n\n## 参考文献\n\n1. 无链接来源\n\n## 方法论附录\n\nx\n"
        p = os.path.join(self.tmp, "研究报告.md")
        Path(p).write_text(text, encoding="utf-8")
        validator = vr.ReportValidator(Path(p))
        self.assertFalse(validator._check_bibliography())

    def test_verify_citations_zero_verified_fails(self):
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text("# t\n\n## 参考文献\n\n1. [a](https://x.invalid/1)\n2. [b](https://x.invalid/2)\n",
                           encoding="utf-8")
        verifier = vc.CitationVerifier(Path(p), strict_mode=False)
        with mock.patch.object(verifier, "verify_url", return_value=(False, "blocked")), \
             mock.patch.object(verifier, "verify_doi", return_value=(False, {})):
            self.assertFalse(verifier.verify_all())


class ExtractionRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_h1_only_report_extracts_claims(self):
        md = "# 执行摘要\n\n2025年出口达到176万辆，同比增长32%。\n\n# 主要发现\n\n市场规模达到1200亿美元。\n"
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(md, encoding="utf-8")
        r = run_script("extract_claims", "extract", "--report", p, "--dir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertGreater(out["claims_added"], 0)

    def test_table_rows_extract_claims(self):
        md = "## 主要发现\n\n| 指标 | 数值 |\n|---|---|\n| 市场规模 | 1200亿美元 |\n| 同比 | 30% |\n"
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(md, encoding="utf-8")
        r = run_script("extract_claims", "extract", "--report", p, "--dir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertGreater(out["claims_added"], 0)

    def test_zero_claim_report_fails(self):
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text("没有任何章节标题的纯文本。\n", encoding="utf-8")
        r = run_script("extract_claims", "extract", "--report", p, "--dir", self.tmp)
        self.assertNotEqual(r.returncode, 0)


class LinkClaimsRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_dangling_citation_fails(self):
        write_jsonl(os.path.join(self.tmp, "来源.jsonl"), [{"source_id": "s1"}])
        write_jsonl(os.path.join(self.tmp, "论点.jsonl"), [
            {"claim_id": "c1", "text": "x", "_citation_numbers": [5], "cited_source_ids": []},
        ])
        r = run_script("citation_manager", "link-claims", "--dir", self.tmp)
        self.assertNotEqual(r.returncode, 0)

    def test_duplicate_sources_numbering_consistent(self):
        write_jsonl(os.path.join(self.tmp, "来源.jsonl"), [
            {"source_id": "s1"}, {"source_id": "s1"}, {"source_id": "s2"},
        ])
        write_jsonl(os.path.join(self.tmp, "论点.jsonl"), [
            {"claim_id": "c1", "text": "x", "_citation_numbers": [2], "cited_source_ids": []},
        ])
        r = run_script("citation_manager", "link-claims", "--dir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.tmp, "论点.jsonl"), encoding="utf-8") as f:
            claim = json.loads(f.readline())
        self.assertEqual(claim["cited_source_ids"], ["s2"])


if __name__ == "__main__":
    unittest.main()
