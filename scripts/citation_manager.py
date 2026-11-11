#!/usr/bin/env python3
"""
来源与运行清单管理器（Citation Manager）—— 稳定的来源身份与 run 清单管理。

CLI 子命令：
  init-run                创建 运行清单.json 与空的 JSONL 产物
  register-source         登记来源到 来源.jsonl，返回 source_id
  assign-display-numbers  生成 stable_id -> 显示编号 的映射
  export-bibliography     从 来源.jsonl 生成参考文献

来源身份：
  source_id = sha256(canonical_locator)[:16]
  canonical_locator = doi:...、arxiv:... 或规范化后的 URL

所有状态均为追加式 JSONL，不在状态文件中保存可变的引用编号。

run 目录约定：
  省略 --out-dir 时，init-run 根据研究问题解析 run 目录，约定唯一由
  resolve_run_dir() 负责，其他脚本与校验器应导入而不是重复实现：

    <cwd>/research/<主题>_研究_<YYYYMMDD>/
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from _json_input import load_json_input


# ---------------------------------------------------------------------------
# run 目录与产物文件约定
# ---------------------------------------------------------------------------

CONTAINER = 'research'
SUFFIX = '研究'

# 运行产物统一使用中文文件名，所有脚本共享同一约定。
ARTIFACT_SOURCES = '来源.jsonl'
ARTIFACT_EVIDENCE = '证据.jsonl'
ARTIFACT_CLAIMS = '论点.jsonl'
ARTIFACT_REPORT = '研究报告.md'
ARTIFACT_MANIFEST = '运行清单.json'
ARTIFACT_PLAN = '研究计划.md'
ARTIFACT_OPEN_SOURCE = '开源方案.jsonl'

ARTIFACT_PATHS = {
    'plan': ARTIFACT_PLAN,
    'sources': ARTIFACT_SOURCES,
    'evidence': ARTIFACT_EVIDENCE,
    'claims': ARTIFACT_CLAIMS,
    'report': ARTIFACT_REPORT,
    'open_source_solutions': ARTIFACT_OPEN_SOURCE,
}

# Windows 下非法字符，以及会让目录名难以在任何位置引用的分隔符和 shell 元字符。
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r'\s+')
_REPEATED_UNDERSCORE = re.compile(r'_+')
_EDGE_JUNK = ' ._'
# 匹配 `<主题>_研究_<YYYYMMDD>`，允许可选的 _2/_3 冲突后缀。
RUN_DIR_RE = re.compile(rf'_{SUFFIX}_\d{{8}}(?:_\d+)?$')


def slugify_topic(topic: str, max_length: int = 60) -> str:
    """把研究主题转换为一个安全的路径片段。

    中文、字母、数字和连字符保留；空白与非法字符折叠为单个下划线。
    主题不做翻译，保证提问者仍能一眼认出目录。
    """
    text = _ILLEGAL_CHARS.sub('_', topic.strip())
    text = _WHITESPACE.sub('_', text)
    text = _REPEATED_UNDERSCORE.sub('_', text)
    text = text.strip(_EDGE_JUNK)

    if len(text) > max_length:
        text = text[:max_length].rstrip(_EDGE_JUNK)

    return text


def resolve_run_dir(topic: str, base=None, date=None, create: bool = False) -> Path:
    """返回主题对应的 run 目录，重名时自动追加 _2/_3。

    同一天同一主题的两次研究不能共用目录：产物文件是追加式的，
    共用目录会把两次无关研究的证据静默混在一起。
    """
    root = Path(base) if base is not None else Path.cwd()
    slug = slugify_topic(topic) or 'untitled'
    stamp = (date or datetime.now()).strftime('%Y%m%d')
    folder = f'{slug}_{SUFFIX}_{stamp}'
    target = root / CONTAINER / folder

    if not create:
        return target

    # 用 mkdir 的 FileExistsError 作为唯一判定（check-then-mkdir 有竞态，
    # 并发调用会共用同一目录、把两次研究的证据静默混在一起）。
    candidate = target
    index = 2
    while True:
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            candidate = root / CONTAINER / f'{folder}_{index}'
            index += 1


def check_run_dir(path) -> list[str]:
    """返回 run 目录不符合约定之处；完全合规时返回空列表。"""
    path = Path(path)
    problems = []

    if path.parent.name != CONTAINER:
        problems.append(
            f"run 目录必须位于 '{CONTAINER}/' 目录内，当前父目录为 '{path.parent.name}'"
        )
    if not RUN_DIR_RE.search(path.name):
        problems.append(
            f"run 目录名必须以 '_{SUFFIX}_<YYYYMMDD>' 结尾，当前为 '{path.name}'"
        )
    if not path.is_dir():
        problems.append(f"run 目录不存在：{path}")

    return problems


# ---------------------------------------------------------------------------
# 规范化 locator
# ---------------------------------------------------------------------------

DOI_RE = re.compile(r'(?:https?://(?:dx\.)?doi\.org/|doi:)(10\.\d{4,}/\S+)', re.IGNORECASE)
ARXIV_RE = re.compile(r'(?:https?://arxiv\.org/abs/|arxiv:)(\d{4}\.\d{4,}(?:v\d+)?)', re.IGNORECASE)

# 只是追踪参数、不是内容标识的 URL 查询参数。
# 注意：不要删除 source/ref 这类可能承载内容语义的参数（?source=foo 与
# ?source=bar 可能是不同来源），只删明确的追踪前缀。
TRACKING_PARAMS = frozenset([
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'fbclid', 'gclid', 'mc_cid', 'mc_eid',
])


def canonicalize_locator(raw_url: str) -> str:
    """从原始 URL 或标识符字符串推导规范化 locator。

    优先级：DOI > arXiv > 规范化 URL。
    保留非默认端口（避免 :8080 与 :80 被误合并）；无 scheme 时补 https://。
    """
    # DOI（剥离尾随标点，避免同一 DOI 因 ')' / '.' 被拆成两个来源）
    m = DOI_RE.search(raw_url)
    if m:
        return 'doi:' + m.group(1).rstrip('.,;:)]}')

    # arXiv
    m = ARXIV_RE.search(raw_url)
    if m:
        return f'arxiv:{m.group(1)}'

    # 无 scheme 的裸域名补 https://，避免 urlparse 产出畸形 locator
    if '://' not in raw_url:
        raw_url = 'https://' + raw_url

    # 规范化 URL：小写 scheme 与 netloc（保留端口），去掉 fragment 与追踪参数
    parsed = urlparse(raw_url)
    scheme = (parsed.scheme or 'https').lower()
    netloc = (parsed.netloc or '').lower()
    path = parsed.path.rstrip('/')
    if parsed.query:
        pairs = []
        for part in parsed.query.split('&'):
            kv = part.split('=', 1)
            if kv[0].lower() not in TRACKING_PARAMS:
                pairs.append(part)
        query = '&'.join(sorted(pairs))
    else:
        query = ''
    return urlunparse((scheme, netloc, path, '', query, ''))


def compute_source_id(canonical_locator: str) -> str:
    """sha256(canonical_locator)[:16] 十六进制。"""
    return hashlib.sha256(canonical_locator.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSONL 读写辅助（共享 _jsonl，统一 UTF-8 / 原子写 / 缺失语义）
# ---------------------------------------------------------------------------

from _jsonl import append_jsonl, read_jsonl, write_jsonl  # noqa: E402


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_init_run(args: argparse.Namespace) -> None:
    """创建 运行清单.json 与空的 JSONL 产物文件。

    省略 --out-dir 时从 --query 解析 run 目录，调用方无需手工拼接
    `research/<主题>_研究_<YYYYMMDD>`。
    """
    if args.out_dir:
        out_dir = os.path.abspath(args.out_dir)
        os.makedirs(out_dir, exist_ok=True)
    elif args.query:
        out_dir = str(resolve_run_dir(args.query, create=True).resolve())
    else:
        print(
            json.dumps({'error': '请提供 --out-dir，或提供 --query 以解析 run 目录'}, ensure_ascii=False),
            file=sys.stderr,
        )
        sys.exit(1)

    # 未显式指定时由研究路径推导，避免 manifest 自相矛盾：
    # deep 路径默认 deep 验证强度；direct 路径默认直接型查询；其余默认 standard/depth。
    rigor = args.rigor or ('deep' if args.mode == 'deep' else 'standard')
    query_type = args.query_type or ('direct' if args.mode == 'direct' else 'depth')

    manifest = {
        'version': '4.1.0',
        'query': args.query or '',
        'query_type': query_type,
        'rigor': rigor,
        'mode': args.mode,
        'budget': args.budget,
        'language': args.language,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'finished_at': None,
        'assumptions': [],
        'provider_config': {
            'primary': 'web_search',
            'scholarly': None,
        },
        'report_dir': out_dir,
        'artifact_paths': dict(ARTIFACT_PATHS),
        'continuation': None,
    }

    manifest_path = os.path.join(out_dir, ARTIFACT_MANIFEST)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write('\n')

    # 创建空的追加式产物文件
    for name in (ARTIFACT_SOURCES, ARTIFACT_EVIDENCE, ARTIFACT_CLAIMS):
        p = os.path.join(out_dir, name)
        if not os.path.exists(p):
            with open(p, 'w', encoding='utf-8'):
                pass

    print(json.dumps({'status': 'ok', 'manifest': manifest_path, 'dir': out_dir}, ensure_ascii=False))


def cmd_finalize_run(args: argparse.Namespace) -> None:
    """收尾 run：写入 finished_at，并可追加关键假设。"""
    manifest_path = os.path.join(args.dir, ARTIFACT_MANIFEST)
    if not os.path.exists(manifest_path):
        print(
            json.dumps({'error': f'找不到运行清单：{manifest_path}'}, ensure_ascii=False),
            file=sys.stderr,
        )
        sys.exit(1)

    with open(manifest_path, encoding='utf-8') as f:
        manifest = json.load(f)

    finished_at = datetime.now(timezone.utc).isoformat()
    manifest['finished_at'] = finished_at

    assumptions = manifest.setdefault('assumptions', [])
    for text in (args.assumption or []):
        text = text.strip()
        if not text:
            continue
        assumption_id = 'asm_' + hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]
        assumptions.append({
            'assumption_id': assumption_id,
            'text': text,
            'materiality': args.assumption_materiality,
            'status': 'user_confirmed',
        })

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(json.dumps({
        'status': 'ok',
        'manifest': manifest_path,
        'finished_at': finished_at,
        'assumption_count': len(assumptions),
    }, ensure_ascii=False))


def cmd_register_source(args: argparse.Namespace) -> None:
    """登记来源，追加到 来源.jsonl，输出 source_id。"""
    data = load_json_input(args.json, args.json_file)
    raw_url = data.get('raw_url', data.get('url', ''))
    if not raw_url:
        print(json.dumps({'error': 'raw_url 为必填字段'}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    canonical = data.get('canonical_locator') or canonicalize_locator(raw_url)
    source_id = compute_source_id(canonical)

    sources_path = os.path.join(args.dir, ARTIFACT_SOURCES)

    # 去重
    existing = read_jsonl(sources_path)
    for row in existing:
        if row.get('source_id') == source_id:
            print(json.dumps({
                'status': 'duplicate',
                'source_id': source_id,
                'canonical_locator': canonical,
            }, ensure_ascii=False))
            return

    source = {
        'source_id': source_id,
        'canonical_locator': canonical,
        'raw_url': raw_url,
        'title': data.get('title', ''),
        'authors': data.get('authors'),
        'year': data.get('year'),
        'source_type': data.get('source_type', 'web'),
        'metadata_status': data.get('metadata_status', 'unverified'),
        'registered_at': datetime.now(timezone.utc).isoformat(),
    }
    append_jsonl(sources_path, source)
    print(json.dumps({
        'status': 'registered',
        'source_id': source_id,
        'canonical_locator': canonical,
    }, ensure_ascii=False))


def cmd_assign_display_numbers(args: argparse.Namespace) -> None:
    """读取 来源.jsonl，按登记顺序分配稳定的显示编号。"""
    sources_path = os.path.join(args.dir, ARTIFACT_SOURCES)
    sources = read_jsonl(sources_path)

    mapping = {}
    seen = set()
    index = 0
    for src in sources:
        sid = src['source_id']
        if sid in seen:
            continue
        seen.add(sid)
        index += 1
        mapping[sid] = index

    print(json.dumps(mapping, indent=2, ensure_ascii=False))


def cmd_link_claims(args: argparse.Namespace) -> None:
    """把 论点.jsonl 中的 _citation_numbers 映射为稳定 source_id。

    报告正文里的 [1]、[2] 是渲染用显示编号，按 来源.jsonl 的登记顺序
    （去重后）分配。本命令把每个论点的引用编号转成 source_id，供
    verify_claim_support.py 按来源汇总证据。
    """
    sources = read_jsonl(os.path.join(args.dir, ARTIFACT_SOURCES))
    claims_path = os.path.join(args.dir, ARTIFACT_CLAIMS)
    claims = read_jsonl(claims_path)

    # 先按 source_id 去重再编号，保证与 export-bibliography / assign-display-numbers
    # 三处编号一致（重复行不得消耗显示编号）。
    unique_sources = []
    seen = set()
    for src in sources:
        sid = src.get('source_id', '')
        if not sid or sid in seen:
            continue
        seen.add(sid)
        unique_sources.append(src)
    display_to_source = {i: s['source_id'] for i, s in enumerate(unique_sources, 1)}

    linked = 0
    unresolved = {}
    for claim in claims:
        numbers = claim.get('_citation_numbers') or []
        if not numbers:
            continue
        resolved = [display_to_source[n] for n in numbers if n in display_to_source]
        missing = [n for n in numbers if n not in display_to_source]
        for n in missing:
            unresolved[str(n)] = unresolved.get(str(n), 0) + 1
        # 以当前正文引用为准覆盖（只增不减会残留改稿前的旧来源）
        resolved = list(dict.fromkeys(resolved))
        if resolved != (claim.get('cited_source_ids') or []):
            claim['cited_source_ids'] = resolved
            linked += 1

    write_jsonl(claims_path, claims)
    print(json.dumps({
        'status': 'ok' if not unresolved else 'fail',
        'claims': len(claims),
        'linked': linked,
        'sources': len(display_to_source),
        'unresolved_citation_numbers': unresolved,
    }, ensure_ascii=False, indent=2))
    if unresolved:
        # 正文引用了不存在的显示编号 = 悬空引用，不得静默通过
        sys.exit(1)


def cmd_export_bibliography(args: argparse.Namespace) -> None:
    """从 来源.jsonl 生成参考文献。"""
    sources_path = os.path.join(args.dir, ARTIFACT_SOURCES)
    sources = read_jsonl(sources_path)

    # 按 source_id 去重，保持登记顺序
    seen = set()
    unique = []
    for src in sources:
        if src['source_id'] not in seen:
            seen.add(src['source_id'])
            unique.append(src)

    style = args.style

    if style == 'markdown':
        lines = ['## 参考文献', '']
        for i, src in enumerate(unique, 1):
            author_str = ''
            if src.get('authors'):
                authors = src['authors']
                if len(authors) == 1:
                    author_str = f'{authors[0]}. '
                elif len(authors) == 2:
                    author_str = f'{authors[0]} & {authors[1]}. '
                else:
                    author_str = f'{authors[0]} 等. '

            year_str = f'({src["year"]})' if src.get('year') else '(出版年不详)'
            title = src.get('title', '无标题')
            url = src.get('raw_url', '')
            lines.append(f'[{i}] {author_str}{year_str}. [{title}]({url})')
        print('\n'.join(lines))

    elif style == 'json':
        out = []
        for i, src in enumerate(unique, 1):
            out.append({
                'display_number': i,
                'source_id': src['source_id'],
                'canonical_locator': src['canonical_locator'],
                'title': src.get('title', ''),
                'authors': src.get('authors'),
                'year': src.get('year'),
                'raw_url': src.get('raw_url', ''),
            })
        print(json.dumps(out, indent=2, ensure_ascii=False))

    else:
        print(f'未知的参考文献样式：{style}', file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(
        prog='citation_manager',
        description='deep-research 4.0 的来源身份与运行清单管理器',
    )
    sub = parser.add_subparsers(dest='command', required=True, help='子命令')

    # init-run
    p_init = sub.add_parser('init-run', help='创建运行清单与空的产物文件')
    p_init.add_argument(
        '--out-dir',
        default=None,
        help='输出目录；省略时从 --query 解析 research/<主题>_研究_<YYYYMMDD>',
    )
    p_init.add_argument('--query', default='', help='原始研究问题')
    p_init.add_argument(
        '--mode',
        default='standard',
        choices=['direct', 'standard', 'deep'],
        help='研究路径：direct=直查、standard=标准研究、deep=深研（默认 standard）',
    )
    p_init.add_argument(
        '--query-type',
        default=None,
        choices=['direct', 'depth', 'breadth'],
        help='查询形态：direct=直接型、depth=深度优先、breadth=广度优先（默认由 --mode 推导：direct→direct，其余→depth）',
    )
    p_init.add_argument(
        '--rigor',
        default=None,
        choices=['standard', 'deep'],
        help='验证强度：standard 或 deep（默认由 --mode 推导：deep→deep，其余→standard）',
    )
    p_init.add_argument(
        '--budget',
        default='normal',
        choices=['normal', 'extended'],
        help='检索预算：normal 或 extended（extended 对应原 ultradeep 的加大预算）',
    )
    p_init.add_argument(
        '--language',
        default='zh',
        choices=['zh', 'en'],
        help='报告语言（默认 zh）',
    )

    # finalize-run
    p_fin = sub.add_parser('finalize-run', help='收尾 run：写入 finished_at 并追加关键假设')
    p_fin.add_argument('--dir', required=True, help='包含 运行清单.json 的 run 目录')
    p_fin.add_argument(
        '--assumption',
        action='append',
        default=None,
        help='追加一条关键假设，可重复传入',
    )
    p_fin.add_argument(
        '--assumption-materiality',
        default='medium',
        choices=['low', 'medium', 'high'],
        help='假设的重要程度（默认 medium）',
    )

    # register-source
    p_reg = sub.add_parser('register-source', help='登记来源并返回稳定 ID')
    p_reg.add_argument('--json', default=None, help='至少包含 raw_url 与 title 的 JSON 对象；传 - 从标准输入读取')
    p_reg.add_argument('--json-file', default=None, help='从 UTF-8 JSON 文件读取来源对象（PowerShell 下推荐）')
    p_reg.add_argument('--dir', required=True, help='包含 来源.jsonl 的 run 目录')

    # assign-display-numbers
    p_num = sub.add_parser('assign-display-numbers', help='把稳定来源 ID 映射为显示编号')
    p_num.add_argument('--dir', required=True, help='包含 来源.jsonl 的 run 目录')

    # link-claims
    p_link = sub.add_parser('link-claims', help='把论点的引用编号映射为稳定 source_id')
    p_link.add_argument('--dir', required=True, help='包含 来源.jsonl 与 论点.jsonl 的 run 目录')

    # export-bibliography
    p_bib = sub.add_parser('export-bibliography', help='从来源生成参考文献')
    p_bib.add_argument('--dir', required=True, help='包含 来源.jsonl 的 run 目录')
    p_bib.add_argument('--style', default='markdown', choices=['markdown', 'json'], help='输出样式')

    args = parser.parse_args()

    dispatch = {
        'init-run': cmd_init_run,
        'finalize-run': cmd_finalize_run,
        'register-source': cmd_register_source,
        'assign-display-numbers': cmd_assign_display_numbers,
        'link-claims': cmd_link_claims,
        'export-bibliography': cmd_export_bibliography,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
