#!/usr/bin/env python3
"""citation_manager.py CLI 冒烟测试。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'citation_manager.py')
ENV = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}


def run_cm(*args: str) -> dict:
    """运行 citation_manager.py，返回解析后的 JSON。"""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding='utf-8', env=ENV,
    )
    if result.returncode != 0:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}')
    return json.loads(result.stdout) if result.stdout.strip().startswith(('{', '[')) else result.stdout


class TestInitRun(unittest.TestCase):
    def test_creates_manifest_and_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            out = run_cm('init-run', '--out-dir', d, '--query', 'test question', '--mode', 'deep')
            self.assertEqual(out['status'], 'ok')

            with open(os.path.join(d, '运行清单.json'), encoding='utf-8') as f:
                manifest = json.load(f)
            self.assertEqual(manifest['version'], '4.3.0')
            self.assertEqual(manifest['query'], 'test question')
            self.assertEqual(manifest['mode'], 'deep')
            self.assertEqual(manifest['query_type'], 'depth')
            self.assertEqual(manifest['rigor'], 'deep')
            self.assertEqual(manifest['budget'], 'normal')
            self.assertEqual(manifest['language'], 'zh')
            self.assertIsNotNone(manifest['started_at'])
            self.assertIsNone(manifest['finished_at'])
            self.assertEqual(manifest['artifact_paths']['sources'], '来源.jsonl')
            self.assertEqual(manifest['artifact_paths']['evidence'], '证据.jsonl')
            self.assertEqual(manifest['artifact_paths']['claims'], '论点.jsonl')
            self.assertEqual(manifest['artifact_paths']['report'], '研究报告.md')

            for name in ('来源.jsonl', '证据.jsonl', '论点.jsonl'):
                path = os.path.join(d, name)
                self.assertTrue(os.path.exists(path), f'{name} missing')
                self.assertEqual(os.path.getsize(path), 0)

    def test_direct_mode_infers_direct_query_type(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', '东京人口是多少', '--mode', 'direct')
            with open(os.path.join(d, '运行清单.json'), encoding='utf-8') as f:
                manifest = json.load(f)
            self.assertEqual(manifest['mode'], 'direct')
            self.assertEqual(manifest['query_type'], 'direct')
            self.assertEqual(manifest['rigor'], 'standard')

    def test_explicit_rigor_overrides_mode(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', '测试', '--mode', 'deep', '--rigor', 'standard')
            with open(os.path.join(d, '运行清单.json'), encoding='utf-8') as f:
                manifest = json.load(f)
            self.assertEqual(manifest['rigor'], 'standard')

    def test_rejects_legacy_mode(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, 'init-run', '--out-dir', tempfile.gettempdir(), '--mode', 'ultradeep'],
            capture_output=True, text=True, encoding='utf-8', env=ENV,
        )
        self.assertNotEqual(0, result.returncode)


class TestFinalizeRun(unittest.TestCase):
    def test_sets_finished_at_and_assumptions(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', '测试问题')
            out = run_cm(
                'finalize-run', '--dir', d,
                '--assumption', '假设一：公开统计数据口径一致',
                '--assumption', '假设二：政策环境保持稳定',
            )
            self.assertEqual(out['status'], 'ok')
            self.assertEqual(out['assumption_count'], 2)
            with open(os.path.join(d, '运行清单.json'), encoding='utf-8') as f:
                manifest = json.load(f)
            self.assertIsNotNone(manifest['finished_at'])
            self.assertEqual(len(manifest['assumptions']), 2)
            self.assertTrue(manifest['assumptions'][0]['assumption_id'].startswith('asm_'))


class TestRegisterSource(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        run_cm('init-run', '--out-dir', self.tmpdir, '--query', 'test')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_register_and_dedup(self):
        src = json.dumps({
            'raw_url': 'https://arxiv.org/abs/2305.14251',
            'title': 'FActScore',
            'source_type': 'academic',
            'year': '2023',
        }, ensure_ascii=False)
        out1 = run_cm('register-source', '--json', src, '--dir', self.tmpdir)
        self.assertEqual(out1['status'], 'registered')
        self.assertEqual(len(out1['source_id']), 16)
        self.assertTrue(out1['canonical_locator'].startswith('arxiv:'))

        out2 = run_cm('register-source', '--json', src, '--dir', self.tmpdir)
        self.assertEqual(out2['status'], 'duplicate')
        self.assertEqual(out2['source_id'], out1['source_id'])

    def test_doi_canonicalization(self):
        src = json.dumps({
            'raw_url': 'https://doi.org/10.1038/s41586-023-06745-9',
            'title': 'Some Nature paper',
        })
        out = run_cm('register-source', '--json', src, '--dir', self.tmpdir)
        self.assertTrue(out['canonical_locator'].startswith('doi:10.1038/'))

    def test_url_normalization(self):
        src1 = json.dumps({
            'raw_url': 'https://Example.Com/article?utm_source=google&id=42',
            'title': 'Test',
        })
        src2 = json.dumps({
            'raw_url': 'https://example.com/article?id=42&utm_medium=email',
            'title': 'Test duplicate',
        })
        out1 = run_cm('register-source', '--json', src1, '--dir', self.tmpdir)
        out2 = run_cm('register-source', '--json', src2, '--dir', self.tmpdir)
        self.assertEqual(out1['source_id'], out2['source_id'])
        self.assertEqual(out2['status'], 'duplicate')


class TestAssignDisplayNumbers(unittest.TestCase):
    def test_assigns_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            for i, url in enumerate(['https://a.com/1', 'https://b.com/2', 'https://c.com/3']):
                run_cm('register-source', '--json', json.dumps({
                    'raw_url': url, 'title': f'Source {i+1}',
                }), '--dir', d)

            mapping = run_cm('assign-display-numbers', '--dir', d)
            self.assertEqual(len(mapping), 3)
            self.assertEqual(sorted(mapping.values()), [1, 2, 3])


class TestLinkClaims(unittest.TestCase):
    def test_maps_citation_numbers_to_source_ids(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', '测试')
            ids = []
            for i, url in enumerate(['https://a.com/1', 'https://b.com/2']):
                out = run_cm('register-source', '--json', json.dumps({
                    'raw_url': url, 'title': f'来源{i+1}',
                }, ensure_ascii=False), '--dir', d)
                ids.append(out['source_id'])

            claims = [
                {
                    'claim_id': 'a' * 16,
                    'section_id': 'main_analysis',
                    'text': '2025 年市场规模为 120 亿美元 [2]。',
                    'claim_type': 'factual',
                    'materiality': 'A',
                    'cited_source_ids': [],
                    'evidence_ids': [],
                    'support_status': 'unverified',
                    '_citation_numbers': [2],
                }
            ]
            with open(os.path.join(d, '论点.jsonl'), 'w', encoding='utf-8') as f:
                for claim in claims:
                    f.write(json.dumps(claim, ensure_ascii=False) + '\n')

            result = run_cm('link-claims', '--dir', d)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['linked'], 1)
            self.assertEqual(result['unresolved_citation_numbers'], {})

            with open(os.path.join(d, '论点.jsonl'), encoding='utf-8') as f:
                saved = json.loads(f.readline())
            self.assertEqual(saved['cited_source_ids'], [ids[1]])


class TestExportBibliography(unittest.TestCase):
    def test_markdown_export(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            run_cm('register-source', '--json', json.dumps({
                'raw_url': 'https://arxiv.org/abs/2305.14251',
                'title': 'FActScore',
                'authors': ['Min, S.', 'Krishna, K.'],
                'year': '2023',
                'source_type': 'academic',
            }), '--dir', d)

            out = run_cm('export-bibliography', '--dir', d, '--style', 'markdown')
            self.assertIn('## 参考文献', out)
            self.assertIn('[1]', out)
            self.assertIn('FActScore', out)
            self.assertIn('Min, S. & Krishna, K.', out)

    def test_json_export(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            run_cm('register-source', '--json', json.dumps({
                'raw_url': 'https://example.com/paper',
                'title': 'Test Paper',
            }), '--dir', d)

            out = run_cm('export-bibliography', '--dir', d, '--style', 'json')
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]['display_number'], 1)
            self.assertEqual(out[0]['title'], 'Test Paper')


class TestCanonicalization(unittest.TestCase):
    """不经过 CLI 的 canonicalize_locator 单元测试。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
        from citation_manager import canonicalize_locator, compute_source_id
        cls.canonicalize = staticmethod(canonicalize_locator)
        cls.compute_id = staticmethod(compute_source_id)

    def test_doi_from_url(self):
        self.assertEqual(
            self.canonicalize('https://doi.org/10.1038/s41586-023-06745-9'),
            'doi:10.1038/s41586-023-06745-9',
        )
        self.assertEqual(
            self.canonicalize('https://dx.doi.org/10.1234/test.'),
            'doi:10.1234/test',
        )

    def test_arxiv_from_url(self):
        self.assertEqual(
            self.canonicalize('https://arxiv.org/abs/2305.14251v2'),
            'arxiv:2305.14251v2',
        )
        self.assertEqual(self.canonicalize('arxiv:2401.15884'), 'arxiv:2401.15884')

    def test_url_strips_tracking(self):
        result = self.canonicalize('https://Example.Com/page?utm_source=x&key=val')
        self.assertNotIn('utm_source', result)
        self.assertIn('key=val', result)
        self.assertTrue(result.startswith('https://example.com'))

    def test_url_strips_fragment(self):
        result = self.canonicalize('https://example.com/page#section')
        self.assertNotIn('#section', result)

    def test_url_strips_trailing_slash(self):
        result = self.canonicalize('https://example.com/page/')
        self.assertFalse(result.endswith('/'))


