# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""lint.py — AI臭い日本語文章を決定的に検出する lint スクリプト。

設計思想（HANDOFF.md 参照）:
    「AI は自分自身の AI 臭さを認識できない」→ 機械的・決定的に検出して
    人間（または AI 自身の別セッション）に突きつけ、直すかどうかの判断は
    委ねる。これは CI ゲートではなく lint であるため、検出件数に関わらず
    exit code は常に 0 にする。
    ただし、これは「文章の中身」に関する判断を保留するという意味であり、
    ファイルが読めない・存在しない・ディレクトリが指定された等の
    「そもそも lint を実行できない」入力エラーとは区別する。
    入力エラーの場合はエラーメッセージを表示し、exit code 1 で終了する。

使い方:
    uv run scripts/lint.py <file.md> [--json]

実装メモ:
    - sudachipy の Tokenizer 生成（辞書ロード）は重いので、プロセス内で
      一度だけ生成し使い回す（lazy シングルトン、textcore.get_tokenizer）。
    - 文分割は「。」「！」「？」「\\n」を区切りとする簡易実装（textcore.split_sentences_with_lines）。
      厳密な文境界解析ではないが、決定的検出のプロトタイプとしてはこれで十分。
    - sudachi トークナイザ初期化・Markdown構造マスク・文分割・ファイル読み込みなどの
      共有基盤は textcore.py にある（scripts/outline.py, scripts/terms.py と共用）。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import statistics
import sys
from pathlib import Path

from textcore import (
    Finding,
    SENTENCE_SPLIT_RE,
    _CODE_FENCE_RE,
    _HEADING_RE,
    _blank_inline_code_spans,
    _LIST_ITEM_RE,
    get_tokenizer,
    iter_lines_with_no,
    iter_paragraphs_with_lines,
    mask_html_comments,
    mask_markdown_structure,
    read_source_file,
    split_sentences_with_lines,
)

