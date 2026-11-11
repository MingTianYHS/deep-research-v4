#!/usr/bin/env python3
"""
原子论点抽取器（Atomic Claim Extractor）—— 把研究报告拆解为带类型的论点。

CLI 子命令：
  extract     解析中文/英文 Markdown 报告，抽取原子论点写入 论点.jsonl
  add         手工添加一条论点
  list        列出论点，可按章节或类型过滤
  stats       输出论点统计（按类型/状态计数）

论点身份：
  claim_id = sha256(section_id + normalized_text)[:16]

论点类型：
  - factual：缺少证据即硬失败
  - synthesis：需要可追溯性，阈值较软
  - recommendation：需要可追溯性，阈值较软
  - speculation：已标注即可，不强制证据
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

from _json_input import load_json_input


ARTIFACT_CLAIMS = '论点.jsonl'

# ---------------------------------------------------------------------------
# 论点 ID 计算
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r'\s+')


def normalize_text(text: str) -> str:
    """归一化空白与大小写，保证哈希稳定。"""
    return _WHITESPACE_RE.sub(' ', text.strip()).lower()


def compute_claim_id(section_id: str, text: str) -> str:
    """sha256(section_id + normalized_text)[:16] 十六进制。"""
    payload = section_id + normalize_text(text)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSONL 读写辅助（共享 _jsonl，统一 UTF-8 / 原子写 / 缺失语义）
# ---------------------------------------------------------------------------

from _jsonl import append_jsonl, read_jsonl, write_jsonl  # noqa: E402


# ---------------------------------------------------------------------------
# 报告解析辅助
# ---------------------------------------------------------------------------

# 章节标题别名：中文为主，保留英文兼容。可匹配「## 一、执行摘要」「## 1. 执行摘要」等编号前缀。
_CN_NUM = r'(?:[一二三四五六七八九十百]+|\d+)'
_NUM_PREFIX = rf'(?:{_CN_NUM}[、.．)）]\s*)?'

SECTION_PATTERNS = [
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:执行摘要|摘要|概要|Executive\s+Summary)', re.I), 'executive_summary'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:引言|导言|简介|Introduction)', re.I), 'introduction'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:决策指南|Decision\s+Guide)', re.I), 'decision_guide'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:主要发现|正文|Main\s+Analysis)', re.I), 'main_analysis'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:发现|Finding)\s*(\d+)', re.I), lambda m: f'finding_{m.group(1)}'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:开源方案全景|Open[- ]Source\s+Solutions?(?:\s+Landscape)?)', re.I), 'open_source_solutions'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:分析综合|综合分析|综合|Synthesis(?:\s*&\s*Insights)?)', re.I), 'synthesis'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:局限与说明|局限性|研究局限|局限|Limitations?(?:\s*&\s*Caveats)?)', re.I), 'limitations'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:建议|推荐建议|Recommendations?)', re.I), 'recommendations'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:结论|Conclusion)', re.I), 'conclusion'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:参考文献|参考资料|References|Bibliography)', re.I), 'bibliography'),
    (re.compile(rf'^##\s*{_NUM_PREFIX}(?:方法论附录|方法论|研究方法|Methodology(?:\s+Appendix)?)', re.I), 'methodology'),
    (re.compile(r'^##\s+(.+)', re.I), lambda m: _fallback_section_id(m.group(1))),
]

# 引用标记 [N] 或 [N, M]
CITATION_RE = re.compile(r'\[(\d+(?:,\s*\d+)*)\]')

# 中文句末标点：。！？；英文句末标点：.!?
_CN_SENTENCE_END_RE = re.compile(r'([。！？!?]+[”’」』）)]*)')
_EN_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

# 纯引用/来源标注行，不应成为论点
_CITATION_ONLY_RE = re.compile(
    r'^(?:来源|资料来源|Sources?|References?)[:：]?\s*(?:\[\d+(?:\s*,\s*\d+)*\]\s*[,，、]?\s*)+$',
    re.I,
)


def _fallback_section_id(heading: str) -> str:
    """把未识别的标题转成稳定的 section_id（保留中文）。"""
    text = re.sub(rf'^{_NUM_PREFIX}', '', heading.strip())
    text = re.sub(r'[^\w\u4e00-\u9fff]+', '_', text).strip('_').lower()
    return text[:30] or 'other'


def classify_claim(text: str, section_id: str) -> str:
    """基于关键词与章节的中文/英文论点类型判定。"""
    lower = text.lower()

    # 建议类关键词
    recommendation_words = [
        '应该', '应当', '建议', '推荐', '必须', '最好', '不妨', '须',
        '不宜', '宜采用', '宜选择', '可采用', '应采取', '需要考虑', '需要评估',
        'should', 'recommend', 'suggest', 'advise', 'consider',
    ]
    if any(w in lower for w in recommendation_words):
        return 'recommendation'

    # 推测类关键词
    speculation_words = [
        '可能', '或许', '也许', '有望', '推测', '假设性', '若假设', '尚不确定',
        '未来可能', '预计将', '不排除', '大概会',
        'might', 'could potentially', 'it is possible', 'may eventually',
        'hypothetically', 'speculatively',
    ]
    if any(w in lower for w in speculation_words):
        return 'speculation'

    # 综合/结论章节默认视为综合判断，但建议与推测优先级更高
    if section_id in ('synthesis', 'conclusion'):
        return 'synthesis'

    # 综合类关键词
    synthesis_words = [
        '总体', '综合', '整体', '综上', '由此', '这表明', '这说明',
        '这意味着', '由此可见', '结合起来',
        'overall', 'taken together', 'collectively',
        'the evidence suggests', 'this implies',
    ]
    if any(w in lower for w in synthesis_words):
        return 'synthesis'

    return 'factual'


def classify_materiality(text: str, claim_type: str, section_id: str = '') -> str:
    """按 A/B/C/D 对论点做启发式材料性分级。

    A 类硬事实必须同时满足：是 factual、位于事实型章节、且包含带单位的
    量化信息（百分比、金额、数量等）。仅出现年份（如「2026年」）不算 A，
    避免把「本报告研究 2026 年出口」这类背景句误判为硬事实。
    B 类背景；C 类分析/综合/建议；D 类推测。
    """
    if claim_type == 'speculation':
        return 'D'
    if claim_type in ('synthesis', 'recommendation'):
        return 'C'

    quantitative = re.search(
        r'\d+(?:\.\d+)?\s*(?:%|％|万|亿|美元|元|人民币|人|辆|台|吨|公里|小时|倍|个百分点)',
        text,
    )
    if not quantitative:
        return 'B'

    factual_sections = {
        'executive_summary', 'main_analysis', 'finding', 'decision_guide', 'open_source_solutions',
    }
    # finding_N 章节按 main_analysis 处理
    is_factual_section = section_id in factual_sections or section_id.startswith('finding_')
    if is_factual_section:
        return 'A'

    # 其他章节中出现带单位的量化信息，若同时含事实性动词，也按 A 处理
    if re.search(r'达到|增长|下降|占比|规模|均价|出口量|产量|销量|收入|利润|成本', text):
        return 'A'
    return 'B'


def _h1_patterns() -> list:
    """当报告只用一级标题（# ）时，把 ## 模式降级为 # 模式复用。"""
    out = []
    for pattern, id_or_fn in SECTION_PATTERNS:
        src = pattern.pattern.replace(r'^##', r'^#', 1)
        out.append((re.compile(src, pattern.flags), id_or_fn))
    return out


