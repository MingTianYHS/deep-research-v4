#!/usr/bin/env python3
"""
来源可信度评估器（Source Credibility Evaluator）
评估来源质量、可信度与潜在偏向，并给出信任建议。
"""

import argparse
import json
from dataclasses import asdict, dataclass
from typing import List, Dict, Optional
from urllib.parse import urlparse
from datetime import datetime, timedelta
import re


@dataclass
class CredibilityScore:
    """来源可信度评估结果"""
    overall_score: float  # 0-100
    domain_authority: float  # 0-100
    recency: float  # 0-100
    expertise: float  # 0-100
    bias_score: float  # 0-100（越高越中立）
    factors: Dict[str, str]
    recommendation: str  # "high_trust", "moderate_trust", "low_trust", "verify"


class SourceEvaluator:
    """评估来源可信度与质量"""

    # 域名声誉分层
    HIGH_AUTHORITY_DOMAINS = {
        # 学术与研究
        'arxiv.org', 'nature.com', 'science.org', 'cell.com', 'nejm.org',
        'thelancet.com', 'springer.com', 'sciencedirect.com', 'plos.org',
        'ieee.org', 'acm.org', 'pubmed.ncbi.nlm.nih.gov',

        # 政府与国际组织
        'nih.gov', 'cdc.gov', 'who.int', 'fda.gov', 'nasa.gov',
        'gov.uk', 'europa.eu', 'un.org',

        # 中文政府、教育与官方媒体/机构
        'gov.cn', 'edu.cn', 'people.com.cn', 'xinhuanet.com', 'news.cn',
        'cctv.com', 'chinadaily.com.cn', 'cnr.cn', 'china.com.cn', 'ce.cn',
        'stats.gov.cn', 'cnnic.cn', 'cac.gov.cn', 'gov.hk', 'gov.mo',

        # 成熟技术文档
        'docs.python.org', 'developer.mozilla.org', 'docs.microsoft.com',
        'cloud.google.com', 'aws.amazon.com', 'kubernetes.io',

        # 可信新闻（经事实核查）
        'reuters.com', 'apnews.com', 'bbc.com', 'economist.com',
        'nature.com/news', 'scientificamerican.com'
    }

    MODERATE_AUTHORITY_DOMAINS = {
        # 科技新闻与分析
        'techcrunch.com', 'theverge.com', 'arstechnica.com', 'wired.com',
        'zdnet.com', 'cnet.com',

        # 行业出版物
        'forbes.com', 'bloomberg.com', 'wsj.com', 'ft.com',

        # 中文财经与科技媒体
        'caixin.com', '36kr.com', 'huxiu.com', 'thepaper.cn',
        'jiemian.com', 'sina.com.cn', 'sohu.com', '163.com',
        'qq.com', 'ifeng.com', 'oschina.net', 'csdn.net', 'juejin.cn',

        # 教育类
        'wikipedia.org', 'britannica.com', 'khanacademy.org',

        # 成熟技术博客
        'medium.com', 'dev.to', 'stackoverflow.com', 'github.com'
    }

    LOW_AUTHORITY_INDICATORS = [
        'blogspot.com', 'wordpress.com', 'wix.com', 'substack.com'
    ]

    def __init__(self):
        pass

    @classmethod
    def _domain_matches(cls, domain: str, candidates) -> bool:
        """判断域名是否等于候选域名或是其子域。"""
        return any(domain == item or domain.endswith('.' + item) for item in candidates)

    @classmethod
    def _is_high_authority(cls, domain: str) -> bool:
        if cls._domain_matches(domain, cls.HIGH_AUTHORITY_DOMAINS):
            return True
        # 所有 .gov.cn / .edu.cn 子域均视为权威
        return domain.endswith('.gov.cn') or domain.endswith('.edu.cn')

    @classmethod
    def _is_moderate_authority(cls, domain: str) -> bool:
        return cls._domain_matches(domain, cls.MODERATE_AUTHORITY_DOMAINS)

    def evaluate_source(
        self,
        url: str,
        title: str,
        content: Optional[str] = None,
        publication_date: Optional[str] = None,
        author: Optional[str] = None
    ) -> CredibilityScore:
        """Evaluate source credibility"""

        domain = self._extract_domain(url)

        # Calculate component scores
        domain_score = self._evaluate_domain_authority(domain)
        recency_score = self._evaluate_recency(publication_date)
        expertise_score = self._evaluate_expertise(domain, title, author)
        bias_score = self._evaluate_bias(domain, title, content)

        # Calculate overall score (weighted average)
        overall = (
            domain_score * 0.35 +
            recency_score * 0.20 +
            expertise_score * 0.25 +
            bias_score * 0.20
        )

        # Determine factors
        factors = self._identify_factors(
            domain, domain_score, recency_score, expertise_score, bias_score
        )

        # Generate recommendation
        recommendation = self._generate_recommendation(overall)

        return CredibilityScore(
            overall_score=round(overall, 2),
            domain_authority=round(domain_score, 2),
            recency=round(recency_score, 2),
            expertise=round(expertise_score, 2),
            bias_score=round(bias_score, 2),
            factors=factors,
            recommendation=recommendation
        )

    def _extract_domain(self, url: str) -> str:
        """从 URL 提取域名。"""
        raw = url.strip()
        if '://' not in raw:
            raw = 'https://' + raw
        parsed = urlparse(raw)
        domain = parsed.netloc.lower()
        domain = domain.split('@')[-1].split(':')[0]
        domain = domain.replace('www.', '', 1)
        return domain

    def _evaluate_domain_authority(self, domain: str) -> float:
        """评估域名权威度（0-100）。"""
        if self._is_high_authority(domain):
            return 90.0
        elif self._is_moderate_authority(domain):
            return 70.0
        elif any(indicator in domain for indicator in self.LOW_AUTHORITY_INDICATORS):
            return 40.0
        else:
            # 未知域名保持中性
            return 55.0

    def _evaluate_recency(self, publication_date: Optional[str]) -> float:
        """Evaluate information recency (0-100)"""
        if not publication_date:
            return 50.0  # Unknown date

        try:
            pub_date = datetime.fromisoformat(publication_date.replace('Z', '+00:00'))
            age = datetime.now() - pub_date

            # Recency scoring
            if age < timedelta(days=90):  # < 3 months
                return 100.0
            elif age < timedelta(days=365):  # < 1 year
                return 85.0
            elif age < timedelta(days=730):  # < 2 years
                return 70.0
            elif age < timedelta(days=1825):  # < 5 years
                return 50.0
            else:
                return 30.0

        except Exception:
            return 50.0

    def _evaluate_expertise(
        self,
        domain: str,
        title: str,
        author: Optional[str]
    ) -> float:
        """评估来源专业度（0-100）。"""
        score = 50.0

        # 学术/研究域名专业度高
        if any(d in domain for d in ['arxiv', 'nature', 'science', 'ieee', 'acm']):
            score += 30

        # 政府/官方来源
        if '.gov' in domain or '.edu.cn' in domain or 'who.int' in domain:
            score += 25

        # 中文官方媒体/机构
        if self._domain_matches(domain, ['people.com.cn', 'xinhuanet.com', 'news.cn', 'cctv.com', 'chinadaily.com.cn']):
            score += 25

        # 技术文档
        if 'docs.' in domain or 'documentation' in title.lower() or '文档' in title:
            score += 20

        # 作者资质（若提供）
        if author:
            if any(marker in author.lower() for marker in ['dr.', 'phd', 'professor', '教授', '博士']):
                score += 15

        return min(score, 100.0)

    def _evaluate_bias(
        self,
        domain: str,
        title: str,
        content: Optional[str]
    ) -> float:
        """评估潜在偏向（0-100，越高越中立）。"""
        score = 70.0  # 初始中性

        # 标题中的煽动性表达
        sensational_indicators = [
            '!', 'shocking', 'unbelievable', "you won't believe",
            'secret', "they don't want you to know",
            '震惊', '惊天', '揭秘', '你绝对想不到', '内幕',
        ]
        title_lower = title.lower()
        if any(indicator in title_lower for indicator in sensational_indicators):
            score -= 20

        # 学术来源通常更少偏向
        if any(d in domain for d in ['arxiv', 'nature', 'science', 'ieee']):
            score += 20

        # 内容平衡性（若提供）
        if content:
            balanced_indicators = [
                'however', 'although', 'on the other hand', 'critics argue',
                '然而', '但是', '另一方面', '有观点认为', '批评者认为',
            ]
            if any(indicator in content.lower() for indicator in balanced_indicators):
                score += 10

        return min(max(score, 0), 100.0)

    def _identify_factors(
        self,
        domain: str,
        domain_score: float,
        recency_score: float,
        expertise_score: float,
        bias_score: float
    ) -> Dict[str, str]:
        """识别关键可信度因素。"""
        factors = {}

        if domain_score >= 85:
            factors['domain'] = '高权威域名'
        elif domain_score <= 45:
            factors['domain'] = '低权威域名，需核验说法'

        if recency_score >= 85:
            factors['recency'] = '信息较新'
        elif recency_score <= 40:
            factors['recency'] = '信息陈旧，需核实时效性'

        if expertise_score >= 80:
            factors['expertise'] = '专家来源'
        elif expertise_score <= 45:
            factors['expertise'] = '专业度信号有限'

        if bias_score >= 80:
            factors['bias'] = '视角较平衡'
        elif bias_score <= 50:
            factors['bias'] = '可能存在偏向'

        return factors

    def _generate_recommendation(self, overall_score: float) -> str:
        """生成信任建议。"""
        if overall_score >= 80:
            return "high_trust"
        elif overall_score >= 60:
            return "moderate_trust"
        elif overall_score >= 40:
            return "low_trust"
        else:
            return "verify"


def main():
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(description="评估单个来源的可信度（中文权威域名识别，未知域名保持中性）")
    parser.add_argument("--url", required=True, help="来源 URL")
    parser.add_argument("--title", required=True, help="来源标题")
    parser.add_argument("--content", help="来源正文（可选）")
    parser.add_argument("--publication-date", help="发布日期，ISO 格式（可选）")
    parser.add_argument("--author", help="作者（可选）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出完整评分")
    args = parser.parse_args()

    score = SourceEvaluator().evaluate_source(
        url=args.url,
        title=args.title,
        content=args.content,
        publication_date=args.publication_date,
        author=args.author,
    )
    payload = asdict(score)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"综合评分：{score.overall_score}/100")
        print(f"信任建议：{score.recommendation}")
        print(f"关键因素：{score.factors}")


if __name__ == '__main__':
    main()
