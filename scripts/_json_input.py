#!/usr/bin/env python3
"""JSON 参数输入辅助：解决 Windows PowerShell 传递内层双引号被剥离的问题。

用法（二选一）：
  --json '{"key": "value"}'        # 简单场景；PowerShell 下需把内层引号写成 \\"
  --json @payload.json             # 从 UTF-8 文件读取（推荐）
  --json -                         # 从标准输入读取
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


def load_json_input(json_text: Optional[str], json_file: Optional[str] = None) -> dict:
    """从 --json / --json-file 读取并解析一个 JSON 对象。"""
    if json_file:
        text = Path(json_file).read_text(encoding='utf-8')
    elif json_text == '-':
        text = sys.stdin.read()
    elif json_text is not None:
        text = json_text
    else:
        raise ValueError('需要提供 --json 或 --json-file')

    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('JSON 输入必须是对象')
    return value