# ---------------------------------------------------------------------------
# モジュール分割（C-002）: 辞書・閾値・ジャンルプロファイルは lint_vocab.py、
# 検出器群は lint_detectors.py、読解負荷レーンの検出器は lint_reading.py に
# 移した（いずれもエントリポイントではないため PEP 723 メタデータは
# 本ファイル側にのみ置く）。従来の import 面（from lint import run_lint、
# lint.detect_*、lint.HINTS 等）を変えないため、移した名前はすべて
# ここで再exportする。calibrate.py や corpus/experiments/ のスクリプトは
# lint 経由の属性アクセス（mod.detect_*、mod.*_THRESHOLD 等）に依存する。
# ---------------------------------------------------------------------------
from lint_detectors import (
    _IDENTIFIER_RE,
    _KANJI_RE,
    _KATAKANA_RE,
    _LATIN_TECH_TOKEN_RE,
    _SMALL_KANA_MERGE,
    _URL_IN_TEXT_RE,
    ABSTRACT_PRONOUN_PHRASES,
    ABSTRACT_PRONOUNS,
    BECAUSE_HEAD,
    BOILERPLATE_HEADING_WORDS,
    BOLD_DENSITY_PER_1000_THRESHOLD,
    BOLD_LABEL_RE,
    BOLD_SPAN_RE,
    BULLET_LINE_MIN_LINES,
    BULLET_LINE_RATIO_THRESHOLD,
    CLEFT_BECAUSE_HEAD,
    CONTENT_WORD_POS,
    EMOJI_SYMBOL_PER_1000_THRESHOLD,
    EMOJI_SYMBOL_RE,
    INANIMATE_SUBJECT_PATTERNS,
    NEGATION_END_RE,
    NEGATION_REPETITION_THRESHOLD,
    NOUN_ENDING_POS,
    NUMBERED_PHASE_MIN_COUNT,
    NUMBERED_PHASE_RE,
    TRAILING_SYMBOL_POS,
    TRANSITIVE_SMELL_VERBS,
    TokenizedSentence,
    _is_proper_noun_or_tech_term,
    _phrase_positions,
    _raw_or_masked,
    _strip_leading_symbols,
    _strip_trailing_symbols,
    attach_hints,
    compute_mtld,
    detect_antithesis_repetition,
    detect_english_syntax_smell,
    detect_forbidden_phrases,
    detect_inanimate_subject_morph,
    detect_lexical_diversity,
    detect_low_sentence_length_variance,
    detect_low_specificity,
    detect_negation_repetition,
    detect_ngram_repetition,
    detect_nominal_ending_and_paragraph_conjunctions,
    detect_rhythm_statistics,
    detect_structural_ai_habits,
    detect_translationese,
    detect_translationese_morph,
    format_related_lines,
    mora_length,
    tokenize_sentences,
)
from lint_reading import (
    _CLOSE_PARENS,
    _CONDITIONAL_NEGATION_RE,
    _JA_CHAR_RE,
    _KANJI_RUN_RE,
    _NEGATION_NORMALIZED,
    _NEGATION_POS,
    _OBLIGATION_SPANS,
    _OPEN_PARENS,
    _PAREN_QUOTE_RE,
    _PAREN_RE,
    _WHITESPACE_RUN_RE,
    READING_LOAD_BURIED_LIST_3ITEM_MIN_CHARS,
    READING_LOAD_BURIED_LIST_MIN_CHARS,
    READING_LOAD_BURIED_LIST_MIN_ITEMS,
    READING_LOAD_CATEGORIES,
    READING_LOAD_KANJI_RUN_MAX,
    READING_LOAD_NEGATION_MAX_GAP,
    READING_LOAD_NO_CHAIN_MIN,
    READING_LOAD_SENTENCE_MAX_CHARS,
    _has_punctuation_between,
    _is_conditional_negation,
    _is_negation,
    _is_obligation_form,
    _longest_noun_phrase_run,
    _reading_length,
    _segment_ends_with_noun,
    _span_contains_proper_noun,
    detect_reading_load,
    detect_sentence_in_paren,
)
from lint_vocab import (
    ABSTRACT_NOUN_WORDS,
    ANTITHESIS_PATTERNS,
    ANTITHESIS_RATE_CRITICAL_ABOVE,
    ANTITHESIS_RATE_INFO_BELOW,
    ANTITHESIS_REPETITION_THRESHOLD,
    AUTOCORR_MIN_XS,
    AUTOCORR_THRESHOLD,
    BURSTINESS_MIN_TOKENIZED,
    BURSTINESS_THRESHOLD,
    EXAMPLE_MARKER_WORDS,
    EXPERIMENTAL_CATEGORIES,
    FORBIDDEN_PHRASES,
    FORBIDDEN_PHRASES_WEAK_SIGNAL,
    GENRE_PROFILES,
    HINTS,
    LEXDIV_MIN_DOC_CHARS,
    LEXDIV_MIN_TOKENS,
    LOW_SPECIFICITY_ABSTRACT_NOUN_WEIGHT,
    LOW_SPECIFICITY_EXAMPLE_MARKER_BONUS,
    LOW_SPECIFICITY_MIN_CHARS,
    LOW_SPECIFICITY_MIN_CONTENT_WORDS,
    LOW_SPECIFICITY_NUMERIC_WEIGHT,
    LOW_SPECIFICITY_PROPER_NOUN_WEIGHT,
    LOW_SPECIFICITY_SCORE_THRESHOLD,
    MTLD_THRESHOLD,
    NGRAM_LEAD_REPEAT_THRESHOLD,
    NGRAM_TEMPLATE_MIN_COUNT,
    NGRAM_TEMPLATE_RATIO_THRESHOLD,
    NOMINAL_ENDING_MIN_CHARS,
    NOMINAL_ENDING_MIN_SENTENCES,
    NOMINAL_ENDING_RATIO_THRESHOLD,
    NUMERIC_QUANTITY_RE,
    PARAGRAPH_CONJ_MIN_PARAGRAPHS,
    PARAGRAPH_CONJ_RATIO_THRESHOLD,
    PARAGRAPH_CONJUNCTIONS,
    SENTENCE_VARIANCE_CV_THRESHOLD,
    SENTENCE_VARIANCE_MIN_SENTENCES,
    TRANSLATIONESE_PATTERNS,
    TTR_THRESHOLD,
    UNIFORM_PARAGRAPH_CV_THRESHOLD,
    UNIFORM_PARAGRAPH_MIN_PARAGRAPHS,
)


