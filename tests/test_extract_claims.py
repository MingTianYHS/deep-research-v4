#!/usr/bin/env python3
"""extract_claims.py CLI 测试（英文回归 + 中文报告）。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'extract_claims.py')
FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
ENV = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}


def run_ec(*args: str) -> dict | list:
    """运行 extract_claims.py。"""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding='utf-8', env=ENV,
    )
    if result.returncode != 0:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}')
    return json.loads(result.stdout)


SAMPLE_REPORT = """\
---
title: Test Research Report
---

## Executive Summary

This report examines the impact of quantum computing on cryptography [1, 2]. The field has advanced significantly since 2020, with major breakthroughs in error correction.

## Introduction

Quantum computing represents a paradigm shift in computational capability. Researchers at Google demonstrated quantum supremacy in 2019 using a 53-qubit processor [3]. This milestone confirmed theoretical predictions made decades earlier.

## Finding 1

The Shor algorithm can factor large numbers exponentially faster than classical methods [4]. Current RSA-2048 encryption could be broken by a sufficiently large quantum computer. However, such machines are estimated to require millions of physical qubits [5, 6].

## Finding 2

Post-quantum cryptography standards should be adopted within the next 5 years. Organizations should consider hybrid classical-quantum approaches during the transition period. NIST has already standardized several lattice-based algorithms [7].

## Synthesis

Taken together, the evidence suggests that quantum computing poses a real but manageable threat to current cryptographic systems. The timeline for practical quantum attacks remains uncertain, but proactive migration reduces risk substantially.

## Recommendations

Organizations should begin evaluating post-quantum cryptography solutions immediately. Security teams should conduct a cryptographic inventory to identify vulnerable systems. Companies should consider implementing crypto-agility frameworks to enable rapid algorithm switching.

## Bibliography

[1] Smith et al. (2023). Quantum Computing Advances.
[2] Johnson (2024). Cryptographic Implications.
"""


class TestExtractEnglish(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        open(os.path.join(self.tmpdir, '论点.jsonl'), 'w', encoding='utf-8').close()
        self.report_path = os.path.join(self.tmpdir, '研究报告.md')
        with open(self.report_path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_REPORT)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_extract_finds_claims(self):
        out = run_ec('extract', '--report', self.report_path, '--dir', self.tmpdir)
        self.assertEqual(out['status'], 'ok')
        self.assertGreater(out['claims_added'], 5)

    def test_extract_idempotent(self):
        out1 = run_ec('extract', '--report', self.report_path, '--dir', self.tmpdir)
        out2 = run_ec('extract', '--report', self.report_path, '--dir', self.tmpdir)
        self.assertEqual(out2['claims_added'], 0)
        self.assertEqual(out2['claims_skipped'], out1['claims_added'])

    def test_claim_types_assigned(self):
        run_ec('extract', '--report', self.report_path, '--dir', self.tmpdir)
        out = run_ec('stats', '--dir', self.tmpdir)
        self.assertIn('factual', out['by_type'])
        self.assertIn('recommendation', out['by_type'])

    def test_sections_detected(self):
        run_ec('extract', '--report', self.report_path, '--dir', self.tmpdir)
        out = run_ec('stats', '--dir', self.tmpdir)
        self.assertIn('finding_1', out['by_section'])
        self.assertIn('finding_2', out['by_section'])
        self.assertIn('recommendations', out['by_section'])


class TestExtractChinese(unittest.TestCase):
    """中文报告 fixture：执行摘要、正文、参考文献。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.report_path = os.path.join(FIXTURES, '中文报告.md')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_chinese_report_extracts_claims(self):
        out = run_ec('extract', '--report', self.report_path, '--dir', self.tmpdir)
        self.assertEqual(out['status'], 'ok')
        self.assertGreaterEqual(out['claims_added'], 8)

    def test_chinese_sections_detected(self):
        run_ec('extract', '--report', self.report_path, '--dir', self.tmpdir)
        out = run_ec('stats', '--dir', self.tmpdir)
        self.assertIn('executive_summary', out['by_section'])
        self.assertIn('main_analysis', out['by_section'])
        self.assertIn('synthesis', out['by_section'])
        self.assertIn('recommendations', out['by_section'])
        self.assertNotIn('bibliography', out['by_section'])

    def test_chinese_claim_types(self):
        run_ec('extract', '--report', self.report_path, '--dir', self.tmpdir)
        out = run_ec('stats', '--dir', self.tmpdir)
        self.assertIn('factual', out['by_type'])
        self.assertIn('recommendation', out['by_type'])
        self.assertIn('synthesis', out['by_type'])

    def test_materiality_output(self):
        run_ec('extract', '--report', self.report_path, '--dir', self.tmpdir)
        with open(os.path.join(self.tmpdir, '论点.jsonl'), encoding='utf-8') as f:
            claims = [json.loads(line) for line in f]
        self.assertTrue(claims)
        self.assertTrue(all(c.get('materiality') in ('A', 'B', 'C', 'D') for c in claims))
        materialities = {c['materiality'] for c in claims}
        self.assertIn('A', materialities)
        self.assertIn('C', materialities)


