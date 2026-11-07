"""C-004 同期担保テスト（特性テスト）: corpus/generate.py の run_claude() と
corpus/experiments/skill-eval/eval.py の run_claude_naive() の同一性。

eval.py の「素の生成」は、generate.py の run_claude() と同一条件で claude CLI を
呼ぶことに存在意義が依存する（eval.py の docstring にも「generate.py の
run_claude() と同一」と明記）。両ファイルに逐語複製されているこの呼び出しが
片方だけ変わったら検知できるよう、次を固定する。

- 定数 NONINTERACTIVE_SYSTEM_PROMPT / NEUTRAL_CWD の一致（現行値そのものも固定）
- subprocess.run へ渡す argv・cwd・timeout・その他の kwargs の一致
- プロンプトの渡し方（stdin ではなく argv の "-p" の次要素）の一致
- 戻り値（stdout を strip したもの）の一致
- 唯一の意図的な差分: eval 側だけが timeout を引数化している（既定値 300 は
  generate 側の直書き 300 と一致）。それ以外に差分が増えたら落ちる。

置き場所について: 本来は eval.py の隣（experiments/skill-eval/）が自然だが、
natural-japanese/.gitignore が同ディレクトリでは eval.py 等の許可リスト方式に
なっており新規ファイルはコミット対象にならないため、corpus/ 直下に置く。

実際の claude 呼び出しは subprocess.run のモックで切り離す。標準ライブラリのみ。

    python3 corpus/test_run_claude_sync_characterization.py
    # または（corpus/ で）
    python3 -m unittest test_run_claude_sync_characterization -v
"""

import importlib.util
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

CORPUS_DIR = Path(__file__).resolve().parent
SKILL_EVAL_DIR = CORPUS_DIR / "experiments" / "skill-eval"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generate = load("corpus_generate", CORPUS_DIR / "generate.py")
skill_eval = load("skill_eval_eval", SKILL_EVAL_DIR / "eval.py")

PROMPT = "季節の移ろいを感じた瞬間についてブログ記事を書いて。"
MODEL = "claude-sonnet-5"
FAKE_STDOUT = "  サンプルの本文です。\n"


def capture_call(module, func, *args, **kwargs):
    """module の subprocess.run をモックし、func の呼び出し1回分を記録する。

    戻り値: (func の戻り値, argv リスト, subprocess.run への kwargs dict)
    """
    calls = []

    def fake_run(argv, **run_kwargs):
        calls.append((list(argv), dict(run_kwargs)))
        return SimpleNamespace(stdout=FAKE_STDOUT)

    with mock.patch.object(module.subprocess, "run", fake_run):
        returned = func(*args, **kwargs)
    assert len(calls) == 1, f"subprocess.run の呼び出しは1回のはず: {calls!r}"
    argv, run_kwargs = calls[0]
    return returned, argv, run_kwargs


class ConstantSyncTests(unittest.TestCase):
    def test_system_prompt_is_identical(self):
        self.assertEqual(
            generate.NONINTERACTIVE_SYSTEM_PROMPT,
            skill_eval.NONINTERACTIVE_SYSTEM_PROMPT,
        )

    def test_system_prompt_current_value(self):
        expected = (
            "これは1往復のみの非対話バッチ呼び出しです。フォローアップの質問はできません。"
            "確認や許可を求めず、指示に対して適切と思う内容を自分で判断し、"
            "記事本文だけをそのまま出力してください。"
        )
        self.assertEqual(generate.NONINTERACTIVE_SYSTEM_PROMPT, expected)
        self.assertEqual(skill_eval.NONINTERACTIVE_SYSTEM_PROMPT, expected)

    def test_neutral_cwd_is_identical(self):
        self.assertEqual(generate.NEUTRAL_CWD, skill_eval.NEUTRAL_CWD)

    def test_neutral_cwd_current_value(self):
        # 素の実行用 cwd は両者ともリポジトリ外の "/tmp"（現行値）。
        self.assertEqual(generate.NEUTRAL_CWD, "/tmp")
        self.assertEqual(skill_eval.NEUTRAL_CWD, "/tmp")