# ---------------------------------------------------------------------------
# --baseline 差分モード
#
# スキルの利用フローは「lint → 台帳に直した/残すを仕分け → 修正 → 再lint →
# 新規findingが出なくなるまで繰り返す」という収束駆動ループになっている。
# ループのたびに全件を目視で見比べるのは負担が大きいので、前回の --json 出力
# （baseline）と今回の結果を比較し、resolved（解消）/ new（新規）/
# persisting（継続）に分類する。
#
# 同一性キーの設計判断:
#   行番号は修正のたびに増減してズレるため、キーに含めない
#   （同じ指摘でも直した箇所より後ろの行が繰り上がるだけで「新規」扱いに
#   なってしまう）。excerpt は形態素境界のわずかな変化や、直した箇所の
#   前後の空白差などで完全一致しなくなることがあるため、正規化
#   （空白除去）した上で先頭 N 文字の前方一致とする。カテゴリ名は
#   検出器の種類そのものなので、そのまま等価比較に使う。
#   これは完全に正確な同一性判定ではないが、実装が単純で、
#   「同じ場所・同じ理由の指摘かどうか」の近似としては十分安定する。
# ---------------------------------------------------------------------------
_BASELINE_KEY_EXCERPT_PREFIX_LEN = 20


# 文書全体の統計量（burstiness・変動係数・TTR/MTLD 等）を excerpt に直接埋め込んでいる
# カテゴリ。これらは1文書につき高々1件しか出ない「集計そのもの」の finding であり、
# excerpt が「burstiness=-0.623 (...)」のように計算結果の数値そのものなので、
# 無関係な編集で文書の統計量がわずかに変化しただけで excerpt 文字列が変わり、
# 同一性キーに含めると「解消」＋「新規」の偽ペアが発生してしまう。
# このグループはカテゴリ名だけをキーにする（1文書1件が前提なので情報の欠落もない）。
#
# 一方、nominal_ending・repeated_sentence_lead・repeated_syntax_template・
# paragraph_lead_conjunction・antithesis_repetition は「文書全体集計型」ではあるが、
# excerpt 自体は実際にマッチした原文（体言止めの文末・反復した文頭など）であり、
# 数値は detail 側にしか出てこない（同一性キーは detail を見ていない）。
# これらは1文書内に複数の異なる該当箇所を持つのが普通なので、カテゴリ名だけに
# 潰さず、従来どおり excerpt の前方一致キーを使う方が精度が高い。
_CATEGORY_ONLY_KEY_CATEGORIES = {
    "low_burstiness",
    "high_length_autocorrelation",
    "low_sentence_variance",
    "uniform_paragraph_structure",
    "low_lexical_diversity_ttr",
    "low_lexical_diversity_mtld",
}


def _normalize_excerpt_for_key(excerpt: str) -> str:
    """excerpt を同一性キー用に正規化する（空白類を除去）。"""
    return re.sub(r"\s+", "", excerpt or "")


def _finding_identity_key(category: str, excerpt: str) -> tuple[str, str]:
    """(category, 正規化excerptの前方一致キー) を返す。行番号は含めない。
    _CATEGORY_ONLY_KEY_CATEGORIES に該当するカテゴリは excerpt を無視し、
    カテゴリ名のみをキーにする（理由は上のコメント参照）。
    """
    if category in _CATEGORY_ONLY_KEY_CATEGORIES:
        return (category, "")
    normalized = _normalize_excerpt_for_key(excerpt)
    return (category, normalized[:_BASELINE_KEY_EXCERPT_PREFIX_LEN])