class TestAdd(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        open(os.path.join(self.tmpdir, '论点.jsonl'), 'w', encoding='utf-8').close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_and_dedup(self):
        claim = json.dumps({
            'section_id': 'finding_1',
            'text': 'Quantum computers can break RSA encryption.',
            'claim_type': 'factual',
        })
        out1 = run_ec('add', '--json', claim, '--dir', self.tmpdir)
        self.assertEqual(out1['status'], 'added')
        self.assertEqual(len(out1['claim_id']), 16)
        out2 = run_ec('add', '--json', claim, '--dir', self.tmpdir)
        self.assertEqual(out2['status'], 'duplicate')

    def test_add_chinese(self):
        claim = json.dumps({
            'section_id': 'finding_1',
            'text': '2026年前三季度中国新能源汽车出口约176万辆。',
            'claim_type': 'factual',
        }, ensure_ascii=False)
        out = run_ec('add', '--json', claim, '--dir', self.tmpdir)
        self.assertEqual(out['status'], 'added')
        listed = run_ec('list', '--dir', self.tmpdir)
        self.assertEqual(listed['claims'][0]['text'], '2026年前三季度中国新能源汽车出口约176万辆。')


class TestListAndStats(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        open(os.path.join(self.tmpdir, '论点.jsonl'), 'w', encoding='utf-8').close()
        for sec, text, ctype in [
            ('finding_1', 'The sky appears blue due to Rayleigh scattering.', 'factual'),
            ('finding_1', 'Light wavelengths scatter differently in the atmosphere.', 'factual'),
            ('synthesis', 'Overall, atmospheric optics explains most visual phenomena.', 'synthesis'),
            ('recommendations', 'Researchers should investigate polarization effects further.', 'recommendation'),
        ]:
            run_ec('add', '--json', json.dumps({
                'section_id': sec, 'text': text, 'claim_type': ctype,
            }), '--dir', self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_list_all(self):
        self.assertEqual(run_ec('list', '--dir', self.tmpdir)['count'], 4)

    def test_list_by_section(self):
        self.assertEqual(run_ec('list', '--dir', self.tmpdir, '--section', 'finding_1')['count'], 2)

    def test_list_by_type(self):
        self.assertEqual(run_ec('list', '--dir', self.tmpdir, '--type', 'recommendation')['count'], 1)

    def test_stats(self):
        out = run_ec('stats', '--dir', self.tmpdir)
        self.assertEqual(out['total'], 4)
        self.assertEqual(out['by_type']['factual'], 2)
        self.assertEqual(out['by_type']['synthesis'], 1)
        self.assertEqual(out['by_type']['recommendation'], 1)


class TestClaimIDAndParsing(unittest.TestCase):
    """compute_claim_id、中文句子切分与分类的单元测试。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
        from extract_claims import (
            compute_claim_id, classify_claim, classify_materiality, split_sentences, extract_sentences, parse_sections,
        )
        cls.compute_id = staticmethod(compute_claim_id)
        cls.classify = staticmethod(classify_claim)
        cls.materiality = staticmethod(classify_materiality)
        cls.split = staticmethod(split_sentences)
        cls.extract = staticmethod(extract_sentences)
        cls.parse = staticmethod(parse_sections)

    def test_deterministic(self):
        self.assertEqual(
            self.compute_id('finding_1', 'Test claim.'),
            self.compute_id('finding_1', 'Test claim.'),
        )

    def test_section_matters(self):
        self.assertNotEqual(
            self.compute_id('finding_1', 'Same text.'),
            self.compute_id('finding_2', 'Same text.'),
        )

    def test_classify_recommendation_english(self):
        self.assertEqual(
            self.classify('Organizations should adopt PQC immediately.', 'recommendations'),
            'recommendation',
        )

    def test_classify_factual_english(self):
        self.assertEqual(self.classify('RSA-2048 uses 2048-bit keys.', 'finding_1'), 'factual')

    def test_classify_synthesis_english(self):
        self.assertEqual(
            self.classify('Taken together, the results indicate a clear trend.', 'synthesis'),
            'synthesis',
        )

    def test_classify_recommendation_chinese(self):
        self.assertEqual(
            self.classify('车企应当加快东南亚与拉美地区的本地化产能布局。', 'recommendations'),
            'recommendation',
        )

    def test_classify_speculation_chinese(self):
        self.assertEqual(
            self.classify('欧盟关税措施可能压低2027年的出口增速。', 'main_analysis'),
            'speculation',
        )

    def test_materiality_a_for_hard_fact(self):
        self.assertEqual(self.materiality('2026年出口量达到176万辆。', 'factual'), 'A')

    def test_materiality_b_for_background(self):
        self.assertEqual(self.materiality('该行业通常分为上游、中游和下游。', 'factual'), 'B')

    def test_materiality_c_for_analysis(self):
        self.assertEqual(self.materiality('综合来看，价格战仍将持续。', 'synthesis'), 'C')

    def test_materiality_d_for_speculation(self):
        self.assertEqual(self.materiality('预计2027年渗透率将达到30%。', 'speculation'), 'D')

    def test_split_chinese_sentences(self):
        sentences = self.split('第一句中文。第二句中文！第三句英文? Yes.')
        self.assertGreaterEqual(len(sentences), 3)
        self.assertEqual(sentences[0], '第一句中文。')

    def test_extract_sentences_filters_citation_only_line(self):
        text = '这是第一句足够长的中文论点。\n\n来源：[1], [2]\n'
        sentences = self.extract(text)
        self.assertEqual(sentences, ['这是第一句足够长的中文论点。'])

    def test_parse_chinese_headings(self):
        markdown = """## 一、执行摘要

摘要正文。

## 正文

### 发现一：标题

正文内容。

## 参考文献

1. [来源](https://example.com)
"""
        sections = self.parse(markdown)
        ids = [sid for sid, _ in sections]
        self.assertIn('executive_summary', ids)
        self.assertIn('main_analysis', ids)
        self.assertIn('bibliography', ids)


if __name__ == '__main__':
    unittest.main()
