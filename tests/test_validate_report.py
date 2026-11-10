import importlib.util
import tempfile
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_report.py"
SPEC = importlib.util.spec_from_file_location("validate_report", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _report() -> str:
    return """# 测试研究报告

## 执行摘要

本报告研究测试主题的现状与趋势，基于多个公开来源进行交叉核对与综合分析[1]。核心结论是测试主题在2026年保持增长，但外部环境仍存在不确定性。报告同时给出可执行建议与后续研究方向。整体置信度为中等偏高。

## 引言

### 研究问题

本报告回答测试主题的现状、驱动因素与主要风险。

### 范围与方法

研究覆盖2025年至2026年的公开资料，采用多来源交叉验证方法。

## 正文

### 发现一：整体保持增长

2026年测试主题相关市场规模达到约1200亿元，同比增长18%[1]。增长主要由需求扩张与技术进步共同驱动。

## 分析综合

综合来看，测试主题的增长具有较强持续性，但需要关注政策与竞争格局变化[1]。

## 局限与说明

本研究依赖公开数据，部分口径可能存在差异，结论应结合具体场景使用。

## 建议

相关企业应当加强技术投入，并建立政策变化的监测机制。

## 参考文献

1. [测试来源](https://example.com/source)

## 方法论附录

研究采用公开资料检索与交叉核对，对关键数字进行至少两个来源比对。
"""


class ChineseReportValidationTests(unittest.TestCase):
    def _validator(self, text: str, run_dir_name: str = "topic_研究_20261028", nested: bool = True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        run_dir = base / "research" / run_dir_name if nested else base / run_dir_name
        run_dir.mkdir(parents=True, exist_ok=True)
        report = run_dir / "研究报告.md"
        report.write_text(text, encoding="utf-8")
        return MODULE.ReportValidator(report)

    def test_valid_chinese_report_passes(self):
        validator = self._validator(_report())
        self.assertTrue(validator.validate())
        self.assertEqual(validator.errors, [])

    def test_figures_check_removed(self):
        self.assertFalse(hasattr(MODULE.ReportValidator, "_check_figures"))
        self.assertFalse(hasattr(MODULE.ReportValidator, "FIGURE_MINIMUM"))

    def test_missing_bibliography_fails(self):
        text = _report().replace("## 参考文献", "## 其他")
        validator = self._validator(text)
        self.assertFalse(validator.validate())
        self.assertTrue(any("参考文献" in e for e in validator.errors))

    def test_bibliography_numbered_list_accepted(self):
        validator = self._validator(_report())
        self.assertTrue(validator._check_bibliography())
        self.assertEqual(validator.errors, [])


class OutputLocationCheckTests(unittest.TestCase):
    def _validator(self, run_dir_name: str, nested_under_research: bool = True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        run_dir = base / "research" / run_dir_name if nested_under_research else base / run_dir_name
        run_dir.mkdir(parents=True, exist_ok=True)
        report = run_dir / "研究报告.md"
        report.write_text(_report(), encoding="utf-8")
        return MODULE.ReportValidator(report)

    def test_conventional_directory_passes_silently(self):
        validator = self._validator("topic_研究_20261028")
        self.assertTrue(validator._check_output_location())
        self.assertFalse(any("research/" in w for w in validator.warnings))

    def test_collision_suffix_still_passes(self):
        validator = self._validator("topic_研究_20261028_2")
        self.assertTrue(validator._check_output_location())
        self.assertFalse(validator.warnings)

    def test_english_suffix_warns(self):
        validator = self._validator("topic_Research_20261028")
        self.assertTrue(validator._check_output_location())
        self.assertTrue(any("研究" in w for w in validator.warnings))

    def test_missing_container_warns(self):
        validator = self._validator("topic_研究_20261028", nested_under_research=False)
        self.assertTrue(validator._check_output_location())
        self.assertTrue(any("research/" in w for w in validator.warnings))

    def test_warning_points_at_resolver(self):
        validator = self._validator("random_place", nested_under_research=False)
        validator._check_output_location()
        self.assertTrue(any("citation_manager.py" in w for w in validator.warnings))


if __name__ == "__main__":
    unittest.main()
