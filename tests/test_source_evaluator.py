#!/usr/bin/env python3
"""source_evaluator.py 中文权威域名与中性域名测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from source_evaluator import SourceEvaluator  # noqa: E402


class SourceEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = SourceEvaluator()

    def test_gov_cn_is_high_authority(self):
        score = self.evaluator.evaluate_source('https://www.customs.gov.cn/example', '海关总署统计数据')
        self.assertGreaterEqual(score.domain_authority, 90.0)
        self.assertEqual(score.factors.get('domain'), '高权威域名')

    def test_edu_cn_is_high_authority(self):
        score = self.evaluator.evaluate_source('https://www.tsinghua.edu.cn/example', '清华大学研究报告')
        self.assertGreaterEqual(score.domain_authority, 90.0)

    def test_official_media_is_high_authority(self):
        score = self.evaluator.evaluate_source('https://www.xinhuanet.com/example', '新华社报道')
        self.assertGreaterEqual(score.domain_authority, 90.0)

    def test_subdomain_of_gov_cn_is_high_authority(self):
        score = self.evaluator.evaluate_source('https://stats.customs.gov.cn/data', '统计公报')
        self.assertGreaterEqual(score.domain_authority, 90.0)

    def test_unknown_domain_stays_neutral(self):
        score = self.evaluator.evaluate_source('https://unknown-example-site.com/post', '某篇文章')
        self.assertEqual(score.domain_authority, 55.0)
        self.assertNotIn('domain', score.factors)

    def test_domain_without_scheme(self):
        score = self.evaluator.evaluate_source('www.mofcom.gov.cn/article', '政策解读')
        self.assertGreaterEqual(score.domain_authority, 90.0)

    def test_low_authority_blog(self):
        score = self.evaluator.evaluate_source('https://someone.blogspot.com/post', '个人博客')
        self.assertEqual(score.domain_authority, 40.0)


if __name__ == '__main__':
    unittest.main()
