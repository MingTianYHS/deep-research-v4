#!/usr/bin/env python3
"""
论点支撑校验（Claim-Support Verification）—— 检查证据是否支撑论点。

CLI 子命令：
  verify      校验全部论点与证据的支撑关系，更新 support_status
  report      生成可读的支撑校验摘要

v1 采用确定性、低成本的方法：实体、数字、年份与词面重叠检查，不调用 LLM。
中文句子使用 CJK 字符 bigram 作为词面 token，避免纯中文句子因缺少
拉丁字母 token 而被恒判为 needs_review。

只有 factual 论点在缺少支撑时硬失败；synthesis/recommendation 需要可追溯性，
但使用更软的阈值。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone


ARTIFACT_CLAIMS = '论点.jsonl'
ARTIFACT_EVIDENCE = '证据.jsonl'
ARTIFACT_SOURCES = '来源.jsonl'

# ---------------------------------------------------------------------------
# JSONL 读写辅助（全部显式 UTF-8）
# ---------------------------------------------------------------------------

def read_jsonl(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


# ---------------------------------------------------------------------------
# 支撑校验逻辑
# ---------------------------------------------------------------------------

# 数字（整数、小数、百分比）；不使用 \b，避免「增长30%」在中文与数字之间无边界的问题
NUMBER_RE = re.compile(r'\d+(?:\.\d+)?(?:\s*(?:%|％|x|X))?')

# 年份
YEAR_RE = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')

# 拉丁字母大写实体（朴素 NER）
ENTITY_RE = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b')

# 中文连续汉字片段（用于 CJK bigram）
CJK_RUN_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]+')

# 常见停用实体
STOP_ENTITIES = frozenset([
    'The', 'This', 'That', 'These', 'However', 'Furthermore',
    'Moreover', 'Additionally', 'Therefore', 'Nevertheless',
])

# 不同验证强度的阈值（direct 直查最宽松，deep 最严格）
PROFILE_THRESHOLDS = {
    'direct': {'supported': 0.50, 'partial': 0.25},
    'standard': {'supported': 0.60, 'partial': 0.35},
    'deep': {'supported': 0.68, 'partial': 0.42},
}


def extract_tokens(text: str) -> set[str]:
    """抽取显著 token：拉丁词（>=4 字符）+ 中文连续汉字的 bigram。"""
    tokens = set(re.findall(r'[a-z]{4,}', text.lower()))
    for run in CJK_RUN_RE.findall(text):
        if len(run) == 1:
            tokens.add(run)
        else:
            tokens.update(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def extract_numbers(text: str) -> set[str]:
    """抽取数字值（去掉内部空白，保证 30 % 与 30% 等价）。"""
    return {re.sub(r'\s+', '', m) for m in NUMBER_RE.findall(text)}


def extract_years(text: str) -> set[str]:
    """抽取年份。"""
    return set(YEAR_RE.findall(text))


def extract_entities(text: str) -> set[str]:
    """抽取拉丁字母大写实体。"""
    ents = set(ENTITY_RE.findall(text))
    return ents - STOP_ENTITIES


def compute_support_score(
    claim_text: str,
    evidence_quotes: list[str],
    profile: str = 'standard',
) -> tuple[str, float, str]:
    """
    计算论点在给定证据引文下的支撑状态。

    返回 (status, score, notes)。score 范围 0.0（无重叠）到 1.0（强支撑）。
    只有论点和证据都具备的信号才参与加权，避免「没有数字」被当成数字全匹配。
    """
    if not evidence_quotes:
        return ('unsupported', 0.0, '无关联证据')

    claim_tokens = extract_tokens(claim_text)
    claim_numbers = extract_numbers(claim_text)
    claim_years = extract_years(claim_text)
    claim_entities = extract_entities(claim_text)

    thresholds = PROFILE_THRESHOLDS.get(profile, PROFILE_THRESHOLDS['standard'])
    best_score = 0.0
    best_notes: list[str] = []

    for quote in evidence_quotes:
        ev_tokens = extract_tokens(quote)
        ev_numbers = extract_numbers(quote)
        ev_years = extract_years(quote)
        ev_entities = extract_entities(quote)

        # 词面重叠（Jaccard-like：相对论点 token 的覆盖率）
        token_overlap = len(claim_tokens & ev_tokens) / len(claim_tokens) if claim_tokens else 0.0

        components: list[tuple[str, float, float]] = [('token', token_overlap, 0.50)]

        if claim_numbers:
            components.append(('number', len(claim_numbers & ev_numbers) / len(claim_numbers), 0.25))
        if claim_years:
            components.append(('year', len(claim_years & ev_years) / len(claim_years), 0.15))
        if claim_entities:
            components.append(('entity', len(claim_entities & ev_entities) / len(claim_entities), 0.10))

        total_weight = sum(weight for _, _, weight in components)
        score = sum(value * weight for _, value, weight in components) / total_weight

        if score > best_score:
            best_score = score
            best_notes = []
            if token_overlap < 0.30:
                best_notes.append('词面重叠不足')
            if claim_numbers and len(claim_numbers & ev_numbers) / len(claim_numbers) < 0.5:
                best_notes.append('数字不一致')
            if claim_years and len(claim_years & ev_years) / len(claim_years) < 1.0:
                best_notes.append('年份不一致')
            if claim_entities and len(claim_entities & ev_entities) / len(claim_entities) < 0.3:
                best_notes.append('实体不一致')

    if best_score >= thresholds['supported']:
        status = 'supported'
    elif best_score >= thresholds['partial']:
        status = 'partial'
    else:
        status = 'needs_review'

    notes = '；'.join(best_notes) if best_notes else '重叠充分'
    return (status, round(best_score, 3), notes)


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def _is_hard_fact_claim(claim: dict) -> bool:
    """判断是否为 A 类硬事实；旧记录缺少 materiality 时按是否含数字推断。"""
    if claim.get('claim_type') != 'factual':
        return False
    materiality = claim.get('materiality')
    if materiality in ('A', 'B', 'C', 'D'):
        return materiality == 'A'
    return bool(re.search(r'\d', claim.get('text', '')))


def cmd_verify(args: argparse.Namespace) -> None:
    """校验全部论点与证据，更新 论点.jsonl。"""
    claims_path = os.path.join(args.dir, ARTIFACT_CLAIMS)
    evidence_path = os.path.join(args.dir, ARTIFACT_EVIDENCE)
    sources_path = os.path.join(args.dir, ARTIFACT_SOURCES)

    claims = read_jsonl(claims_path)
    evidence = read_jsonl(evidence_path)
    _sources = read_jsonl(sources_path)

    # 按 source_id 建证据索引
    ev_by_source: dict[str, list[str]] = {}
    ev_by_id: dict[str, dict] = {}
    for ev in evidence:
        sid = ev.get('source_id', '')
        eid = ev.get('evidence_id', '')
        ev_by_source.setdefault(sid, []).append(ev.get('quote', ''))
        ev_by_id[eid] = ev

    # 论点去重
    seen = set()
    unique_claims = []
    for c in claims:
        cid = c.get('claim_id')
        if cid not in seen:
            seen.add(cid)
            unique_claims.append(c)

    verified = 0
    updated_claims = []

    for claim in unique_claims:
        claim_type = claim.get('claim_type', 'factual')

        cited_ids = claim.get('cited_source_ids', [])
        evidence_ids = claim.get('evidence_ids', [])

        quotes = []
        for eid in evidence_ids:
            if eid in ev_by_id:
                quotes.append(ev_by_id[eid].get('quote', ''))

        for sid in cited_ids:
            if sid in ev_by_source:
                quotes.extend(ev_by_source[sid])

        if not quotes and not cited_ids and not evidence_ids:
            if claim_type == 'speculation':
                claim['support_status'] = 'supported'  # 推测不需要证据
            elif claim_type in ('synthesis', 'recommendation'):
                claim['support_status'] = 'needs_review'  # 需要可追溯性
            elif claim.get('materiality') == 'B':
                # B 类背景句允许不逐句引用，但应提示补充来源
                claim['support_status'] = 'needs_review'
            else:
                claim['support_status'] = 'unsupported'
        elif not quotes:
            claim['support_status'] = 'needs_review'
        else:
            status, score, notes = compute_support_score(
                claim['text'], quotes, profile=args.profile
            )
            claim['support_status'] = status
            claim['_support_score'] = score
            claim['_support_notes'] = notes

        verified += 1
        updated_claims.append(claim)

    write_jsonl(claims_path, updated_claims)

    status_counts = Counter(c.get('support_status') for c in updated_claims)
    factual_unsupported = sum(
        1 for c in updated_claims
        if c.get('claim_type') == 'factual' and c.get('support_status') == 'unsupported'
    )
    hard_factual_unsupported = sum(
        1 for c in updated_claims
        if _is_hard_fact_claim(c) and c.get('support_status') == 'unsupported'
    )
    total_factual = sum(1 for c in updated_claims if c.get('claim_type') == 'factual')

    # 按验证强度决定严格模式失败条件：
    # direct 只警告；standard 仅 A 类硬事实硬失败；deep 所有 factual 硬失败。
    passed = True
    if args.strict:
        if args.profile == 'standard':
            passed = hard_factual_unsupported == 0
        elif args.profile == 'deep':
            passed = factual_unsupported == 0

    print(json.dumps({
        'status': 'pass' if passed else 'fail',
        'profile': args.profile,
        'verified': verified,
        'support_status_counts': dict(status_counts),
        'factual_unsupported': factual_unsupported,
        'hard_factual_unsupported': hard_factual_unsupported,
        'total_factual': total_factual,
        'unsupported_rate': round(factual_unsupported / max(total_factual, 1), 3),
    }, indent=2, ensure_ascii=False))

    if not passed:
        sys.exit(1)


def cmd_report(args: argparse.Namespace) -> None:
    """生成可读的论点支撑校验报告。"""
    claims_path = os.path.join(args.dir, ARTIFACT_CLAIMS)
    claims = read_jsonl(claims_path)

    seen = set()
    unique = []
    for c in claims:
        cid = c.get('claim_id')
        if cid not in seen:
            seen.add(cid)
            unique.append(c)

    lines = ['# 论点支撑校验报告', '']

    status_counts = Counter(c.get('support_status') for c in unique)
    type_counts = Counter(c.get('claim_type') for c in unique)
    lines.append(f'**论点总数：** {len(unique)}')
    lines.append(f'**按类型：** {dict(type_counts)}')
    lines.append(f'**按状态：** {dict(status_counts)}')
    lines.append('')

    unsupported_factual = [
        c for c in unique
        if c.get('claim_type') == 'factual' and c.get('support_status') in ('unsupported', 'needs_review')
    ]
    if unsupported_factual:
        lines.append('## 缺少支撑或需复核的事实性论点')
        lines.append('')
        for c in unsupported_factual:
            lines.append(f'- [{c["support_status"]}] `{c["section_id"]}`：{c["text"][:100]}...')
            if c.get('_support_notes'):
                lines.append(f'  说明：{c["_support_notes"]}')
        lines.append('')
    else:
        lines.append('## 全部事实性论点均有充分支撑。')
        lines.append('')

    print('\n'.join(lines))


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(
        prog='verify_claim_support',
        description='deep-research 4.0 的论点支撑校验工具',
    )
    sub = parser.add_subparsers(dest='command', required=True, help='子命令')

    p_ver = sub.add_parser('verify', help='校验论点与证据的支撑关系')
    p_ver.add_argument('--dir', required=True, help='run 目录')
    p_ver.add_argument(
        '--profile',
        default='standard',
        choices=['direct', 'standard', 'deep'],
        help='验证强度：direct、standard 或 deep（deep 阈值更严格，默认 standard）',
    )
    p_ver.add_argument('--strict', action='store_true', help='存在无支撑的事实性论点时以退出码 1 失败')

    p_rep = sub.add_parser('report', help='生成支撑校验报告')
    p_rep.add_argument('--dir', required=True, help='run 目录')

    args = parser.parse_args()
    dispatch = {
        'verify': cmd_verify,
        'report': cmd_report,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