class TestRunDirectoryConvention(unittest.TestCase):
    """run 目录命名由 citation_manager 解析，因此在此测试。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
        import citation_manager
        cls.cm = citation_manager

    def test_slug_collapses_whitespace(self):
        self.assertEqual('PostgreSQL_vs_Supabase', self.cm.slugify_topic('PostgreSQL vs Supabase'))

    def test_slug_keeps_cjk(self):
        self.assertEqual('城市更新政策', self.cm.slugify_topic('城市更新政策'))

    def test_slug_keeps_both_languages(self):
        self.assertEqual('PostgreSQL_与_Supabase_对比', self.cm.slugify_topic('PostgreSQL 与 Supabase 对比'))

    def test_slug_cannot_escape_container(self):
        slug = self.cm.slugify_topic('../../etc/passwd')
        self.assertNotIn('/', slug)
        self.assertNotIn('\\', slug)
        self.assertEqual('etc_passwd', slug)

    def test_slug_strips_windows_illegal_chars(self):
        slug = self.cm.slugify_topic('a<b>c:d"e|f?g*h')
        for char in '<>:"|?*':
            self.assertNotIn(char, slug)

    def test_slug_truncates(self):
        self.assertLessEqual(len(self.cm.slugify_topic('x' * 200)), 60)

    def test_resolve_places_run_under_research(self):
        with tempfile.TemporaryDirectory() as base:
            path = self.cm.resolve_run_dir('quantum computing', base=base, date=datetime(2026, 10, 28))
            self.assertEqual(Path(base) / 'research' / 'quantum_computing_研究_20261028', path)

    def test_resolve_collision_adds_suffix(self):
        with tempfile.TemporaryDirectory() as base:
            first = self.cm.resolve_run_dir('topic', base=base, date=datetime(2026, 10, 28), create=True)
            second = self.cm.resolve_run_dir('topic', base=base, date=datetime(2026, 10, 28), create=True)
            self.assertEqual('topic_研究_20261028', first.name)
            self.assertEqual('topic_研究_20261028_2', second.name)

    def test_check_accepts_conforming_dir(self):
        with tempfile.TemporaryDirectory() as base:
            run_dir = Path(base) / 'research' / 'topic_研究_20261028'
            run_dir.mkdir(parents=True)
            self.assertEqual([], self.cm.check_run_dir(run_dir))

    def test_check_rejects_missing_container(self):
        with tempfile.TemporaryDirectory() as base:
            run_dir = Path(base) / 'topic_研究_20261028'
            run_dir.mkdir()
            problems = self.cm.check_run_dir(run_dir)
            self.assertTrue(any('research/' in p for p in problems))

    def test_check_rejects_english_suffix(self):
        with tempfile.TemporaryDirectory() as base:
            run_dir = Path(base) / 'research' / 'topic_Research_20261028'
            run_dir.mkdir(parents=True)
            self.assertTrue(any('研究' in p for p in self.cm.check_run_dir(run_dir)))

    def test_init_run_resolves_dir_from_query(self):
        with tempfile.TemporaryDirectory() as base:
            cwd = os.getcwd()
            os.chdir(base)
            try:
                out = run_cm('init-run', '--query', '城市更新政策', '--mode', 'standard')
            finally:
                os.chdir(cwd)
            self.assertTrue(
                out['dir'].endswith(
                    os.path.join('research', '城市更新政策_研究_' + datetime.now().strftime('%Y%m%d'))
                )
            )
            self.assertTrue(os.path.isdir(out['dir']))

    def test_init_run_requires_dir_or_query(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, 'init-run'],
            capture_output=True, text=True, encoding='utf-8', env=ENV,
        )
        self.assertNotEqual(0, result.returncode)


if __name__ == '__main__':
    unittest.main()
