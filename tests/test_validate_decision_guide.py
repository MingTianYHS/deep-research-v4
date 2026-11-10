import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_decision_guide.py"


class DecisionGuideValidatorTests(unittest.TestCase):
    def run_validator(self, markdown: str):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "研究报告.md"
            report.write_text(markdown, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--report", str(report), "--strict"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
            )
            return result.returncode, json.loads(result.stdout)

    def test_accepts_svg_and_textual_outcomes(self):
        code, payload = self.run_validator("""## 决策指南

<svg data-decision-guide role="img"><title>Flow</title></svg>

### 选择结果

- 推荐 A
- 停止 B
- 前置条件 C

## 发现 1
""")
        self.assertEqual(0, code)
        self.assertEqual("pass", payload["status"])

    def test_rejects_table_only_selection(self):
        code, payload = self.run_validator("""## 决策指南

| 选项 | 分数 |
|---|---|
| A | 5 |
""")
        self.assertNotEqual(0, code)
        self.assertIn("决策指南缺少分支视觉（决策流程图/箭头/Mermaid/SVG）", payload["errors"])


if __name__ == "__main__":
    unittest.main()