def validate_baseline_data(baseline_data) -> tuple[dict | None, list[str]]:
    """--baseline で読み込んだ JSON の形を検証する。

    スキーマが想定外（トップレベルが dict でない、"findings" が配列でない、
    配列内の要素が dict でない等）でも compute_baseline_diff() をクラッシュ
    させたくないため、ここで軽量な検証を行い、
    - 完全に想定外の形なら (None, [警告メッセージ]) を返し、呼び出し側は
      baseline 比較そのものを諦めて通常の lint 実行にフォールバックする
      （graceful degradation。lint はそもそも CI ゲートではないので、
      baseline ファイルの不備で実行全体を落とすべきではない）
    - "findings" 配列の一部の要素だけが dict でない場合は、その要素だけを
      読み飛ばして残りで比較を続行する
    """
    warnings: list[str] = []
    if not isinstance(baseline_data, dict):
        warnings.append(
            "--baseline の内容が JSON オブジェクトではありません。baseline との比較はせずに通常のlintを実行します。"
        )
        return None, warnings

    findings_raw = baseline_data.get("findings")
    if not isinstance(findings_raw, list):
        warnings.append(
            "--baseline に 'findings' 配列が見つかりません。baseline との比較はせずに通常のlintを実行します。"
        )
        return None, warnings

    valid_findings = []
    skipped = 0
    for item in findings_raw:
        # dict であることに加え、_finding_identity_key() が参照するフィールドの型も
        # ここで検証する（category が非文字列だと set 判定、excerpt が非文字列だと
        # re.sub がクラッシュするため。JSON としては valid でも型が壊れた baseline
        # は要素単位で読み飛ばす）。
        if (
            isinstance(item, dict)
            and isinstance(item.get("category"), str)
            and isinstance(item.get("excerpt"), str)
        ):
            valid_findings.append(item)
        else:
            skipped += 1
    if skipped:
        warnings.append(
            f"--baseline の findings 配列内に不正な要素が{skipped}件あったため読み飛ばしました。"
        )
    return {"findings": valid_findings}, warnings


def compute_baseline_diff(
    findings: list[Finding], baseline_data: dict
) -> tuple[list[dict], dict[str, int]]:
    """今回の findings と、前回の --json 出力（baseline_data、事前に
    validate_baseline_data() を通した想定）を比較する。

    各 Finding の `.status` を "new"（今回のみ）または "persisting"
    （両方に存在）に破壊的に設定する。baseline にしかない finding は
    「resolved（解消）」として別途リストで返す（対応する現在の Finding
    オブジェクトが存在しないため、baseline の生 dict のまま返す）。

    多重集合としてマッチングする（同じキーの finding が複数あっても、
    件数分だけ 1 対 1 で対応付ける）ため、同じ指摘が複数箇所にある
    ケースでも resolved/persisting の件数がズレない。
    """
    from collections import defaultdict

    baseline_findings = baseline_data.get("findings", [])
    baseline_by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for bf in baseline_findings:
        key = _finding_identity_key(bf.get("category", ""), bf.get("excerpt", ""))
        baseline_by_key[key].append(bf)

    for f in findings:
        key = _finding_identity_key(f.category, f.excerpt)
        bucket = baseline_by_key.get(key)
        if bucket:
            bucket.pop(0)
            f.status = "persisting"
        else:
            f.status = "new"

    resolved = [bf for bucket in baseline_by_key.values() for bf in bucket]

    summary = {
        "resolved": len(resolved),
        "new": sum(1 for f in findings if f.status == "new"),
        "persisting": sum(1 for f in findings if f.status == "persisting"),
    }
    return resolved, summary