def parse_sections(markdown: str) -> list[tuple[str, str]]:
    """把 Markdown 解析为 (section_id, content) 列表。

    优先识别二级标题；若全文没有 ## 但存在多个 # 标题，则按一级标题切分，
    避免「只用 # 的合法报告」被整体当作 preamble 跳过。
    """
    has_h2 = re.search(r'^##\s', markdown, re.M) is not None
    h1_count = len(re.findall(r'^#\s', markdown, re.M))
    patterns = SECTION_PATTERNS if (has_h2 or h1_count <= 1) else _h1_patterns()

    lines = markdown.split('\n')
    sections = []
    current_id = 'preamble'
    current_lines = []

    for line in lines:
        matched = False
        for pattern, id_or_fn in patterns:
            m = pattern.match(line)
            if m:
                if current_lines:
                    sections.append((current_id, '\n'.join(current_lines)))
                current_id = id_or_fn(m) if callable(id_or_fn) else id_or_fn
                current_lines = []
                matched = True
                break
        if not matched:
            current_lines.append(line)

    if current_lines:
        sections.append((current_id, '\n'.join(current_lines)))

    return sections


def _visible_length(text: str) -> int:
    """中文按字、拉丁按词计数，用于过滤碎片。"""
    cjk = len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]', text))
    latin = len(re.findall(r'[A-Za-z0-9]+', text))
    return cjk + latin


