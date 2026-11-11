#!/usr/bin/env python3
"""
证据库（Evidence Store）—— deep-research 4.0 的追加式证据持久化。

CLI 子命令：
  init         在 run 目录创建空的 证据.jsonl
  add          追加一条证据，返回 evidence_id
  list         列出证据，可按 source_id 过滤
  export       以 JSON 数组导出全部证据

证据身份：
  evidence_id = sha256(source_id + normalized_quote + locator)[:16]

所有状态均为追加式 JSONL；证据一旦采集不再修改。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

from _json_input import load_json_input


ARTIFACT_EVIDENCE = '证据.jsonl'

# ---------------------------------------------------------------------------
# 证据 ID 计算
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r'\s+')


def normalize_quote(quote: str) -> str:
    """归一化空白，保证哈希稳定。"""
    return _WHITESPACE_RE.sub(' ', quote.strip()).lower()


def compute_evidence_id(source_id: str, quote: str, locator: str | None) -> str:
    """sha256(source_id + normalized_quote + locator)[:16] 十六进制。"""
    payload = source_id + normalize_quote(quote) + (locator or '')
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSONL 读写辅助（共享 _jsonl，统一 UTF-8 / 原子写 / 缺失语义）
# ---------------------------------------------------------------------------

from _jsonl import append_jsonl, read_jsonl  # noqa: E402


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    """若不存在则创建空的 证据.jsonl。"""
    out_dir = os.path.abspath(args.dir)
    path = os.path.join(out_dir, ARTIFACT_EVIDENCE)
    if not os.path.exists(path):
        os.makedirs(out_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8'):
            pass
    print(json.dumps({'status': 'ok', 'path': path}, ensure_ascii=False))


def cmd_add(args: argparse.Namespace) -> None:
    """追加一条证据并输出 evidence_id。"""
    data = load_json_input(args.json, args.json_file)
    source_id = data.get('source_id', '')
    quote = data.get('quote', '')
    if not source_id or not quote:
        print(
            json.dumps({'error': 'source_id 与 quote 为必填字段'}, ensure_ascii=False),
            file=sys.stderr,
        )
        sys.exit(1)

    locator = data.get('locator')
    evidence_id = compute_evidence_id(source_id, quote, locator)
    evidence_path = os.path.join(args.dir, ARTIFACT_EVIDENCE)

    # 去重
    existing = read_jsonl(evidence_path)
    for row in existing:
        if row.get('evidence_id') == evidence_id:
            print(json.dumps({
                'status': 'duplicate',
                'evidence_id': evidence_id,
            }, ensure_ascii=False))
            return

    valid_types = {'direct_quote', 'paraphrase', 'data_point', 'methodology', 'official_statement'}
    evidence_type = data.get('evidence_type', 'direct_quote')
    if evidence_type not in valid_types:
        evidence_type = 'direct_quote'

    row = {
        'evidence_id': evidence_id,
        'source_id': source_id,
        'retrieval_query': data.get('retrieval_query'),
        'locator': locator,
        'quote': quote,
        'evidence_type': evidence_type,
        'captured_at': datetime.now(timezone.utc).isoformat(),
    }
    append_jsonl(evidence_path, row)
    print(json.dumps({
        'status': 'added',
        'evidence_id': evidence_id,
        'source_id': source_id,
    }, ensure_ascii=False))


def cmd_list(args: argparse.Namespace) -> None:
    """列出证据，可按来源过滤。"""
    evidence_path = os.path.join(args.dir, ARTIFACT_EVIDENCE)
    rows = read_jsonl(evidence_path)

    if args.source_id:
        rows = [r for r in rows if r.get('source_id') == args.source_id]

    # 按 evidence_id 去重
    seen = set()
    unique = []
    for r in rows:
        eid = r.get('evidence_id')
        if eid not in seen:
            seen.add(eid)
            unique.append(r)

    print(json.dumps({
        'count': len(unique),
        'evidence': unique,
    }, indent=2, ensure_ascii=False))


def cmd_export(args: argparse.Namespace) -> None:
    """以 JSON 数组导出全部证据。"""
    evidence_path = os.path.join(args.dir, ARTIFACT_EVIDENCE)
    rows = read_jsonl(evidence_path)

    seen = set()
    unique = []
    for r in rows:
        eid = r.get('evidence_id')
        if eid not in seen:
            seen.add(eid)
            unique.append(r)

    print(json.dumps(unique, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(
        prog='evidence_store',
        description='deep-research 4.0 的追加式证据持久化工具',
    )
    sub = parser.add_subparsers(dest='command', required=True, help='子命令')

    p_init = sub.add_parser('init', help='创建空的 证据.jsonl')
    p_init.add_argument('--dir', required=True, help='run 目录')

    p_add = sub.add_parser('add', help='追加一条证据')
    p_add.add_argument('--json', default=None, help='包含 source_id、quote、locator、evidence_type、retrieval_query 的 JSON；传 - 从标准输入读取')
    p_add.add_argument('--json-file', default=None, help='从 UTF-8 JSON 文件读取证据对象（PowerShell 下推荐）')
    p_add.add_argument('--dir', required=True, help='包含 证据.jsonl 的 run 目录')

    p_list = sub.add_parser('list', help='列出证据')
    p_list.add_argument('--dir', required=True, help='run 目录')
    p_list.add_argument('--source-id', default=None, help='按 source_id 过滤')

    p_export = sub.add_parser('export', help='以 JSON 数组导出全部证据')
    p_export.add_argument('--dir', required=True, help='run 目录')

    args = parser.parse_args()

    dispatch = {
        'init': cmd_init,
        'add': cmd_add,
        'list': cmd_list,
        'export': cmd_export,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