def run_reading_load(raw_text: str, genre: str | None = None) -> tuple[list[Finding], dict]:
    """読みにくそうな箇所の検査だけを実行する。

    run_lint() とは意図的に独立した関数にしてある。既存の findings / stats /
    baseline 比較に読解負荷の finding が混入する経路を、構造として作らないため。
    マスク・文分割・形態素解析の手順は run_lint() と同じで、Tokenizer は
    textcore.get_tokenizer() のシングルトンを共有する。
    """
    profile = GENRE_PROFILES.get(genre, {})
    text = mask_markdown_structure(raw_text)
    lines = iter_lines_with_no(text)
    raw_lines_by_no = dict(iter_lines_with_no(raw_text))
    sentences = split_sentences_with_lines(lines, raw_lines_by_no)
    tokenized = tokenize_sentences(sentences)

    findings = detect_reading_load(
        tokenized,
        sentence_max_chars=profile.get(
            "reading_load_sentence_max_chars", READING_LOAD_SENTENCE_MAX_CHARS
        ),
    )
    # 「〜ことができる」は生成AIらしさではなく冗長さの指摘として、このレーンで出す。
    findings += detect_translationese_morph(tokenized)
    findings += detect_sentence_in_paren(raw_text)
    findings.sort(key=lambda f: f.line)
    attach_hints(findings)
    stats = {
        "total": len(findings),
        "sentences": len(tokenized),
        "genre": genre,
        "by_category": {},
    }
    for f in findings:
        stats["by_category"][f.category] = stats["by_category"].get(f.category, 0) + 1
    return findings, stats




