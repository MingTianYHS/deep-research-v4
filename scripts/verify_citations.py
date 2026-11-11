#!/usr/bin/env python3
"""
引用核验脚本

通过以下方式发现虚构引用：
1. DOI 解析（通过 doi.org）
2. 基础元数据匹配（标题相似度、年份匹配）
3. URL 可访问性核验
4. 幻觉模式检测（泛化标题、可疑结构）
5. 标记可疑条目供人工复核

用法：
    python verify_citations.py --report [路径]
    python verify_citations.py --report [路径] --strict  # 任一未核验即失败

不需要 API key，使用免费 DOI 解析器与启发式规则。
"""

import sys
import argparse
import ipaddress
import os
import re
import socket
from pathlib import Path
from typing import List, Dict, Tuple
from urllib import request, error
from urllib.parse import quote, urlparse
import json
import time
from datetime import datetime


# 明确需要拒绝的地址段（不用 ip.is_private，避免把沙箱/基准测试网段
# 198.18.0.0/15 误判为私有地址而阻断正常公网访问）。
_BLOCKED_V4 = [
    ipaddress.ip_network('0.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('100.64.0.0/10'),   # CGNAT
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'),  # 链路本地 / 云元数据
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
]
_BLOCKED_V6 = [
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),        # 唯一本地地址
    ipaddress.ip_network('fe80::/10'),       # 链路本地
]


def _is_blocked_ip(ip) -> bool:
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in net for net in _BLOCKED_V4)
    return any(ip in net for net in _BLOCKED_V6)


# 安全：只允许 http/https，且解析后的地址不得是回环/私有/链路本地/保留地址。
# 报告中的 URL 来自不可信网页，必须防止被诱导访问本机或云元数据端点（SSRF）。
def is_safe_url(url: str) -> Tuple[bool, str]:
    """校验 URL 协议与目标地址是否允许访问。"""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, 'invalid URL'

    if parsed.scheme not in ('http', 'https'):
        return False, f'unsupported scheme: {parsed.scheme or "(none)"}'
    if not parsed.hostname:
        return False, 'no host'

    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or None)
    except Exception:
        return False, f'DNS resolution failed: {parsed.hostname}'

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, f'invalid address: {info[4][0]}'
        if _is_blocked_ip(ip):
            return False, f'blocked non-public address: {ip}'
    return True, ''


