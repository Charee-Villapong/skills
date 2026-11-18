"""lint_detectors の誤検出修正の回帰テスト（2026-11 の Gemini レビュー指摘対応）。

    uv run --with sudachipy --with sudachidict-core python dev/test_lint_detector_fixes.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/natural-japanese/scripts"))

from lint_detectors import detect_structural_ai_habits  # noqa: E402


def bold_count(text):
    _, stats = detect_structural_ai_habits(text)
    return stats["bold_span_count"]


class BoldLabelTests(unittest.TestCase):
    def test_three_digit_numbered_labels_are_not_counted(self):
        # 「100. **ラベル**:」のラベル太字は、番号の桁数によらず数えない。
        text = "\n".join(f"{100 + i}. **ラベル{i}**: 説明文です。" for i in range(3))
        self.assertEqual(bold_count(text), 0)

    def test_one_digit_numbered_labels_are_not_counted(self):
        text = "\n".join(f"{i}. **ラベル{i}**: 説明文です。" for i in range(1, 4))
        self.assertEqual(bold_count(text), 0)

    def test_bullet_labels_are_not_counted(self):
        self.assertEqual(bold_count("- **ラベル**: 説明文です。"), 0)
        self.assertEqual(bold_count("* **ラベル**: 説明文です。"), 0)

    def test_plain_bold_labels_are_not_counted(self):
        self.assertEqual(bold_count("**ラベル**: 説明文です。"), 0)

    def test_emphasis_bold_is_counted(self):
        text = "本文の**強調**です。次の**強調**です。さらに**強調**です。"
        self.assertEqual(bold_count(text), 3)

    def test_emphasis_after_three_digit_label_is_counted(self):
        text = "100. **ラベル**: **強調**を含む説明文です。"
        self.assertEqual(bold_count(text), 1)


if __name__ == "__main__":
    unittest.main()