# ---------------------------------------------------------------------------
def run_lint(
    raw_text: str, genre: str | None = None, experimental: bool = False
) -> tuple[list[Finding], dict]:
    """genre: "essay" | "tech" | "business" | None。指定するとジャンル別に校正した
    閾値プロファイル（GENRE_PROFILES）を適用する。指定しない場合（デフォルト）は
    共通の保守的な閾値（モジュール定数のデフォルト値）を使う。
    experimental: True にすると EXPERIMENTAL_CATEGORIES（まだ定量校正前、または
    無反応と判定された検出器）の finding も出力する。デフォルトは False で、
    それらは stats/findings から除外される。
    """
    profile = GENRE_PROFILES.get(genre, {})

    # --- 構造層検出器は Markdown マスクより前のテキストを解析するが、HTML コメント内の
    # 太字・番号付きフェーズ・絵文字を誤検知しないよう、HTML コメントのみを同じ長さの
    # 空白に置換したテキストを渡す（行番号・オフセットは raw_text と一致するため、
    # 検出器内で raw_text から excerpt を切り出す既存ロジックはそのまま使える）。
    structural_findings, structural_stats = detect_structural_ai_habits(mask_html_comments(raw_text))

    # Markdown の構造行（見出し/リスト/コードブロック/引用/表）とインラインコードスパンは
    # 文章として扱わず、行番号を保ったままマスクしてから解析用テキストとして使う。
    # ただし excerpt（レポート表示）は必ず raw_text（原文）から同じオフセットで切り出す。
    # マスクは「解析専用」であり、表示用ではないことに注意。
    text = mask_markdown_structure(raw_text)
    lines = iter_lines_with_no(text)
    raw_lines_by_no = dict(iter_lines_with_no(raw_text))
    sentences = split_sentences_with_lines(lines, raw_lines_by_no)
    # sudachipy の形態素解析結果は複数の検出器で使い回す（トークナイズは1回だけ）。
    tokenized = tokenize_sentences(sentences)

    findings: list[Finding] = []
    findings += structural_findings
    # --- 表層（正規表現）ベースの検出器 ---
    findings += detect_forbidden_phrases(lines, raw_lines_by_no)
    findings += detect_translationese(lines, raw_lines_by_no)
    findings += detect_antithesis_repetition(
        lines,
        raw_lines_by_no,
        rate_critical_above=profile.get("antithesis_rate_critical_above", ANTITHESIS_RATE_CRITICAL_ABOVE),
    )
    findings += detect_negation_repetition(lines, raw_lines_by_no)
    findings += detect_low_sentence_length_variance(sentences)
    findings += detect_english_syntax_smell(lines, raw_lines_by_no)

    # --- 形態素解析ベースの検出器（拡張: 品詞列・活用形マッチ） ---
    nominal_and_conj_findings, morph_stats = detect_nominal_ending_and_paragraph_conjunctions(
        lines,
        tokenized,
        raw_lines_by_no,
        nominal_min_chars=profile.get("nominal_min_chars", NOMINAL_ENDING_MIN_CHARS),
    )
    findings += nominal_and_conj_findings
    findings += detect_inanimate_subject_morph(tokenized)
    # nested_attributive はコーパス校正で削除済み（上のコメント参照）。

    rhythm_findings, rhythm_stats = detect_rhythm_statistics(tokenized)
    findings += rhythm_findings

    ngram_findings, ngram_stats = detect_ngram_repetition(
        tokenized,
        lead_repeat_threshold=profile.get("lead_repeat_threshold", NGRAM_LEAD_REPEAT_THRESHOLD),
    )
    findings += ngram_findings

    lexdiv_findings, lexdiv_stats = detect_lexical_diversity(tokenized)
    findings += lexdiv_findings

    low_spec_findings, low_spec_stats = detect_low_specificity(lines, raw_lines_by_no)
    findings += low_spec_findings

    # EXPERIMENTAL_CATEGORIES はデフォルトでは除外する（--experimental でのみ出力）。
    if not experimental:
        findings = [f for f in findings if f.category not in EXPERIMENTAL_CATEGORIES]

    # ジャンルプロファイルによるカテゴリ単位の無効化（現状 business のみ使用）。
    # --experimental を付けて実験的カテゴリを表示させた場合でも、そのジャンルの
    # 正当な文書慣習と衝突すると判定された検出器はここで確実に除外する。
    disabled_categories = profile.get("disabled_categories", set())
    if disabled_categories:
        findings = [f for f in findings if f.category not in disabled_categories]

    findings.sort(key=lambda f: f.line)
    attach_hints(findings)

    stats = {
        "total_findings": len(findings),
        "by_category": {},
        "genre": genre,
        "experimental": experimental,
        **morph_stats,
        "rhythm": rhythm_stats,
        "ngram": ngram_stats,
        "lexical_diversity": lexdiv_stats,
        "structural": structural_stats,
        "low_specificity": low_spec_stats,
    }
    for f in findings:
        stats["by_category"][f.category] = stats["by_category"].get(f.category, 0) + 1

    return findings, stats


SEVERITY_LABEL = {"info": "情報", "warn": "警告", "critical": "重大"}


STATUS_LABEL = {"new": "新規", "persisting": "継続"}


def print_human_report(
    path: Path,
    findings: list[Finding],
    stats: dict,
    baseline_summary: dict[str, int] | None = None,
) -> None:
    print(f"=== lint: {path} ===")
    print(f"検出件数: {stats['total_findings']}")
    if stats["by_category"]:
        print("カテゴリ別内訳:")
        for cat, count in sorted(stats["by_category"].items(), key=lambda kv: -kv[1]):
            print(f"  - {cat}: {count}")

    # --baseline 指定時のみ、解消/新規/継続のサマリを追加表示する
    # （--baseline なしの場合はこのブロックごと出力されず、既存の挙動と完全に同じ）。
    if baseline_summary is not None:
        print(
            f"ベースライン比較: 解消: {baseline_summary['resolved']}件 / "
            f"新規: {baseline_summary['new']}件 / "
            f"継続: {baseline_summary['persisting']}件"
        )
    print()

    if not findings:
        print("検出なし。")
        return

    for f in findings:
        label = SEVERITY_LABEL.get(f.severity, f.severity)
        # baseline比較時は各行に新規/継続タグを付ける（比較しない場合は付けない＝従来どおり）
        status_tag = f"[{STATUS_LABEL.get(f.status, f.status)}] " if f.status else ""
        print(f"{status_tag}[{label}] L{f.line} ({f.category})")
        print(f"    該当箇所: {f.excerpt}")
        if f.detail:
            # 「対応箇所: L12, L34, ...」（related_lines）は detail 文字列に既に
            # 含めているため、人間可読レポートでは detail をそのまま表示すれば十分。
            print(f"    詳細    : {f.detail}")
        if f.hint:
            print(f"    直し方  : {f.hint}")
        print()


