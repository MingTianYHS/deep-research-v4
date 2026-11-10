#!/usr/bin/env python3
"""CLI 控制台编码辅助：统一把 stdout/stderr 设为 UTF-8，兼容 Windows GBK 控制台。"""

import sys


def setup_console_encoding() -> None:
    """在可用时把标准输出/错误流重设为 UTF-8，避免中文与 emoji 触发编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
