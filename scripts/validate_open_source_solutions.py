#!/usr/bin/env python3
"""校验开源方案登记表（开源方案.jsonl）及其报告章节。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_FIELDS = {
    "name",
    "canonical_url",
    "forge",
    "description",
    "license",
    "last_activity_at",
    "retrieved_at",
    "implementation_mechanism",
    "evidence_url",
    "verification_status",
    "fit",
    "risks",
}
VERIFICATION_STATUSES = {
    "code_verified",
    "release_verified",
    "documentation_only",
    "unverified",
}
FIT_VALUES = {"reuse", "reference", "human_in_the_loop", "research_only", "reject"}
SECTION_RE = re.compile(r"^##\s+(?:开源方案全景|Open-Source Solutions Landscape)\s*$", re.MULTILINE)


def load_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"第 {line_number} 行：JSON 无效：{error}") from error
        if not isinstance(row, dict):
            raise ValueError(f"第 {line_number} 行：应为 JSON 对象")
        row["_line"] = line_number
        rows.append(row)
    return rows


def validate_no_results(row: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in ("attempted_forges", "queries", "retrieved_at", "reason"):
        if not row.get(field):
            errors.append(f"第 {row['_line']} 行：无结果记录缺少 {field}")
    if len(row.get("attempted_forges", [])) < 1:
        errors.append(f"第 {row['_line']} 行：attempted_forges 不能为空")
    return errors


def validate_solution(row: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    missing = sorted(field for field in REQUIRED_FIELDS if row.get(field) in (None, ""))
    if missing:
        errors.append(f"第 {row['_line']} 行：缺少字段：{', '.join(missing)}")
    if not str(row.get("canonical_url", "")).startswith("https://"):
        errors.append(f"第 {row['_line']} 行：canonical_url 必须使用 https")
    if not str(row.get("evidence_url", "")).startswith("https://"):
        errors.append(f"第 {row['_line']} 行：evidence_url 必须使用 https")
    if row.get("verification_status") not in VERIFICATION_STATUSES:
        errors.append(f"第 {row['_line']} 行：verification_status 无效")
    if row.get("fit") not in FIT_VALUES:
        errors.append(f"第 {row['_line']} 行：fit 无效")
    if not isinstance(row.get("risks"), list):
        errors.append(f"第 {row['_line']} 行：risks 必须是 JSON 数组")
    return errors


def main() -> int:
    from _console import setup_console_encoding
    setup_console_encoding()
    parser = argparse.ArgumentParser(description="校验 开源方案.jsonl 与报告中的开源方案章节")
    parser.add_argument("--artifact", type=Path, required=True, help="开源方案.jsonl 路径")
    parser.add_argument("--report", type=Path, help="研究报告 Markdown 路径（可选）")
    parser.add_argument("--strict", action="store_true", help="把警告也视为错误")
    args = parser.parse_args()

    errors: List[str] = []
    warnings: List[str] = []
    if not args.artifact.exists():
        errors.append(f"找不到产物文件：{args.artifact}")
        rows: List[Dict[str, Any]] = []
    else:
        try:
            rows = load_rows(args.artifact)
        except ValueError as error:
            rows = []
            errors.append(str(error))

    if not rows and not errors:
        errors.append("产物文件没有任何记录")

    urls = set()
    no_result_rows = [row for row in rows if row.get("status") == "no_qualifying_repositories"]
    if no_result_rows:
        if len(rows) != 1:
            errors.append("无结果记录不能与方案记录混在同一文件")
        errors.extend(validate_no_results(no_result_rows[0]))
    else:
        for row in rows:
            errors.extend(validate_solution(row))
            url = row.get("canonical_url")
            if url in urls:
                errors.append(f"第 {row['_line']} 行：canonical_url 重复：{url}")
            urls.add(url)

    if args.report:
        if not args.report.exists():
            errors.append(f"找不到报告：{args.report}")
        else:
            report = args.report.read_text(encoding="utf-8")
            if not SECTION_RE.search(report):
                errors.append("报告缺少「## 开源方案全景」章节")
            for url in sorted(urls):
                if url not in report:
                    warnings.append(f"报告未链接该仓库：{url}")

    if args.strict and warnings:
        errors.extend(warnings)

    payload = {
        "status": "pass" if not errors else "fail",
        "records": len(rows),
        "solutions": len(urls),
        "no_qualifying_repositories": bool(no_result_rows),
        "warnings": warnings,
        "errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