def print_reading_load_report(findings: list[Finding], stats: dict) -> None:
    """読みにくそうな箇所の検査を、AI臭さの検出結果とは視覚的にも分けて出力する。"""
    print("=== 読解負荷（推敲で見る箇所を示すだけ。自然度スコアには含まない） ===")
    print(f"指摘件数: {stats.get('total', len(findings))}（本文 {stats.get('sentences', 0)} 文）")
    if stats.get("by_category"):
        print("カテゴリ別内訳:")
        for cat, count in sorted(stats["by_category"].items(), key=lambda kv: -kv[1]):
            print(f"  - {cat}: {count}")
    print()

    if not findings:
        print("指摘なし。")
        return

    for f in findings:
        print(f"[見る箇所] L{f.line} ({f.category})")
        print(f"    該当箇所: {f.excerpt}")
        if f.detail:
            print(f"    詳細    : {f.detail}")
        if f.hint:
            print(f"    直し方  : {f.hint}")
        print()

    print("※ これらは「直すべき欠陥」ではなく「見るべき箇所」。読んで引っかからない文はいじらない。")
    print("※ 直し方は SKILL.md §5「読みやすさの点検」に従う。")


def print_paragraph_sheet(text: str) -> None:
    """段落ごとの確認(SKILL.md §3)の一覧を出す。判断はしない。

    文書を通して読むだけだと、モデルは「もう読みやすい」と判断して段落ごとの確認を
    飛ばす。別のコマンドにすると実行を省かれるので、毎回実行される lint の出力に含める。
    """
    from paragraphs import split_units

    units = split_units(text)
    print(f"=== 段落ごとの確認(全 {len(units)} 段落。既存の文書を直すときは必須。SKILL.md §3) ===")
    print("1段落ずつ、動詞と名詞をすべて見て、§3「読み手が何のことか分からない言い回し」の型に当たるものを")
    print("「番号: 言い回し → 指しているもの(元の文書やコードにある事実・名前)」の形で書き出す。")
    print("当たらない段落は「番号: なし」と書く。最後の段落まで書き出してから直す。途中で省かない。")
    print()
    for u in units:
        body = u["text"].replace("\n", " / ")
        print(f"[{u['no']}] L{u['line']} {u['kind']}: {body}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI臭い日本語文章を決定的に検出する lint スクリプト（CI ゲートではない）。"
    )
    parser.add_argument("file", type=Path, help="lint 対象の Markdown/テキストファイル")
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        metavar="PREV.json",
        help=(
            "前回の --json 出力ファイルと比較し、resolved（解消）/ new（新規）/ "
            "persisting（継続）を判定する（直して lint をかけ直すたびに、指摘が減ったかを見るのに使う。"
            "指定しない場合の挙動は完全に不変）"
        ),
    )
    parser.add_argument(
        "--genre",
        choices=sorted(GENRE_PROFILES),
        default=None,
        help=(
            "文書のジャンルに応じてコーパス校正済みの閾値プロファイルを適用する"
            "（essay/tech/business）。未指定時は共通の保守的閾値を使う"
        ),
    )
    parser.add_argument(
        "--experimental",
        action="store_true",
        help=(
            "まだコーパスで定量校正されていない、またはコーパスでほとんど何も検出しなかった検出器"
            "（EXPERIMENTAL_CATEGORIES）も出力する。デフォルトでは除外される"
        ),
    )
    parser.add_argument(
        "--reading-load",
        action="store_true",
        help=(
            "読みにくそうな箇所（一文長・埋もれた列挙・連続漢字・二重否定・「の」連鎖）も"
            "出力する。AI臭さの検出とは別の検査で、推敲で見る箇所を示すだけ。"
            "自然度スコアにも --baseline 比較にも含まれない"
        ),
    )
    args = parser.parse_args()

    # 「文章の中身に関する判断」と「そもそも実行できない入力エラー」は区別する。
    # 前者（検出結果）は exit 0（lintでありCIゲートではない）、
    # 後者（ファイル不在/ディレクトリ指定/読み取り不可/非UTF-8等）は exit 1。
    text, err = read_source_file(args.file)
    if err is not None:
        print(err, file=sys.stderr)
        return 1

    baseline_data = None
    if args.baseline is not None:
        if not args.baseline.exists():
            print(f"エラー: --baseline ファイルが見つかりません: {args.baseline}", file=sys.stderr)
            return 1
        try:
            loaded_baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"エラー: --baseline ファイルを読み込めません: {args.baseline} ({exc})", file=sys.stderr)
            return 1

        # JSON としては読めても、スキーマが想定外（トップレベルが配列、findings が
        # 欠けている、findings 内の要素が dict でない等）だと compute_baseline_diff()
        # がクラッシュしうる。lint は CI ゲートではなく、baseline はあくまで補助
        # 情報なので、想定外の形式のときは実行全体を落とさず、baseline比較を諦めて
        # 通常の lint 実行にフォールバックする（警告は出す）。
        baseline_data, baseline_warnings = validate_baseline_data(loaded_baseline)
        for w in baseline_warnings:
            print(f"警告: {w}", file=sys.stderr)

    findings, stats = run_lint(text, genre=args.genre, experimental=args.experimental)

    # 読みにくそうな箇所の検査は完全に別扱いにする。findings にも stats にも混ぜず、
    # --baseline 比較（compute_baseline_diff）にも渡さない。
    reading_load_findings: list[Finding] | None = None
    reading_load_stats: dict | None = None
    if args.reading_load:
        reading_load_findings, reading_load_stats = run_reading_load(text, genre=args.genre)

    resolved: list[dict] = []
    baseline_summary: dict[str, int] | None = None
    if baseline_data is not None:
        resolved, baseline_summary = compute_baseline_diff(findings, baseline_data)

    if args.json:
        output = {
            "file": str(args.file),
            "stats": stats,
            "findings": [f.to_dict() for f in findings],
        }
        # --baseline を指定したときだけ baseline セクションを追加する
        # （指定しない場合の JSON 構造は従来と完全に同じ）。
        if baseline_summary is not None:
            output["baseline"] = {
                "file": str(args.baseline),
                "summary": baseline_summary,
                "resolved": resolved,
            }
        # --reading-load を指定したときだけ独立したセクションを追加する
        # （指定しない場合の JSON 構造は従来と完全に同じ）。
        if reading_load_findings is not None:
            output["reading_load"] = {
                "stats": reading_load_stats,
                "findings": [f.to_dict() for f in reading_load_findings],
            }
        from paragraphs import split_units

        output["paragraphs"] = split_units(text)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_human_report(args.file, findings, stats, baseline_summary)
        if reading_load_findings is not None:
            print_reading_load_report(reading_load_findings, reading_load_stats or {})
        print_paragraph_sheet(text)

    # lint であって CI ゲートではない。文章の検出結果は件数に関わらず常に exit 0 とし、
    # 修正するかどうかの判断は人間（または後続の AI 自己点検フロー）に委ねる。
    return 0


if __name__ == "__main__":
    sys.exit(main())
