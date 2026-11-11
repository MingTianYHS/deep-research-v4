#!/usr/bin/env python3
"""共享 JSONL 读写助手：统一 UTF-8、原子写与「缺失 vs 空」语义。

四个证据链模块（citation_manager / evidence_store / extract_claims /
verify_claim_support）共用本模块，避免各自复制 read/write/append 导致
修一处漏三处。
"""

import json
import os


def read_jsonl(path: str, required: bool = False) -> list[dict]:
    """逐行读取 JSONL。

    required=True 时文件缺失抛 FileNotFoundError（用于校验路径，
    防止「文件不存在」被静默当作空集而假通过）；默认缺失返回 []。
    """
    if not os.path.exists(path):
        if required:
            raise FileNotFoundError(path)
        return []
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: str, obj: dict) -> None:
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def write_jsonl(path: str, rows: list[dict]) -> None:
    """原子重写：先写临时文件再替换，避免中断/磁盘满留下半截 JSONL。"""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    os.replace(tmp, path)