class CitationVerifier:
    """Verify citations in research report"""

    def __init__(self, report_path: Path, strict_mode: bool = False):
        self.report_path = report_path
        self.strict_mode = strict_mode
        self.content = self._read_report()
        self.suspicious = []
        self.verified = []
        self.errors = []

        # Hallucination detection patterns (2025 CiteGuard enhancement)
        self.suspicious_patterns = [
            # Generic academic-sounding but fake patterns
            (r'^(A |An |The )?(Study|Analysis|Review|Survey|Investigation) (of|on|into)',
             "Generic academic title pattern"),
            (r'^(Recent|Current|Modern|Contemporary) (Advances|Developments|Trends) in',
             "Generic 'advances' title pattern"),
            # Too perfect, templated titles
            (r'^[A-Z][a-z]+ [A-Z][a-z]+: A (Comprehensive|Complete|Systematic) (Review|Analysis|Guide)$',
             "Too perfect, templated structure"),
        ]

    def _read_report(self) -> str:
        """读取报告文件。"""
        try:
            with open(self.report_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"错误：无法读取报告：{e}")
            sys.exit(1)

    def extract_bibliography(self) -> List[Dict]:
        """Extract bibliography entries from report"""
        # Accept English or Chinese bibliography headings.
        pattern = r'##\s*(?:Bibliography|References|参考文献)[^\n]*\n(.*?)(?=\n##\s|\Z)'
        match = re.search(pattern, self.content, re.DOTALL | re.IGNORECASE)

        if not match:
            self.errors.append("No Bibliography section found")
            return []

        bib_section = match.group(1)

        # Parse entries: [N] Author (Year). "Title". Venue. URL
        entries = []
        lines = bib_section.strip().split('\n')

        current_entry = None
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检查是否以引用编号开头：[N] 或 N.
            match_num = re.match(r'^\[(\d+)\]\s+(.+)$', line) or re.match(r'^(\d+)[.、)）]\s+(.+)$', line)
            if match_num:
                if current_entry:
                    entries.append(current_entry)

                num = match_num.group(1)
                rest = match_num.group(2)

                # 尝试解析：Author (Year). "Title". Venue. URL，或中文 Markdown 链接格式
                year_match = re.search(r'[（(](\d{4})[）)]', rest)
                title_match = re.search(r'"([^"]+)"', rest)
                md_link_match = re.search(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', rest)
                doi_match = re.search(r'doi\.org/(10\.\S+)', rest)
                url_match = re.search(r'(?:https?|file)://[^\s\)]+', rest)

                current_entry = {
                    'num': num,
                    'raw': rest,
                    'year': year_match.group(1) if year_match else None,
                    'title': title_match.group(1) if title_match else (md_link_match.group(1) if md_link_match else None),
                    'doi': doi_match.group(1) if doi_match else None,
                    'url': url_match.group(0) if url_match else None
                }
            elif current_entry:
                # Multi-line entry, append to raw
                current_entry['raw'] += ' ' + line

        if current_entry:
            entries.append(current_entry)

        return entries

    def verify_doi(self, doi: str) -> Tuple[bool, Dict]:
        """
        Verify DOI exists and get metadata.
        Returns (success, metadata_dict)
        """
        if not doi:
            return False, {}

        try:
            # Use content negotiation to get JSON metadata
            url = f"https://doi.org/{quote(doi)}"
            req = request.Request(url)
            req.add_header('Accept', 'application/vnd.citationstyles.csl+json')

            with request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

                return True, {
                    'title': data.get('title', ''),
                    'year': data.get('issued', {}).get('date-parts', [[None]])[0][0],
                    'authors': [
                        f"{a.get('family', '')} {a.get('given', '')}"
                        for a in data.get('author', [])
                    ],
                    'venue': data.get('container-title', '')
                }
        except error.HTTPError as e:
            if e.code == 404:
                return False, {'error': 'DOI not found (404)'}
            return False, {'error': f'HTTP {e.code}'}
        except Exception as e:
            return False, {'error': str(e)}

    def verify_url(self, url: str) -> Tuple[bool, str]:
        """
        Verify URL is accessible (2025 CiteGuard enhancement).
        Returns (accessible, status_message)

        安全：先做协议/地址白名单校验（防 SSRF）；HEAD 被 403/405/501 拒绝时
        回退 GET（Range: bytes=0-0），避免不支持 HEAD 的站点被误判。
        """
        if not url:
            return False, "No URL"

        safe, reason = is_safe_url(url)
        if not safe:
            return False, f"blocked: {reason}"

        def _request(method: str) -> Tuple[bool, str, int]:
            req = request.Request(url, method=method)
            req.add_header('User-Agent', 'Mozilla/5.0 (Research Citation Verifier)')
            if method == 'GET':
                req.add_header('Range', 'bytes=0-0')
            try:
                with request.urlopen(req, timeout=10) as response:
                    code = response.status
                    # 2xx 与 3xx（urllib 已跟随重定向）视为可访问
                    ok = 200 <= code < 400
                    return ok, f"HTTP {code}", code
            except error.HTTPError as e:
                return False, f"HTTP {e.code}", e.code
            except error.URLError as e:
                return False, f"URL error: {e.reason}", 0
            except Exception as e:
                return False, f"Connection error: {str(e)[:50]}", 0

        ok, msg, code = _request('HEAD')
        if ok:
            return True, "URL accessible"

        # HEAD 不被支持/被拒时用 GET 复核
        if code in (403, 405, 501, 400):
            ok2, msg2, _ = _request('GET')
            if ok2:
                return True, "URL accessible (GET fallback)"
            return False, msg2

        return False, msg

    def detect_hallucination_patterns(self, entry: Dict) -> List[str]:
        """
        Detect common LLM hallucination patterns in citations (2025 CiteGuard).
        Returns list of detected issues.
        """
        issues = []
        title = entry.get('title', '')

        if not title:
            return issues

        # Check against suspicious patterns
        for pattern, description in self.suspicious_patterns:
            if re.match(pattern, title, re.IGNORECASE):
                issues.append(f"Suspicious title pattern: {description}")

        # Check for overly generic titles
        generic_words = ['overview', 'introduction', 'guide', 'handbook', 'manual']
        if any(word in title.lower() for word in generic_words) and len(title.split()) < 5:
            issues.append("Very generic short title")

        # Check for placeholder-like titles
        if any(x in title.lower() for x in ['tbd', 'todo', 'placeholder', 'example']):
            issues.append("Placeholder text in title")

        # Check for inconsistent metadata
        if entry.get('year'):
            year = int(entry['year'])
            current_year = datetime.now().year
            # Very recent without DOI or URL is suspicious
            if year >= current_year - 1 and not entry.get('doi') and not entry.get('url'):
                issues.append(f"Recent year ({year}) with no verification method")
            # Future year is definitely wrong
            if year > current_year:
                issues.append(f"Future year: {year} (current: {current_year})")
            # Very old with modern phrasing is suspicious
            if year < 2000 and any(word in title.lower() for word in ['ai', 'llm', 'gpt', 'transformer']):
                issues.append(f"Anachronistic: pre-2000 ({year}) citation mentioning modern AI terms")

        return issues

    def check_title_similarity(self, title1: str, title2: str) -> float:
        """
        Simple title similarity check (word overlap).
        Returns score 0.0-1.0
        """
        if not title1 or not title2:
            return 0.0

        # 归一化：小写、去标点、分词；中文补充 CJK bigram
        def normalize(s):
            s = s.lower()
            s = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', s)
            words = set(s.split())
            for run in re.findall(r'[\u4e00-\u9fff]+', s):
                if len(run) == 1:
                    words.add(run)
                else:
                    words.update(run[i:i + 2] for i in range(len(run) - 1))
            return words

        words1 = normalize(title1)
        words2 = normalize(title2)

        if not words1 or not words2:
            return 0.0

        overlap = len(words1 & words2)
        total = len(words1 | words2)

        return overlap / total if total > 0 else 0.0

    def verify_entry(self, entry: Dict) -> Dict:
        """Verify a single bibliography entry (Enhanced 2025 with CiteGuard)"""
        result = {
            'num': entry['num'],
            'status': 'unknown',
            'issues': [],
            'metadata': {},
            'verification_methods': []
        }

        # STEP 1: Run hallucination detection (CiteGuard 2025)
        hallucination_issues = self.detect_hallucination_patterns(entry)
        if hallucination_issues:
            result['issues'].extend(hallucination_issues)
            result['status'] = 'suspicious'

        # STEP 2: Has DOI?
        if entry['doi']:
            print(f"  [{entry['num']}] Checking DOI {entry['doi']}...", end=' ')
            success, metadata = self.verify_doi(entry['doi'])

            if success:
                result['metadata'] = metadata
                result['status'] = 'verified'
                print("")

                # Check title similarity if we have both
                if entry['title'] and metadata.get('title'):
                    similarity = self.check_title_similarity(
                        entry['title'],
                        metadata['title']
                    )

                    if similarity < 0.5:
                        result['issues'].append(
                            f"Title mismatch (similarity: {similarity:.1%})"
                        )
                        result['status'] = 'suspicious'

                # Check year match
                if entry['year'] and metadata.get('year'):
                    if int(entry['year']) != int(metadata['year']):
                        result['issues'].append(
                            f"Year mismatch: report says {entry['year']}, DOI says {metadata['year']}"
                        )
                        result['status'] = 'suspicious'

            else:
                print(f"✗ {metadata.get('error', 'Failed')}")
                result['status'] = 'unverified'
                result['issues'].append(f"DOI resolution failed: {metadata.get('error', 'unknown')}")

        # STEP 2.5: 本地 file:// 引用——不联网，但必须真实存在；
        # 存在记 local_ok（计入已核验），不存在记 unverified（strict 下失败）。
        if (entry.get('url') or '').startswith('file://'):
            raw_path = entry['url'][7:]
            if re.match(r'^/[A-Za-z]:', raw_path):
                raw_path = raw_path[1:]
            local_path = raw_path.replace('/', os.sep)
            if os.path.exists(local_path):
                result['status'] = 'local_ok'
                result['verification_methods'].append('LOCAL')
                result['issues'].append('本地文件存在，未做内容核验')
            else:
                result['status'] = 'unverified'
                result['issues'].append(f'本地文件不存在：{local_path}')
            return result

        # STEP 3: Check URL accessibility (if no DOI or DOI failed)
        if entry['url'] and result['status'] != 'verified':
            url_ok, url_status = self.verify_url(entry['url'])
            if url_ok:
                result['verification_methods'].append('URL')
                # Upgrade status if URL verifies
                if result['status'] in ['unknown', 'no_doi', 'unverified']:
                    result['status'] = 'url_verified'
                print(f"  [{entry['num']}] URL accessible ✓")
            else:
                result['issues'].append(f"URL check failed: {url_status}")

        # STEP 4: Final fallback - no verification method
        if not entry['doi'] and not entry['url']:
            if 'No DOI provided' not in ' '.join(result['issues']):
                result['issues'].append("No DOI or URL - cannot verify")
            result['status'] = 'suspicious'

        return result

    def verify_all(self):
        """Verify all bibliography entries"""
        print(f"\n{'='*60}")
        print(f"CITATION VERIFICATION: {self.report_path.name}")
        print(f"{'='*60}\n")

        entries = self.extract_bibliography()

        if not entries:
            print("未找到参考文献条目\n")
            return False

        print(f"Found {len(entries)} citations\n")

        results = []
        for entry in entries:
            # 单条损坏不得中断整轮核验：记录为 unverified 并继续。
            try:
                result = self.verify_entry(entry)
            except Exception as e:
                result = {
                    'num': entry.get('num', '?'),
                    'status': 'unverified',
                    'issues': [f'核验异常：{type(e).__name__}: {str(e)[:80]}'],
                    'metadata': {},
                    'verification_methods': [],
                }
            results.append(result)

            # Rate limiting
            time.sleep(0.5)

        # Summarize
        print(f"\n{'='*60}")
        print(f"VERIFICATION SUMMARY")
        print(f"{'='*60}\n")

        verified = [r for r in results if r['status'] == 'verified']
        url_verified = [r for r in results if r['status'] == 'url_verified']
        suspicious = [r for r in results if r['status'] == 'suspicious']
        local_ok = [r for r in results if r['status'] == 'local_ok']
        unverified = [r for r in results if r['status'] in ['unverified', 'no_doi', 'unknown']]

        print(f'DOI Verified: {len(verified)}/{len(results)}')
        print(f'URL Verified: {len(url_verified)}/{len(results)}')
        print(f'Local files verified: {len(local_ok)}/{len(results)}')
        print(f'Suspicious: {len(suspicious)}/{len(results)}')
        print(f'Unverified: {len(unverified)}/{len(results)}')
        print()

        if suspicious:
            print('SUSPICIOUS CITATIONS (Manual Review Needed):')
            for r in suspicious:
                print(f"\n  [{r['num']}]")
                for issue in r['issues']:
                    print(f"    - {issue}")
            print()

        if unverified and len(unverified) > 0:
            print('UNVERIFIED CITATIONS (Could not check):')
            for r in unverified:
                print(f"  [{r['num']}] {r['issues'][0] if r['issues'] else 'Unknown'}")
            print()

        # Decision (Enhanced 2025 - DOI / URL / local file 均算已核验)
        total_verified = len(verified) + len(url_verified) + len(local_ok)

        if suspicious:
            print('WARNING: Suspicious citations detected')
            if self.strict_mode:
                print('  STRICT MODE: Failing due to suspicious citations')
                return False
            else:
                print('  (Continuing in non-strict mode)')

        if self.strict_mode and unverified:
            print('STRICT MODE: Unverified citations found')
            return False

        if total_verified == 0:
            print('FAIL: No citation could be verified (0 verified)')
            return False

        if total_verified / len(results) < 0.5:
            print('WARNING: Less than 50% citations verified')
            return True  # Pass with warning
        else:
            print('CITATION VERIFICATION PASSED')
            return True


def main():
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(
        description="核验研究报告中的引用真实性（DOI/URL/元数据/幻觉模式）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python verify_citations.py --report 研究报告.md

说明：需要联网检查 DOI；使用免费 DOI 解析器，无需 API key。
        """
    )

    parser.add_argument(
        '--report', '-r',
        type=str,
        required=True,
        help='研究报告 Markdown 文件路径'
    )

    parser.add_argument(
        '--strict',
        action='store_true',
        help='严格模式：存在未核验或可疑引用时失败'
    )

    args = parser.parse_args()
    report_path = Path(args.report)

    if not report_path.exists():
        print(f"错误：找不到报告文件：{report_path}")
        sys.exit(1)

    verifier = CitationVerifier(report_path, strict_mode=args.strict)
    passed = verifier.verify_all()

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
