"""C-008 特性テスト（現状固定）: reader-study app.py の実験条件値。

テスト係が実装本体を見ず、既存テスト（test_app.py）・事前登録
（preregistration.md）・README から得た仕様と、公開インターフェース
（assignment / validate_submission）への入出力確認だけで書いた。
既存の test_app.py 4件では境界が固定されていない実験条件値
（回答件数・参加者ID長・評価範囲・理解問題の範囲・回答時間の範囲・
注意確認の範囲・刺激ID集合）だけを固定する。
app.py の定数化リファクタリング（C-008）でこれらの現行値が変われば、
このテストが落ちて検知できることが目的であり、値の変更を提案する
ものではない。
"""

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reader_app", HERE / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def fake_stimuli():
    # test_app.py の fake_stimuli と同じ形（12項目・3条件・三択で正答0）。
    return [{
        "id": f"item-{i:02}", "genre": "test",
        "variants": {condition: f"{condition}-{i}" for condition in app.CONDITIONS},
        "question": {"prompt": "正しいものは？", "choices": ["A", "B", "C"], "answer": 0},
    } for i in range(12)]


def valid_payload(participant_id="participant-0001"):
    stimuli = fake_stimuli()
    answers = [{
        "item_id": item["id"], "condition": item["condition"],
        "monotony": 4, "naturalness": 4, "readability": 4,
        "comprehension": 0, "elapsed_ms": 15000,
    } for item in app.assignment(participant_id, stimuli)]
    payload = {
        "participant_id": participant_id, "attention_check": 4,
        "answers": answers,
    }
    return payload, stimuli


def set_all_answers(payload, field, value):
    for answer in payload["answers"]:
        answer[field] = value


class AnswerCountCharacterizationTest(unittest.TestCase):
    """回答件数は刺激リストの長さによらず現行では12件ちょうど。"""

    def test_answers_fewer_than_12_are_rejected(self):
        payload, stimuli = valid_payload()
        payload["answers"] = payload["answers"][:11]
        ok, message = app.validate_submission(payload, stimuli)
        self.assertFalse(ok)
        self.assertEqual(message, "回答は12件必要です")

    def test_answers_more_than_12_are_rejected(self):
        payload, stimuli = valid_payload()
        payload["answers"] = payload["answers"] + [dict(payload["answers"][-1])]
        ok, message = app.validate_submission(payload, stimuli)
        self.assertFalse(ok)
        self.assertEqual(message, "回答は12件必要です")


class ParticipantIdLengthCharacterizationTest(unittest.TestCase):
    """参加者IDは現行では16〜64文字（文字種は問わない）で受理される。"""

    def _validate_with_id(self, participant_id):
        payload, stimuli = valid_payload(participant_id)
        return app.validate_submission(payload, stimuli)

    def test_participant_id_15_chars_is_rejected(self):
        ok, message = self._validate_with_id("a" * 15)
        self.assertFalse(ok)
        self.assertEqual(message, "participant_idが不正です")

    def test_participant_id_16_chars_is_accepted(self):
        self.assertEqual(self._validate_with_id("a" * 16), (True, ""))

    def test_participant_id_64_chars_is_accepted(self):
        self.assertEqual(self._validate_with_id("a" * 64), (True, ""))

    def test_participant_id_65_chars_is_rejected(self):
        ok, message = self._validate_with_id("a" * 65)
        self.assertFalse(ok)
        self.assertEqual(message, "participant_idが不正です")


class RatingRangeCharacterizationTest(unittest.TestCase):
    """3つの評価（単調さ・自然さ・読みやすさ）は現行では1〜7（事前登録の7件法）。"""

    FIELDS = ("monotony", "naturalness", "readability")

    def test_rating_boundaries_1_and_7_are_accepted(self):
        for field in self.FIELDS:
            for value in (1, 7):
                with self.subTest(field=field, value=value):
                    payload, stimuli = valid_payload()
                    set_all_answers(payload, field, value)
                    self.assertEqual(
                        app.validate_submission(payload, stimuli), (True, "")
                    )

    def test_ratings_0_and_8_are_rejected(self):
        for field in self.FIELDS:
            for value in (0, 8):
                with self.subTest(field=field, value=value):
                    payload, stimuli = valid_payload()
                    set_all_answers(payload, field, value)
                    ok, message = app.validate_submission(payload, stimuli)
                    self.assertFalse(ok)
                    self.assertEqual(message, f"{field}は1〜7で回答してください")


class AttentionCheckCharacterizationTest(unittest.TestCase):
    """注意確認は現行では固定値ではなく1〜7の範囲で受理される。"""

    def test_attention_check_1_and_7_are_accepted(self):
        for value in (1, 7):
            with self.subTest(value=value):
                payload, stimuli = valid_payload()
                payload["attention_check"] = value
                self.assertEqual(
                    app.validate_submission(payload, stimuli), (True, "")
                )

    def test_attention_check_0_and_8_are_rejected(self):
        for value in (0, 8):
            with self.subTest(value=value):
                payload, stimuli = valid_payload()
                payload["attention_check"] = value
                ok, message = app.validate_submission(payload, stimuli)
                self.assertFalse(ok)
                self.assertEqual(message, "注意確認項目が不正です")


class ComprehensionRangeCharacterizationTest(unittest.TestCase):
    """理解問題の回答は現行では0〜2（選択肢インデックス）で受理される。"""

    def test_comprehension_2_is_accepted(self):
        payload, stimuli = valid_payload()
        set_all_answers(payload, "comprehension", 2)
        self.assertEqual(app.validate_submission(payload, stimuli), (True, ""))

    def test_comprehension_minus1_and_3_are_rejected(self):
        for value in (-1, 3):
            with self.subTest(value=value):
                payload, stimuli = valid_payload()
                set_all_answers(payload, "comprehension", value)
                ok, message = app.validate_submission(payload, stimuli)
                self.assertFalse(ok)
                self.assertEqual(message, "理解問題の回答が不正です")


class ElapsedRangeCharacterizationTest(unittest.TestCase):
    """1項目の回答時間は現行では1000〜1800000ミリ秒で受理される。"""

    def test_elapsed_boundaries_are_accepted(self):
        for value in (1000, 1800000):
            with self.subTest(value=value):
                payload, stimuli = valid_payload()
                set_all_answers(payload, "elapsed_ms", value)
                self.assertEqual(
                    app.validate_submission(payload, stimuli), (True, "")
                )

    def test_elapsed_outside_boundaries_is_rejected(self):
        for value in (999, 1800001):
            with self.subTest(value=value):
                payload, stimuli = valid_payload()
                set_all_answers(payload, "elapsed_ms", value)
                ok, message = app.validate_submission(payload, stimuli)
                self.assertFalse(ok)
                self.assertEqual(message, "回答時間が不正です")


class ItemIdSetCharacterizationTest(unittest.TestCase):
    """回答の刺激ID集合は現行では刺激12項目と一致しなければ受理されない。"""

    def test_duplicated_item_id_is_rejected(self):
        payload, stimuli = valid_payload()
        payload["answers"][-1]["item_id"] = payload["answers"][0]["item_id"]
        ok, message = app.validate_submission(payload, stimuli)
        self.assertFalse(ok)
        self.assertEqual(message, "刺激IDが重複または不正です")

    def test_unknown_item_id_is_rejected(self):
        payload, stimuli = valid_payload()
        payload["answers"][0]["item_id"] = "item-99"
        ok, message = app.validate_submission(payload, stimuli)
        self.assertFalse(ok)
        self.assertEqual(message, "刺激IDが重複または不正です")


if __name__ == "__main__":
    unittest.main()