def split_sentences(line: str) -> list[str]:
    """按中英文句末标点切分单行文本。"""
    # 先按中文句末标点切分，保留标点与右引号/右括号
    chunks = _CN_SENTENCE_END_RE.split(line)
    merged: list[str] = []
    buf = ''
    for chunk in chunks:
        if not chunk:
            continue
        if _CN_SENTENCE_END_RE.fullmatch(chunk):
            buf += chunk
            merged.append(buf)
            buf = ''
        else:
            buf += chunk
    if buf.strip():
        merged.append(buf)

    # 再对每个片段做英文句末切分（句号 + 空格 + 大写开头）
    sentences: list[str] = []
    for chunk in merged:
        sentences.extend(_EN_SENTENCE_SPLIT_RE.split(chunk))

    # 句末引用（「……。[1]」）会被切成独立碎片；把它并回前一句，
    # 否则引用编号会丢失，link-claims 无法关联来源。
    merged_sentences: list[str] = []
    citation_only = re.compile(r'^\[\d+(?:\s*,\s*\d+)*\]$')
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        if citation_only.match(s) and merged_sentences:
            merged_sentences[-1] = merged_sentences[-1].rstrip() + s
        else:
            merged_sentences.append(sentence)
    return merged_sentences


def extract_sentences(text: str) -> list[str]:
    """把章节正文切成句子，过滤 Markdown 噪声与过短碎片。"""
    # 去掉粗体/斜体标记
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    result = []
    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('#'):
            continue
        from_table = False
        if line.startswith('|'):
            # 表格分隔行（|---|---|）跳过
            if re.fullmatch(r'[\s|:\-]+', line):
                continue
            # 表格单元格拼成一句，保留表内 A 类量化事实（不再整表跳过）
            cells = [c.strip() for c in line.strip('|').split('|') if c.strip()]
            line = '，'.join(cells)
            if not re.search(r'\d', line):
                continue  # 无数字的表头/描述行不作为硬事实候选
            from_table = True
        if re.fullmatch(r'[-*_]{3,}', line):
            continue
        # 去掉无序/有序列表标记
        line = re.sub(r'^[-*+]\s+', '', line)
        line = re.sub(r'^\d+[.、)）]\s*', '', line)
        line = line.strip()
        if not line:
            continue

        # 表格单元格是浓缩事实，碎片阈值放宽；正文仍用 10 过滤噪声
        min_len = 4 if from_table else 10
        for sentence in split_sentences(line):
            sentence = sentence.strip()
            if not sentence or sentence.startswith('#'):
                continue
            if _CITATION_ONLY_RE.match(sentence):
                continue
            # 「……。[1]下一句」中，[1] 属于前一句：移到前一句末尾
            lead_cite = re.match(r'^(\[\d+(?:\s*,\s*\d+)*\])(.+)$', sentence)
            if lead_cite and result:
                result[-1] = result[-1].rstrip() + lead_cite.group(1)
                sentence = lead_cite.group(2).strip()
                if not sentence:
                    continue
            if _visible_length(sentence) >= min_len:
                result.append(sentence)

    return result


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_extract(args: argparse.Namespace) -> None:
    """从 Markdown 报告抽取原子论点。"""
    report_path = args.report
    if not os.path.exists(report_path):
        print(json.dumps({'error': f'找不到报告：{report_path}'}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    with open(report_path, encoding='utf-8') as f:
        markdown = f.read()

    claims_path = os.path.join(args.dir, ARTIFACT_CLAIMS)
    existing_ids = {r['claim_id'] for r in read_jsonl(claims_path)}

    sections = parse_sections(markdown)
    added = 0
    skipped = 0
    current_ids = set()

    skip_sections = {'preamble', 'bibliography', 'methodology'}
    for section_id, content in sections:
        if section_id in skip_sections:
            continue
        sentences = extract_sentences(content)
        for sentence in sentences:
            claim_id = compute_claim_id(section_id, sentence)
            current_ids.add(claim_id)
            if claim_id in existing_ids:
                skipped += 1
                continue

            # 抽取句子中的引用编号
            citation_nums = []
            for m in CITATION_RE.finditer(sentence):
                nums = [int(n.strip()) for n in m.group(1).split(',')]
                citation_nums.extend(nums)

            claim_type = classify_claim(sentence, section_id)
            claim = {
                'claim_id': claim_id,
                'section_id': section_id,
                'text': sentence,
                'claim_type': claim_type,
                'materiality': classify_materiality(sentence, claim_type, section_id),
                'cited_source_ids': [],  # 由链接步骤填充
                'evidence_ids': [],  # 由 verify_claim_support 回填命中的证据 ID
                'support_status': 'unverified',
                'extracted_at': datetime.now(timezone.utc).isoformat(),
                '_citation_numbers': citation_nums,  # 临时字段，供链接步骤使用
            }
            append_jsonl(claims_path, claim)
            existing_ids.add(claim_id)
            added += 1

    if added == 0 and skipped == 0:
        print(json.dumps({
            'status': 'error',
            'error': '未抽取到任何论点：报告可能缺少可识别章节（## 或单一 # 体系）或正文为空',
            'claims_added': 0,
        }, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    #  retire：本次报告未出现的旧论点标记 retired，避免改稿后旧 A 类论点
    #  永久残留并让 --strict 永远失败。
    all_claims = read_jsonl(claims_path)
    retired = 0
    for c in all_claims:
        if c.get('claim_id') not in current_ids and c.get('support_status') != 'retired':
            c['support_status'] = 'retired'
            retired += 1
    if retired:
        write_jsonl(claims_path, all_claims)

    print(json.dumps({
        'status': 'ok',
        'claims_added': added,
        'claims_skipped': skipped,
        'claims_retired': retired,
        'total_claims': len(existing_ids),
    }, ensure_ascii=False))


def cmd_add(args: argparse.Namespace) -> None:
    """手工添加一条论点。"""
    data = load_json_input(args.json, args.json_file)
    section_id = data.get('section_id', 'unknown')
    text = data.get('text', '')
    if not text:
        print(json.dumps({'error': 'text 为必填字段'}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    claim_id = compute_claim_id(section_id, text)
    claims_path = os.path.join(args.dir, ARTIFACT_CLAIMS)

    existing = read_jsonl(claims_path)
    for row in existing:
        if row.get('claim_id') == claim_id:
            print(json.dumps({'status': 'duplicate', 'claim_id': claim_id}, ensure_ascii=False))
            return

    valid_types = {'factual', 'synthesis', 'recommendation', 'speculation'}
    claim_type = data.get('claim_type', 'factual')
    if claim_type not in valid_types:
        claim_type = 'factual'

    materiality = data.get('materiality')
    if materiality not in ('A', 'B', 'C', 'D'):
        materiality = classify_materiality(text, claim_type, section_id)

    claim = {
        'claim_id': claim_id,
        'section_id': section_id,
        'text': text,
        'claim_type': claim_type,
        'materiality': materiality,
        'cited_source_ids': data.get('cited_source_ids', []),
        'evidence_ids': data.get('evidence_ids', []),
        'support_status': 'unverified',
        'extracted_at': datetime.now(timezone.utc).isoformat(),
    }
    append_jsonl(claims_path, claim)
    print(json.dumps({'status': 'added', 'claim_id': claim_id}, ensure_ascii=False))


def cmd_list(args: argparse.Namespace) -> None:
    """列出论点，支持过滤。"""
    claims_path = os.path.join(args.dir, ARTIFACT_CLAIMS)
    rows = read_jsonl(claims_path)

    if args.section:
        rows = [r for r in rows if r.get('section_id') == args.section]
    if args.type:
        rows = [r for r in rows if r.get('claim_type') == args.type]
    if args.status:
        rows = [r for r in rows if r.get('support_status') == args.status]

    # 去重
    seen = set()
    unique = []
    for r in rows:
        cid = r.get('claim_id')
        if cid not in seen:
            seen.add(cid)
            unique.append(r)

    print(json.dumps({'count': len(unique), 'claims': unique}, indent=2, ensure_ascii=False))


def cmd_stats(args: argparse.Namespace) -> None:
    """输出论点统计。"""
    claims_path = os.path.join(args.dir, ARTIFACT_CLAIMS)
    rows = read_jsonl(claims_path)

    seen = set()
    unique = []
    for r in rows:
        cid = r.get('claim_id')
        if cid not in seen:
            seen.add(cid)
            unique.append(r)

    by_type = {}
    by_status = {}
    by_section = {}
    for r in unique:
        t = r.get('claim_type', 'unknown')
        s = r.get('support_status', 'unknown')
        sec = r.get('section_id', 'unknown')
        by_type[t] = by_type.get(t, 0) + 1
        by_status[s] = by_status.get(s, 0) + 1
        by_section[sec] = by_section.get(sec, 0) + 1

    print(json.dumps({
        'total': len(unique),
        'by_type': by_type,
        'by_status': by_status,
        'by_section': by_section,
    }, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(
        prog='extract_claims',
        description='deep-research 4.0 的原子论点抽取与台账工具',
    )
    sub = parser.add_subparsers(dest='command', required=True, help='子命令')

    p_ext = sub.add_parser('extract', help='从 Markdown 报告抽取论点')
    p_ext.add_argument('--report', required=True, help='研究报告.md 的路径')
    p_ext.add_argument('--dir', required=True, help='包含 论点.jsonl 的 run 目录')

    p_add = sub.add_parser('add', help='手工添加一条论点')
    p_add.add_argument('--json', default=None, help='包含 section_id、text、claim_type 的 JSON；传 - 从标准输入读取')
    p_add.add_argument('--json-file', default=None, help='从 UTF-8 JSON 文件读取论点对象（PowerShell 下推荐）')
    p_add.add_argument('--dir', required=True, help='run 目录')

    p_list = sub.add_parser('list', help='列出论点')
    p_list.add_argument('--dir', required=True, help='run 目录')
    p_list.add_argument('--section', default=None, help='按 section_id 过滤')
    p_list.add_argument('--type', default=None, help='按 claim_type 过滤')
    p_list.add_argument('--status', default=None, help='按 support_status 过滤')

    p_stats = sub.add_parser('stats', help='论点统计')
    p_stats.add_argument('--dir', required=True, help='run 目录')

    args = parser.parse_args()
    dispatch = {
        'extract': cmd_extract,
        'add': cmd_add,
        'list': cmd_list,
        'stats': cmd_stats,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
