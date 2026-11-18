"""lint_detectors の誤検出修正の回帰テスト（2026-11 の Gemini レビュー指摘対応）。

    uv run --with sudachipy --with sudachidict-core python dev/test_lint_detector_fixes.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/natural-japanese/scripts"))

from lint_detectors import detect_low_specificity, detect_structural_ai_habits  # noqa: E402
from textcore import mask_markdown_structure  # noqa: E402


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


ABSTRACT_PARAGRAPH = (
    "この課題は、状況の変化や背景にある要因を踏まえ、観点や視点の違いを意識しながら、"
    "全体の傾向と側面を見極めていくことが重要であり、その重要性は今後ますます"
    "高まっていくと考えられる。"
)


def fired_count(text):
    # 本番（run_lint）と同じく、マスク済みテキストを lines、原文を
    # raw_lines_by_no として渡す。
    masked = mask_markdown_structure(text)
    lines = [(i + 1, line) for i, line in enumerate(masked.split("\n"))]
    raw_by_no = {i + 1: line for i, line in enumerate(text.split("\n"))}
    findings, stats = detect_low_specificity(lines, raw_by_no)
    return stats["paragraphs_fired"], [f.category for f in findings]


class LowSpecificityImageTests(unittest.TestCase):
    def test_abstract_paragraph_fires(self):
        fired, categories = fired_count(ABSTRACT_PARAGRAPH)
        self.assertEqual(fired, 1)
        self.assertIn("low_specificity", categories)

    def test_image_filenames_do_not_inflate_specificity(self):
        # 画像のファイル名（英字の識別子らしい文字列）が固有名詞として
        # 数えられると、具体性スコアが水増しされて検出が消えてしまう。
        images = "".join(f"![図{i}](diagram-part-{i}-overview.png)" for i in range(8))
        fired, categories = fired_count(ABSTRACT_PARAGRAPH + images)
        self.assertEqual(fired, 1)
        self.assertIn("low_specificity", categories)


if __name__ == "__main__":
    unittest.main()
