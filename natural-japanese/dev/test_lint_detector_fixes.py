"""lint 系スクリプトの誤検出・不具合修正の回帰テスト（2026-11 の Gemini レビュー指摘対応）。

    uv run --with sudachipy --with sudachidict-core python dev/test_lint_detector_fixes.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills/natural-japanese/scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lint_detectors import (  # noqa: E402
    detect_low_specificity,
    detect_structural_ai_habits,
)
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


@unittest.skipUnless(shutil.which("git"), "git が必要")
class NewFactsGitEncodingTests(unittest.TestCase):
    def test_git_mode_works_under_non_utf8_locale(self):
        # newfacts.py --git は git show の出力を encoding="utf-8" で読む。
        # ロケール任せだと、UTF-8 でない環境で日本語の原文がデコードできず
        # UnicodeDecodeError で落ちる（修正前の実挙動）。
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                subprocess.run(
                    ["git", *args], cwd=repo, check=True, capture_output=True
                )

            git("init", "-q", ".")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "test")
            draft = repo / "draft.md"
            draft.write_text(
                "これは元の文書です。会議の内容をまとめました。\n", encoding="utf-8"
            )
            git("add", ".")
            git("commit", "-qm", "init")
            draft.write_text(
                "これは元の文書です。会議の内容をまとめました。"
                "NewFrameworkを導入しました。\n",
                encoding="utf-8",
            )
            env = dict(os.environ)
            env.update(
                {
                    "LC_ALL": "C",
                    "LANG": "C",
                    "PYTHONCOERCECLOCALE": "0",
                    "PYTHONUTF8": "0",
                    "PYTHONIOENCODING": "utf-8",
                }
            )
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "newfacts.py"), "--git", "draft.md"],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("newframework", proc.stdout)


class SemanticTrustRemoteCodeTests(unittest.TestCase):
    """semantic.load_model の trust_remote_code 既定値と有効化経路。

    torch / sentence_transformers は重い依存なので、偽モジュールで
    差し替えて SentenceTransformer へ渡る引数だけを確かめる。
    """

    def _load(self, name, env_value, **kwargs):
        import semantic

        calls = {}

        class FakeSentenceTransformer:
            def __init__(self, model_name, device=None, trust_remote_code=None):
                calls["trust_remote_code"] = trust_remote_code

        fake_torch = types.SimpleNamespace(
            backends=types.SimpleNamespace(
                mps=types.SimpleNamespace(is_available=lambda: False)
            ),
            cuda=types.SimpleNamespace(is_available=lambda: False),
        )
        fake_st = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
        env = {} if env_value is None else {"SEMANTIC_TRUST_REMOTE_CODE": env_value}
        with mock.patch.dict(
            sys.modules, {"torch": fake_torch, "sentence_transformers": fake_st}
        ), mock.patch.dict(os.environ, env):
            if env_value is None:
                os.environ.pop("SEMANTIC_TRUST_REMOTE_CODE", None)
            semantic.load_model(name, **kwargs)
        return calls["trust_remote_code"]

    def test_default_is_false(self):
        self.assertIs(self._load("fake-model-default", None), False)

    def test_env_var_enables(self):
        self.assertIs(self._load("fake-model-env", "1"), True)

    def test_explicit_argument_enables(self):
        self.assertIs(
            self._load("fake-model-arg", None, trust_remote_code=True), True
        )

    def test_explicit_argument_wins_over_env(self):
        self.assertIs(
            self._load("fake-model-override", "1", trust_remote_code=False), False
        )


if __name__ == "__main__":
    unittest.main()
