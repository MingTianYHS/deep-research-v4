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


class ReviewRound2Regressions(unittest.TestCase):
    """v4.1.0 复审发现的 4 个必须修项：回归锁。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_mixed_h1_h2_keeps_h1_sections(self):
        """# 章节 + ## 小节混合时，H1 正文不能被当作 preamble 丢弃。"""
        md = "# 一、执行摘要\n\n2026年出口量达到176万辆，同比增长32%。\n\n# 二、主要发现\n\n市场规模达到1200亿美元。\n\n## 2.1 细分\n\n细分市场增长20%。\n"
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(md, encoding="utf-8")
        r = run_script("extract_claims", "extract", "--report", p, "--dir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertGreaterEqual(out["claims_added"], 2)
        with open(os.path.join(self.tmp, "论点.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        texts = " ".join(row["text"] for row in rows)
        self.assertIn("176万辆", texts)
        self.assertIn("1200亿美元", texts)

    def test_decimal_not_eaten_by_ordered_list(self):
        """1.5万亿美元 / 3.12版本 不能被有序列表正则吞掉行首数字。"""
        md = "## 主要发现\n\n1.5万亿美元的市场规模在2025年持续扩张，增速显著。\n\n3.12版本于2026年正式发布，包含多项改进。\n"
        p = os.path.join(self.tmp, "r.md")
        Path(p).write_text(md, encoding="utf-8")
        r = run_script("extract_claims", "extract", "--report", p, "--dir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.tmp, "论点.jsonl"), encoding="utf-8") as f:
            texts = [json.loads(line)["text"] for line in f if line.strip()]
        joined = " ".join(texts)
        self.assertIn("1.5万亿美元", joined)
        self.assertIn("3.12版本", joined)

    def test_retired_claim_revives(self):
        """改回旧版本重抽时，retired 论点应恢复为 unverified。"""
        run = os.path.join(self.tmp, "run")
        os.makedirs(run)
        p1 = os.path.join(self.tmp, "r1.md")
        p2 = os.path.join(self.tmp, "r2.md")
        Path(p1).write_text("## 主要发现\n\n2026年出口量达到176万辆，同比增长32%。\n", encoding="utf-8")
        Path(p2).write_text("## 主要发现\n\n2026年进口量达到200万辆，同比增长10%。\n", encoding="utf-8")
        run_script("extract_claims", "extract", "--report", p1, "--dir", run)
        run_script("extract_claims", "extract", "--report", p2, "--dir", run)
        r = run_script("extract_claims", "extract", "--report", p1, "--dir", run)
        out = json.loads(r.stdout)
        self.assertGreaterEqual(out["claims_revived"], 1)

    def test_all_retired_verify_fails(self):
        """全部论点 retired 时，verify --strict 必须以活跃论点为 0 失败。"""
        write_jsonl(os.path.join(self.tmp, "来源.jsonl"), [{"source_id": "s1"}])
        write_jsonl(os.path.join(self.tmp, "证据.jsonl"), [
            {"evidence_id": "e1", "source_id": "s1", "quote": "x"},
        ])
        write_jsonl(os.path.join(self.tmp, "论点.jsonl"), [
            {"claim_id": "c1", "section_id": "finding_1", "text": "某事实。",
             "claim_type": "factual", "support_status": "retired"},
        ])
        r = run_script("verify_claim_support", "verify", "--dir", self.tmp,
                       "--profile", "deep", "--strict")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("活跃论点为 0", r.stdout)

    def test_price_fact_zero_overlap_fails_without_year_percent(self):
        """不含年份/百分比的 A 类价格事实，配无关证据也必须失败。"""
        write_jsonl(os.path.join(self.tmp, "来源.jsonl"), [{"source_id": "s1"}])
        write_jsonl(os.path.join(self.tmp, "证据.jsonl"), [
            {"evidence_id": "e1", "source_id": "s1",
             "quote": "香蕉富含钾元素，对人体健康有益。"},
        ])
        write_jsonl(os.path.join(self.tmp, "论点.jsonl"), [
            {"claim_id": "c1", "section_id": "finding_1",
             "text": "该方案单价为120美元，比竞品更低。",
             "claim_type": "factual", "materiality": "A",
             "cited_source_ids": ["s1"], "evidence_ids": [],
             "support_status": "unverified"},
        ])
        r = run_script("verify_claim_support", "verify", "--dir", self.tmp,
                       "--profile", "deep", "--strict")
        self.assertNotEqual(r.returncode, 0)
        self.assertGreaterEqual(json.loads(r.stdout)["hard_fact_conflicts"], 1)


if __name__ == "__main__":
    unittest.main()