class SignatureSyncTests(unittest.TestCase):
    def test_signatures_differ_only_in_timeout_parameter(self):
        gen_params = list(inspect.signature(generate.run_claude).parameters)
        eval_params = list(inspect.signature(skill_eval.run_claude_naive).parameters)
        self.assertEqual(gen_params, ["prompt", "model"])
        self.assertEqual(eval_params, ["prompt", "model", "timeout"])

    def test_eval_default_timeout_matches_generate(self):
        default = inspect.signature(skill_eval.run_claude_naive).parameters["timeout"].default
        self.assertEqual(default, 300)


class RunClaudeCallSyncTests(unittest.TestCase):
    def capture_both(self):
        gen = capture_call(generate, generate.run_claude, PROMPT, MODEL)
        ev = capture_call(skill_eval, skill_eval.run_claude_naive, PROMPT, MODEL)
        return gen, ev

    def test_argv_is_identical(self):
        (_, gen_argv, _), (_, eval_argv, _) = self.capture_both()
        self.assertEqual(gen_argv, eval_argv)

    def test_argv_current_shape(self):
        expected = [
            "claude",
            "-p",
            PROMPT,
            "--model",
            MODEL,
            "--disallowed-tools",
            "*",
            "--append-system-prompt",
            generate.NONINTERACTIVE_SYSTEM_PROMPT,
        ]
        (_, gen_argv, _), (_, eval_argv, _) = self.capture_both()
        self.assertEqual(gen_argv, expected)
        self.assertEqual(eval_argv, expected)

    def test_run_kwargs_are_identical(self):
        (_, _, gen_kwargs), (_, _, eval_kwargs) = self.capture_both()
        self.assertEqual(gen_kwargs, eval_kwargs)

    def test_run_kwargs_current_values(self):
        expected = {
            "capture_output": True,
            "text": True,
            "timeout": 300,
            "check": True,
            "cwd": "/tmp",
        }
        (_, _, gen_kwargs), (_, _, eval_kwargs) = self.capture_both()
        self.assertEqual(gen_kwargs, expected)
        self.assertEqual(eval_kwargs, expected)

    def test_cwd_comes_from_each_modules_neutral_cwd(self):
        (_, _, gen_kwargs), (_, _, eval_kwargs) = self.capture_both()
        self.assertEqual(gen_kwargs["cwd"], generate.NEUTRAL_CWD)
        self.assertEqual(eval_kwargs["cwd"], skill_eval.NEUTRAL_CWD)

    def test_prompt_is_passed_via_argv_not_stdin(self):
        # 入力の渡し方: 両者ともプロンプトは "-p" の次要素として argv で渡し、
        # stdin への input は使わない。
        (_, gen_argv, gen_kwargs), (_, eval_argv, eval_kwargs) = self.capture_both()
        for argv, kwargs in ((gen_argv, gen_kwargs), (eval_argv, eval_kwargs)):
            self.assertEqual(argv[1], "-p")
            self.assertEqual(argv[2], PROMPT)
            self.assertNotIn("input", kwargs)
            self.assertNotIn("stdin", kwargs)

    def test_return_value_is_stripped_stdout_for_both(self):
        (gen_returned, _, _), (eval_returned, _, _) = self.capture_both()
        self.assertEqual(gen_returned, FAKE_STDOUT.strip())
        self.assertEqual(eval_returned, FAKE_STDOUT.strip())
        self.assertEqual(gen_returned, eval_returned)

    def test_eval_explicit_timeout_changes_only_timeout(self):
        # 唯一の意図的な差分: eval 側は timeout を差し替えられる。その場合でも
        # argv と timeout 以外の kwargs は generate 側と完全一致する。
        (_, gen_argv, gen_kwargs), (_, _, _) = self.capture_both()
        _, eval_argv, eval_kwargs = capture_call(
            skill_eval, skill_eval.run_claude_naive, PROMPT, MODEL, timeout=123
        )
        self.assertEqual(eval_kwargs["timeout"], 123)
        self.assertEqual(eval_argv, gen_argv)
        self.assertEqual(
            {k: v for k, v in eval_kwargs.items() if k != "timeout"},
            {k: v for k, v in gen_kwargs.items() if k != "timeout"},
        )


if __name__ == "__main__":
    unittest.main()
