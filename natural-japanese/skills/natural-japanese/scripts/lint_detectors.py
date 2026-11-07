"""lint_detectors.py — lint の検出器群（表層・形態素・統計・構造）。

エントリポイントではない（単体実行を想定しない）ため PEP 723 インライン
メタデータは持たない。依存（sudachipy 等）はエントリスクリプト
（lint.py）側で宣言する。辞書・閾値は lint_vocab.py、共有基盤は
textcore.py にある。

C-002 の分割で lint.py から検出関数をそのまま移したもの（ロジック変更
なし）。lint.py は従来の import 面を保つため、ここの名前をすべて
再exportする。
"""

from __future__ import annotations

import dataclasses
import re
import statistics

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
    FORBIDDEN_PHRASES,
    FORBIDDEN_PHRASES_WEAK_SIGNAL,
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
from textcore import (
    _HEADING_RE,
    _LIST_ITEM_RE,
    SENTENCE_SPLIT_RE,
    Finding,
    get_tokenizer,
    iter_lines_with_no,
    iter_paragraphs_with_lines,
    split_sentences_with_lines,
)


def format_related_lines(related_lines: list[int]) -> str:
    """related_lines を人間可読の「対応箇所: L12, L34, ...」形式に整形する（重複除去・昇順ソート）。"""
    uniq_sorted = sorted(set(related_lines))
    return "対応箇所: " + ", ".join(f"L{n}" for n in uniq_sorted)


# ---------------------------------------------------------------------------
# 各検出器
# ---------------------------------------------------------------------------
def _raw_or_masked(raw_lines_by_no: dict[int, str] | None, no: int, fallback: str) -> str:
    """行番号に対応する原文行を返す（無ければマスク済み行にフォールバック）。"""
    if raw_lines_by_no is None:
        return fallback
    return raw_lines_by_no.get(no, fallback)


_KATAKANA_RE = re.compile(r"[ァ-ヶー]")


_KANJI_RE = re.compile(r"[一-龠々]")


def _phrase_positions(line: str, phrase: str) -> list[int]:
    """phrase が語として現れる位置をすべて返す。カタカナで始まる語の直前がカタカナ、
    漢字で始まる語の直前が漢字のときは、別の語の一部(「エンドポイントは」の「ポイントは」、
    「包括的経済連携協定」の前に漢字が続く「日英包括的」など)とみなして数えない。"""
    out = []
    head = phrase[0]
    for m in re.finditer(re.escape(phrase), line):
        prev = line[m.start() - 1] if m.start() > 0 else ""
        if prev and ((_KATAKANA_RE.match(head) and _KATAKANA_RE.match(prev))
                     or (_KANJI_RE.match(head) and _KANJI_RE.match(prev))):
            continue
        out.append(m.start())
    return out


def detect_forbidden_phrases(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    """マスク済み行（コードスパン等を空白化したテキスト）でパターンマッチし、
    excerpt は同じオフセットで原文行から切り出す（マスクは解析専用、表示は原文）。
    """
    findings = []
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for phrase in FORBIDDEN_PHRASES:
            for idx in _phrase_positions(line, phrase):
                start = max(0, idx - 10)
                end = idx + len(phrase) + 10
                excerpt = raw_line[start:end] if len(raw_line) >= end else line[start:end]
                is_weak_signal = phrase in FORBIDDEN_PHRASES_WEAK_SIGNAL
                severity = "info" if is_weak_signal else "warn"
                detail = f"AI の書いた文章によく出る言い回し「{phrase}」"
                if is_weak_signal:
                    detail += "（人間の文書にもよく出る語なので、弱い疑い）"
                findings.append(
                    Finding(
                        line=no,
                        category="forbidden_phrase",
                        excerpt=excerpt.strip(),
                        severity=severity,
                        detail=detail,
                    )
                )
    return findings


def detect_translationese(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    findings = []
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for pat in TRANSLATIONESE_PATTERNS:
            for m in re.finditer(pat, line):
                start = max(0, m.start() - 10)
                end = m.end() + 10
                excerpt = raw_line[start:end] if len(raw_line) >= end else line[start:end]
                findings.append(
                    Finding(
                        line=no,
                        category="translationese",
                        excerpt=excerpt.strip(),
                        severity="info",
                        detail="英語の構文をなぞった翻訳調の言い回しの疑い",
                    )
                )
    return findings


def detect_antithesis_repetition(
    lines: list[tuple[int, str]],
    raw_lines_by_no: dict[int, str] | None = None,
    threshold: int = ANTITHESIS_REPETITION_THRESHOLD,
    rate_info_below: float = ANTITHESIS_RATE_INFO_BELOW,
    rate_critical_above: float = ANTITHESIS_RATE_CRITICAL_ABOVE,
) -> list[Finding]:
    """「〜ではなく、〜」「〜だけでなく〜も」を文書全体で数え、threshold回（デフォルト3回）
    以上なら反復として検出する。

    2026-07 コーパス校正2（corpus/reports/antithesis-recalibration.md、モジュール定数
    ANTITHESIS_RATE_INFO_BELOW / ANTITHESIS_RATE_CRITICAL_ABOVE のコメントも参照）:
    出現ごとに severity=critical を付けていた旧仕様は、長文書での薄い頻度でも
    critical が連打されノイズ化する一方、人間の意図的な修辞技法にも無差別に発火して
    いた。「検出数/総文数」の比率で severity を3段階化する: 比率が低ければ info
    （人間の技法との区別がつかない参考情報）、高ければ critical（実測で真陽性が
    多い高頻度パターン）、その中間は warn。

    どの文同士が反復としてカウントされたか追えるよう、全ヒット行番号を
    related_lines / detail の両方に含める。excerpt は原文から切り出す。
    """
    hits: list[tuple[int, str, str]] = []  # (line_no, matched_excerpt(raw), pattern_name)
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for pat in ANTITHESIS_PATTERNS:
            for m in re.finditer(pat, line):
                excerpt = raw_line[m.start() : m.end()] if len(raw_line) >= m.end() else m.group(0)
                hits.append((no, excerpt, pat.pattern))

    findings = []
    if len(hits) >= threshold:
        # 文書全体の総文数に対する検出数の比率で severity を決める（絶対回数の閾値
        # 判定とは別に、比率が文書の長さに関わらず一貫した「密度」の指標になる）。
        total_sentences = len(split_sentences_with_lines(lines, raw_lines_by_no))
        ratio = len(hits) / total_sentences if total_sentences else 0.0
        if ratio < rate_info_below:
            severity = "info"
        elif ratio >= rate_critical_above:
            severity = "critical"
        else:
            severity = "warn"

        all_lines = [no for no, _, _ in hits]
        related = format_related_lines(all_lines)
        for no, text, patname in hits:
            findings.append(
                Finding(
                    line=no,
                    category="antithesis_repetition",
                    excerpt=text.strip(),
                    severity=severity,
                    detail=(
                        f"否定→肯定対比パターンが文書内で{len(hits)}回検出（閾値{threshold}回以上、"
                        f"総文数に対する比率={ratio:.1%}）。{related}"
                    ),
                    related_lines=all_lines,
                )
            )
    return findings


# 文末を打ち消しで終える文(「〜ではない。」「〜わけではない。」)の多用。GPT 系の文書に特に多い。
# 2026-10 の測定(手元の評価用データ):文書内に4回以上あったのは、生成AI以前の人間の文書
# 400本で0本、Claude・Gemini の文書65本で0本、GPT 系の文書35本で22本。「〜ではないでしょうか」
# 「〜ではないか」のような問いかけ・推量は数えない(人間の文書に多く、打ち消しではないため)。
NEGATION_END_RE = re.compile(r"(?:ではない|ではありません|じゃない|わけではない|わけではありません|わけじゃない)(?:のです|んです|のだ)?$")


NEGATION_REPETITION_THRESHOLD = 4


def detect_negation_repetition(
    lines: list[tuple[int, str]],
    raw_lines_by_no: dict[int, str] | None = None,
    threshold: int = NEGATION_REPETITION_THRESHOLD,
) -> list[Finding]:
    """文末を打ち消しで終える文を文書全体で数え、threshold 回以上なら多用として検出する。"""
    hits = []
    for no, sent, raw in split_sentences_with_lines(lines, raw_lines_by_no):
        body = sent.strip().rstrip("。．")
        if NEGATION_END_RE.search(body):
            hits.append((no, (raw or sent).strip()))
    findings = []
    if len(hits) >= threshold:
        all_lines = [no for no, _ in hits]
        related = format_related_lines(all_lines)
        for no, text in hits:
            findings.append(Finding(
                line=no, category="negation_repetition", excerpt=text[:60], severity="warn",
                detail=f"文末を打ち消しで終える文が文書内で{len(hits)}回(閾値{threshold}回以上)。{related}",
                related_lines=all_lines,
            ))
    return findings


def detect_low_sentence_length_variance(
    sentences: list[tuple[int, str, str]],
    threshold: float = SENTENCE_VARIANCE_CV_THRESHOLD,
    min_sentences: int = SENTENCE_VARIANCE_MIN_SENTENCES,
) -> list[Finding]:
    """文長（文字数）の変動係数（CV = 標準偏差/平均）が閾値未満なら
    「文長が均質すぎる = リズムが単調 = AI臭い」として警告する。
    最低5文以上ないと統計的に意味がないので判定しない。
    """
    lengths = [len(s) for _, s, _ in sentences if len(s) > 0]
    if len(lengths) < min_sentences:
        return []
    mean = statistics.mean(lengths)
    if mean == 0:
        return []
    stdev = statistics.pstdev(lengths)
    cv = stdev / mean
    if cv < threshold:
        first_line = sentences[0][0] if sentences else 1
        return [
            Finding(
                line=first_line,
                category="low_sentence_variance",
                excerpt=f"文数={len(lengths)}, 平均文長={mean:.1f}字, 変動係数={cv:.3f}",
                severity="warn",
                detail=f"文の長さのばらつきが小さい（変動係数が閾値{threshold}未満）。文の長さがそろいすぎている疑い",
            )
        ]
    return []


NOUN_ENDING_POS = {"名詞"}


TRAILING_SYMBOL_POS = {"補助記号", "空白"}


# 語彙多様性計測の対象とする内容語 POS
CONTENT_WORD_POS = {"名詞", "動詞", "形容詞", "副詞"}


# 「無生物主語+他動詞」判定で「主語になっても不自然でない代名詞」として許可する語。
# sudachipy は「この事実」「そのこと」を単一形態素にせず複数形態素
# （例:「この」+「事実」）に分割するため、単一形態素の表層文字列と比較する
# 判定では到達不可能。単一形態素で成立する語だけをここに残し、
# 複数形態素にまたがる語は ABSTRACT_PRONOUN_PHRASES で別途、
# 隣接形態素を連結して比較する。
ABSTRACT_PRONOUNS = {"これ", "それ", "あれ", "それら"}


# 2形態素にまたがる指示表現（連結した表層文字列で比較する）
ABSTRACT_PRONOUN_PHRASES = {"この事実", "そのこと"}


# 述語側: 直訳調でよく使われる他動詞的な動詞（辞書は拡張前提）
TRANSITIVE_SMELL_VERBS = {
    "もたらす",
    "示す",
    "意味する",
    "証明する",
    "生み出す",
    "反映する",
    "示唆する",
    "物語る",
    "浮き彫りにする",
    "後押しする",
}


@dataclasses.dataclass
class TokenizedSentence:
    line: int
    text: str  # マスク済みテキスト（形態素解析・パターンマッチ用）
    morphemes: list  # sudachipy.MorphemeList の要素（text を解析した結果）
    raw_text: str = ""  # 原文（レポートのexcerpt表示は必ずこちらを使う）


def tokenize_sentences(sentences: list[tuple[int, str, str]]) -> list[TokenizedSentence]:
    """文ごとに一度だけ形態素解析し、以後の検出器で使い回す（辞書ロードとトークナイズの
    コストを最小化するための共有キャッシュ）。
    形態素解析はマスク済みテキスト（text）に対して行うが、レポート表示用の原文
    （raw_text、インラインコードスパンのバッククォート内文字列などを含む）も保持し、
    excerpt はそちらから切り出す。
    """
    tokenizer = get_tokenizer()
    from sudachipy import SplitMode

    result = []
    for no, sent, raw_sent in sentences:
        if not sent:
            continue
        morphemes = list(tokenizer.tokenize(sent, SplitMode.C))
        result.append(TokenizedSentence(line=no, text=sent, morphemes=morphemes, raw_text=raw_sent or sent))
    return result


def _strip_leading_symbols(morphemes: list) -> list:
    """文頭の記号（Markdown の `**` `![` `*` など）を除いた実質的な先頭形態素列を返す。

    sudachi はこれらをいずれも「補助記号」として切り出すため、品詞で落とせる。
    """
    i = 0
    while i < len(morphemes) and morphemes[i].part_of_speech()[0] in TRAILING_SYMBOL_POS:
        i += 1
    return morphemes[i:]


def _strip_trailing_symbols(morphemes: list) -> list:
    """文末の記号（」など）を除いた実質的な最終形態素列を返す。"""
    i = len(morphemes)
    while i > 0 and morphemes[i - 1].part_of_speech()[0] in TRAILING_SYMBOL_POS:
        i -= 1
    return morphemes[:i]


def detect_nominal_ending_and_paragraph_conjunctions(
    lines: list[tuple[int, str]],
    tokenized: list[TokenizedSentence],
    raw_lines_by_no: dict[int, str] | None = None,
    nominal_min_sentences: int = NOMINAL_ENDING_MIN_SENTENCES,
    nominal_ratio_threshold: float = NOMINAL_ENDING_RATIO_THRESHOLD,
    nominal_min_chars: int = NOMINAL_ENDING_MIN_CHARS,
    conj_min_paragraphs: int = PARAGRAPH_CONJ_MIN_PARAGRAPHS,
    conj_ratio_threshold: float = PARAGRAPH_CONJ_RATIO_THRESHOLD,
    uniform_min_paragraphs: int = UNIFORM_PARAGRAPH_MIN_PARAGRAPHS,
    uniform_cv_threshold: float = UNIFORM_PARAGRAPH_CV_THRESHOLD,
) -> tuple[list[Finding], dict]:
    """sudachipy で形態素解析し、
    1) 体言止めの「欠如」（長文なのに体言止めが1つもない = 人間的修辞の欠如）
    2) 段落頭の接続詞率
    を計測する。stats も返す（JSON用）。

    体言止め検出はコーパス校正（2026-07）で方向を反転した。反転前は
    「体言止めが多い」ことを AI 臭として警告していたが、実コーパスでは
    体言止めは人間側の方が圧倒的に多く使う修辞技法（essay同ジャンルで
    人間60% vs AI 0%）だったため、前提が逆だった。現在は「ある程度の
    長さの文書なのに体言止めが1つもない」ことを、人間的な修辞技法の欠如
    （AIらしさの一側面）として info レベルで示す。
    """
    nominal_ending_count = 0
    total_sentences = 0
    total_chars = 0
    last_line = 1

    for ts in tokenized:
        total_sentences += 1
        total_chars += len(ts.raw_text)
        last_line = ts.line
        effective = _strip_trailing_symbols(ts.morphemes)
        if not effective:
            continue
        last = effective[-1]
        pos = last.part_of_speech()[0]
        # 体言止め: 実質的な最終形態素が名詞（助動詞「だ/です」等が続かない）場合
        if pos in NOUN_ENDING_POS:
            nominal_ending_count += 1

    ratio = nominal_ending_count / total_sentences if total_sentences else 0.0

    findings = []
    if (
        total_sentences >= nominal_min_sentences
        and total_chars >= nominal_min_chars
        and ratio <= nominal_ratio_threshold
    ):
        # 「欠如」の検出なので、体言止めの文自体は存在しない。指摘対象の1文を
        # 指させないため、文書末尾の行に1件だけ finding を出す（一覧性重視）。
        findings.append(
            Finding(
                line=last_line,
                category="nominal_ending",
                excerpt=f"体言止め0件（全{total_sentences}文、約{total_chars}字）",
                severity="info",
                detail=(
                    "この文書には体言止めが1つもない。ある程度の長さの文書で一度も使わないのは、"
                    "AI の書いた文章によく見られる特徴"
                ),
            )
        )

    # 段落頭の接続詞率
    # 段落を行番号付きでグルーピングすることで、段落開始行が直接分かる
    # （re.split + テキスト検索による line_cursor 近似だと、同一内容の段落が
    # 複数回登場したときに誤帰属していたため、行ベースの分割に置き換えた）。
    paragraphs = iter_paragraphs_with_lines(lines)
    conj_paragraph_count = 0
    total_paragraphs = len(paragraphs)
    conj_findings = []
    sentence_counts_per_paragraph = []
    for para_lines in paragraphs:
        first_no, first_line_raw = para_lines[0]
        first_line_text = first_line_raw.strip()
        para_joined = "\n".join(t for _, t in para_lines)
        sentence_counts_per_paragraph.append(
            len([p for p in SENTENCE_SPLIT_RE.split(para_joined) if p.strip()])
        )
        for conj in PARAGRAPH_CONJUNCTIONS:
            if first_line_text.startswith(conj):
                conj_paragraph_count += 1
                conj_findings.append((first_no, first_line_text, conj))
                break

    conj_ratio = conj_paragraph_count / total_paragraphs if total_paragraphs else 0.0
    if total_paragraphs >= conj_min_paragraphs and conj_ratio >= conj_ratio_threshold:
        conj_lines = [no for no, _, _ in conj_findings]
        related = format_related_lines(conj_lines)
        for no, text_line, conj in conj_findings:
            excerpt_source = _raw_or_masked(raw_lines_by_no, no, text_line)
            findings.append(
                Finding(
                    line=no,
                    category="paragraph_lead_conjunction",
                    excerpt=excerpt_source[:40],
                    severity="info",
                    detail=(
                        f"段落頭が接続詞「{conj}」で始まる（文書全体の段落頭接続詞率={conj_ratio:.1%}、"
                        f"閾値{conj_ratio_threshold:.0%}以上で警告）。{related}"
                    ),
                    related_lines=conj_lines,
                )
            )

    # 段落構造の均質性: AI は「3文段落」を量産しがち。段落あたり文数の変動係数が
    # 極端に低い（＝どの段落もほぼ同じ文数）場合は定型段落の疑いとして警告する。
    para_structure_stats = {
        "paragraph_sentence_counts": sentence_counts_per_paragraph,
        "paragraph_sentence_count_cv": None,
    }
    if len(sentence_counts_per_paragraph) >= uniform_min_paragraphs:
        p_mean = statistics.mean(sentence_counts_per_paragraph)
        p_std = statistics.pstdev(sentence_counts_per_paragraph)
        p_cv = (p_std / p_mean) if p_mean else 0.0
        para_structure_stats["paragraph_sentence_count_cv"] = p_cv
        if p_cv < uniform_cv_threshold:
            findings.append(
                Finding(
                    line=1,
                    category="uniform_paragraph_structure",
                    excerpt=f"段落数={len(sentence_counts_per_paragraph)}, 各段落の文数={sentence_counts_per_paragraph}",
                    severity="info",
                    detail=(
                        f"段落あたり文数の変動係数={p_cv:.3f}（閾値{uniform_cv_threshold}未満）。"
                        "どの段落もほぼ同じ文数=定型段落（例: 3文段落の量産）の疑い"
                    ),
                )
            )

    stats = {
        "total_sentences": total_sentences,
        "nominal_ending_count": nominal_ending_count,
        "nominal_ending_ratio": ratio,
        "total_paragraphs": total_paragraphs,
        "paragraph_lead_conjunction_count": conj_paragraph_count,
        "paragraph_lead_conjunction_ratio": conj_ratio,
        **para_structure_stats,
    }
    return findings, stats


def detect_translationese_morph(tokenized: list[TokenizedSentence]) -> list[Finding]:
    """品詞列で「こと（名詞）+ が/は（助詞）+ でき〜（動詞、"でき"始まりの活用形）」の並びを
    検出する、翻訳調「〜することができる」の品詞列版。
    表層の正規表現（TRANSLATIONESE_PATTERNS）と違い、直前の動詞部分の送り仮名や
    活用（〜することができる/〜出来ます/〜出来た 等）の表記揺れに影響されない。
    注意: 「こと」の前に本当に動詞（〜する）が来ているかまでは確認していない
    （「このことができる」のような非対象ケースを完全には除外できない）。
    """
    findings = []
    for ts in tokenized:
        surfaces = [m.surface() for m in ts.morphemes]
        poss = [m.part_of_speech()[0] for m in ts.morphemes]
        n = len(ts.morphemes)
        for i in range(n):
            # 「こと」(名詞) + が/は(助詞) + でき(動詞語幹)... の並びを探す
            if surfaces[i] == "こと" and poss[i] == "名詞":
                j = i + 1
                if j < n and poss[j] == "助詞" and surfaces[j] in {"が", "は"}:
                    k = j + 1
                    if k < n and poss[k] == "動詞" and surfaces[k].startswith("でき"):
                        # excerptは形態素のbegin/end（マスク済みテキスト内オフセット）を使い、
                        # 原文（raw_text）から同じ位置を切り出す（インラインコードスパンの
                        # バッククォート内文字列が欠落しないようにするため）。
                        span_start = ts.morphemes[max(0, i - 4)].begin()
                        span_end = ts.morphemes[k].end()
                        excerpt = ts.raw_text[span_start:span_end]
                        findings.append(
                            Finding(
                                line=ts.line,
                                category="translationese_morph",
                                excerpt=excerpt,
                                severity="info",
                                detail="「〜することができる」型の言い回し",
                            )
                        )
    return findings


# 拗音を作る小書き文字（ャュョァィゥェォヮ）。「キャ」のように直前の文字と
# 合わせて1モーラを構成するため、単純な文字数カウントだと過大カウントになる。
# 促音（ッ）・長音（ー）は独立した1モーラとして数えるため、ここには含めない。
_SMALL_KANA_MERGE = set("ァィゥェォャュョヮ")


def mora_length(morphemes: list) -> int:
    """読み（カタカナ）を基にモーラ数の近似値を計算する。
    拗音の小書き文字（ャュョ等）は直前の文字と合算して1モーラとして数える
    補正を行うが、それ以外の長音・促音等の厳密な処理まではしていない。
    """
    total = 0
    for m in morphemes:
        reading = m.reading_form() or m.surface()
        count = 0
        for ch in reading:
            if ch in _SMALL_KANA_MERGE and count > 0:
                # 直前の文字と合わせて1モーラなので、追加でカウントしない
                continue
            count += 1
        total += count
    return total


def detect_rhythm_statistics(
    tokenized: list[TokenizedSentence],
    min_tokenized: int = BURSTINESS_MIN_TOKENIZED,
    burstiness_threshold: float = BURSTINESS_THRESHOLD,
    autocorr_min_xs: int = AUTOCORR_MIN_XS,
    autocorr_threshold: float = AUTOCORR_THRESHOLD,
) -> tuple[list[Finding], dict]:
    """文字数だけでなくモーラ近似長を使い、単純な変動係数に加えて
    burstiness（(σ-μ)/(σ+μ)）と隣接文長の自己相関（lag-1）を計測する。
    - burstiness が負に大きい ≈ 文長が均一（AI的）
    - 自己相関が高い ≈ 「短い文の後は短い文」というリズムパターンが固定化している
    """
    if len(tokenized) < min_tokenized:
        return [], {}

    mora_lengths = [mora_length(ts.morphemes) for ts in tokenized]
    mean = statistics.mean(mora_lengths)
    std = statistics.pstdev(mora_lengths)

    findings = []
    burstiness = (std - mean) / (std + mean) if (std + mean) else 0.0

    # lag-1 自己相関（ピアソン相関を1つずらした系列同士で計算）
    xs = mora_lengths[:-1]
    ys = mora_lengths[1:]
    autocorr = None
    if len(xs) >= autocorr_min_xs and statistics.pstdev(xs) > 0 and statistics.pstdev(ys) > 0:
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs)
        autocorr = cov / (statistics.pstdev(xs) * statistics.pstdev(ys))

    # 閾値 -0.62: このスキルの原則は「自然な人間の文章で誤検知しない」こと。
    # 人間が書いた自然な文章（fixtures/natural.md 相当）でも burstiness は
    # -0.55 前後まで下がることが実測で分かっている（モーラ計算の拗音補正後の実測値）。
    # -0.55 ちょうどを閾値にすると、その実測値のごく僅かな変動で人間の文章にまで
    # 誤検知するため、マージンを取って -0.62 まで緩めている。
    if burstiness < burstiness_threshold:
        findings.append(
            Finding(
                line=tokenized[0].line,
                category="low_burstiness",
                excerpt=f"burstiness={burstiness:.3f} (モーラ近似長 平均={mean:.1f}, 標準偏差={std:.1f})",
                severity="warn",
                detail=f"文の長短の差が小さい（burstiness が閾値{burstiness_threshold}未満）。文の長さがそろいすぎている疑い",
            )
        )

    if autocorr is not None and autocorr > autocorr_threshold:
        findings.append(
            Finding(
                line=tokenized[0].line,
                category="high_length_autocorrelation",
                excerpt=f"lag-1 自己相関={autocorr:.3f}",
                severity="info",
                detail=f"隣接する文の長さが強く相関（閾値{autocorr_threshold}超）。文長パターンが単調に繰り返されている疑い",
            )
        )

    stats = {
        "mora_mean": mean,
        "mora_stdev": std,
        "burstiness": burstiness,
        "length_autocorrelation_lag1": autocorr,
    }
    return findings, stats


# 文頭反復の severity 判定: 固有名詞・製品名/技術用語（ラテン文字主体の表層）が
# 文頭に来る場合は「そして」「また」のような定型導入の使い回しとは性質が異なり、
# 技術文書では自然な反復（例: 「Cloudflareは」「better-authが」）なので
# severity を warn ではなく info に下げる（検出自体は残し、判断材料として提示する）。
_LATIN_TECH_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-_.]*$")


def _is_proper_noun_or_tech_term(morpheme) -> bool:
    """先頭形態素が固有名詞、またはラテン文字・数字主体（製品名/ライブラリ名等）かを判定する。
    カタカナ語は一般語（「クラウド」「システム」等）も多く誤って severity を下げるリスクが
    高いため、ここでは対象外とする（迷ったら対象外でよい、という方針）。
    """
    pos = morpheme.part_of_speech()
    surface = morpheme.surface()
    is_proper_noun = pos[0] == "名詞" and pos[1] == "固有名詞"
    is_latin_tech = bool(_LATIN_TECH_TOKEN_RE.match(surface))
    return is_proper_noun or is_latin_tech


def detect_ngram_repetition(
    tokenized: list[TokenizedSentence],
    lead_repeat_threshold: int = NGRAM_LEAD_REPEAT_THRESHOLD,
    template_min_count: int = NGRAM_TEMPLATE_MIN_COUNT,
    template_ratio_threshold: float = NGRAM_TEMPLATE_RATIO_THRESHOLD,
) -> tuple[list[Finding], dict]:
    """
    1) 文頭2形態素（表層形）の n-gram が3回以上繰り返される
       → 「そして、」「また、」のような定型導入の使い回し
       ただし先頭形態素が固有名詞・ラテン文字主体の技術用語（製品名/ライブラリ名等）の
       場合は技術文書として自然な反復なので severity を info に下げる（検出自体は残す）。
    2) 文頭のPOS 4-gram（品詞の粗い並び）の一致率が高い
       → 語彙は違っても構文テンプレートが同じ（AIにありがちな構造の使い回し）
    をそれぞれ検出する。
    """
    from collections import Counter

    findings = []

    lead_bigrams = []
    for ts in tokenized:
        # 文頭の補助記号を落としてから2形態素を取る。マスク処理は行単位の構造
        # （見出し・リスト・引用・表）とインラインコード/URLしか落とさないため、
        # インラインの強調記法（`**強調**`）や画像記法（`![alt](url)`）のマーカーが
        # 文頭に残る。これを数えると「文頭2形態素が **」という無意味な反復が量産される。
        # zenn-content 60本の実測で repeated_sentence_lead 236件のうち 100件（42%）が
        # この記号由来だった（`**` 88件 / `![` 12件）。
        lead_morphemes = _strip_leading_symbols(ts.morphemes)[:2]
        surfaces = [m.surface() for m in lead_morphemes]
        if len(surfaces) == 2:
            # 文頭が固有名詞・英字の技術用語・数(「2019年」「日本・」「Amazon」「Python」など)の
            # 反復は、記事の主題や日付を並べた自然な書き方で、人間の文書でも同じだけ出る
            # (2026-10 の測定で、人間の文書と生成AIの文書で件数に差がなかった)。数えない。
            first = lead_morphemes[0]
            if _is_proper_noun_or_tech_term(first) or first.part_of_speech()[1] == "数詞" or re.match(r"[0-9０-９]", first.surface()):
                continue
            lead_bigrams.append((ts.line, ts.raw_text, "".join(surfaces), False))

    bigram_counter = Counter(text for _, _, text, _ in lead_bigrams)
    for bigram, count in bigram_counter.items():
        if count >= lead_repeat_threshold:
            bigram_lines = [no for no, _, text, _ in lead_bigrams if text == bigram]
            related = format_related_lines(bigram_lines)
            # 同じ書き出しの反復は、反復ごとに1件にまとめる(出現ごとに数えると件数が膨らみ、
            # 指摘の大半を占めてしまう)。severity は常に info(人間の意図的な反復と区別できない)。
            no, sent, _, _ = next(x for x in lead_bigrams if x[2] == bigram)
            findings.append(
                Finding(
                    line=no,
                    category="repeated_sentence_lead",
                    excerpt=sent[:20],
                    severity="info",
                    detail=(
                        f"文頭2形態素「{bigram}」が{count}回反復（閾値{lead_repeat_threshold}回以上）。"
                        f"人間が意図して繰り返す場合と区別がつかないため、参考情報。{related}"
                    ),
                    related_lines=bigram_lines,
                )
            )

    lead_pos_ngrams = []
    for ts in tokenized:
        # 文頭2形態素と同じ理由で、ここでも文頭の補助記号を落としてから品詞列を取る
        # （落とさないと「補助記号/補助記号/名詞/助詞」が量産され一致率が跳ね上がる）。
        pos_seq = tuple(m.part_of_speech()[0] for m in _strip_leading_symbols(ts.morphemes)[:4])
        if len(pos_seq) == 4:
            lead_pos_ngrams.append((ts.line, ts.raw_text, pos_seq))

    total_with_ngram = len(lead_pos_ngrams)
    pos_counter = Counter(seq for _, _, seq in lead_pos_ngrams)
    stats = {"lead_pos_4gram_top": None, "lead_pos_4gram_ratio": None}
    if total_with_ngram >= template_min_count and pos_counter:
        top_seq, top_count = pos_counter.most_common(1)[0]
        ratio = top_count / total_with_ngram
        stats["lead_pos_4gram_top"] = "/".join(top_seq)
        stats["lead_pos_4gram_ratio"] = ratio
        if ratio >= template_ratio_threshold:
            template_lines = [no for no, _, seq in lead_pos_ngrams if seq == top_seq]
            related = format_related_lines(template_lines)
            for no, sent, seq in lead_pos_ngrams:
                if seq == top_seq:
                    findings.append(
                        Finding(
                            line=no,
                            category="repeated_syntax_template",
                            excerpt=sent[:20],
                            severity="info",
                            detail=(
                                f"文頭品詞4-gram「{'/'.join(top_seq)}」が全文の{ratio:.1%}で一致"
                                f"（閾値{template_ratio_threshold:.0%}以上）。構文テンプレートの使い回しの疑い。{related}"
                            ),
                            related_lines=template_lines,
                        )
                    )

    return findings, stats


def compute_mtld(tokens: list[str], threshold: float = 0.72) -> float | None:
    """MTLD（Measure of Textual Lexical Diversity）の簡易実装。
    文長に依存しにくい語彙多様性指標。TTR が threshold を下回るごとに
    「1ファクター」を数え、前方・後方2方向の平均をとる。
    """
    if len(tokens) < 20:
        return None

    def factors_one_direction(seq: list[str]) -> float:
        factor_count = 0
        types: set[str] = set()
        token_count = 0
        for tok in seq:
            types.add(tok)
            token_count += 1
            ttr = len(types) / token_count
            if ttr <= threshold:
                factor_count += 1
                types = set()
                token_count = 0
        # 端数分を部分ファクターとして加算
        if token_count > 0:
            types_ttr = len(types) / token_count if token_count else 1.0
            partial = (1 - types_ttr) / (1 - threshold) if types_ttr < 1 else 0.0
            factor_count += min(partial, 1.0)
        return len(seq) / factor_count if factor_count > 0 else float(len(seq))

    forward = factors_one_direction(tokens)
    backward = factors_one_direction(list(reversed(tokens)))
    return (forward + backward) / 2


def detect_lexical_diversity(
    tokenized: list[TokenizedSentence],
    min_tokens: int = LEXDIV_MIN_TOKENS,
    ttr_threshold: float = TTR_THRESHOLD,
    mtld_threshold: float = MTLD_THRESHOLD,
    min_doc_chars: int = LEXDIV_MIN_DOC_CHARS,
) -> tuple[list[Finding], dict]:
    """内容語（名詞/動詞/形容詞/副詞）の基本形を対象に TTR と MTLD を計測する。
    語彙が使い回されている（AIが同じ言い回しをループしがち）と TTR/MTLD が低くなる。

    2026-07 コーパス校正（corpus/reports/archive/length_analysis.md）: TTR は文書長
    ~4000字未満のビンではhuman/aiとも一律0%で、統計として機能していない
    ことが判明した。4000字以上のビンで初めて意味のある差（human 77%）が
    出るため、文書全体の文字数が min_doc_chars 未満の場合は「文書が短いため
    未評価」として明示的にスキップする（閾値ではなく適用条件でガードする、
    という報告書の推奨に沿った実装）。
    """
    content_tokens = []
    total_doc_chars = sum(len(ts.raw_text) for ts in tokenized)
    for ts in tokenized:
        for m in ts.morphemes:
            if m.part_of_speech()[0] in CONTENT_WORD_POS:
                content_tokens.append(m.dictionary_form())

    findings = []
    stats = {
        "ttr": None,
        "mtld": None,
        "content_token_count": len(content_tokens),
        "doc_char_count": total_doc_chars,
        "skipped_too_short": False,
    }
    if total_doc_chars < min_doc_chars:
        stats["skipped_too_short"] = True
        return findings, stats
    if len(content_tokens) >= min_tokens:
        ttr = len(set(content_tokens)) / len(content_tokens)
        mtld = compute_mtld(content_tokens)
        stats["ttr"] = ttr
        stats["mtld"] = mtld
        if ttr < ttr_threshold:
            findings.append(
                Finding(
                    line=tokenized[0].line,
                    category="low_lexical_diversity_ttr",
                    excerpt=f"TTR={ttr:.3f} (内容語 {len(content_tokens)} 語中 {len(set(content_tokens))} 種類)",
                    severity="info",
                    detail=f"TTR(Type-Token Ratio)が閾値{ttr_threshold}未満。同じ語彙の使い回しが多い疑い",
                )
            )
        if mtld is not None and mtld < mtld_threshold:
            findings.append(
                Finding(
                    line=tokenized[0].line,
                    category="low_lexical_diversity_mtld",
                    excerpt=f"MTLD={mtld:.1f}",
                    severity="info",
                    detail=f"MTLD が閾値{mtld_threshold}未満。文章長で正規化した語彙多様性が低い疑い",
                )
            )
    return findings, stats


_URL_IN_TEXT_RE = re.compile(r"https?://\S+")


_IDENTIFIER_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_.\-]*[A-Za-z0-9](?![A-Za-z0-9_])")


def detect_low_specificity(
    lines: list[tuple[int, str]],
    raw_lines_by_no: dict[int, str] | None = None,
    min_chars: int = LOW_SPECIFICITY_MIN_CHARS,
    min_content_words: int = LOW_SPECIFICITY_MIN_CONTENT_WORDS,
    proper_noun_weight: float = LOW_SPECIFICITY_PROPER_NOUN_WEIGHT,
    numeric_weight: float = LOW_SPECIFICITY_NUMERIC_WEIGHT,
    example_marker_bonus: float = LOW_SPECIFICITY_EXAMPLE_MARKER_BONUS,
    abstract_noun_weight: float = LOW_SPECIFICITY_ABSTRACT_NOUN_WEIGHT,
    score_threshold: float = LOW_SPECIFICITY_SCORE_THRESHOLD,
) -> tuple[list[Finding], dict]:
    """段落単位で「具体性の欠如（一般論臭）」を検出する。

    固有名詞密度・数値/日付出現率・例示マーカーの有無を「具体性シグナル」として
    加点し、形式名詞・抽象名詞率を減点した合成スコアが閾値未満の段落を拾う。
    短い段落は誰が書いてもある程度抽象的になりうるため、文字数・内容語数の
    両方が最低ラインを超えた段落だけを判定対象にする（gate）。

    これは文体（言い回し）の問題ではなく、段落を支える固有名詞・数値・一次情報
    そのものが足りていない「素材不足」のサインであるため、detail では
    書き直しではなく情報収集を検討するよう促す
    （SKILL.md §1「素材」と §3 を参照）。
    """
    tokenizer = get_tokenizer()
    from sudachipy import SplitMode

    findings: list[Finding] = []
    paragraphs = iter_paragraphs_with_lines(lines)
    evaluated = 0
    fired = 0

    for para_lines in paragraphs:
        first_no, _ = para_lines[0]
        para_masked = "\n".join(t for _, t in para_lines)
        para_chars = len(para_masked)
        if para_chars < min_chars:
            continue

        # sudachipy は1回のtokenize呼び出しに約49KBのバイト数上限があるため、
        # 段落が長大な場合（青空文庫の長い段落等）に備えて行単位で分割して
        # トークナイズし、結果を連結する（行番号・オフセットは形態素解析後は
        # 使わないため連結して問題ない）。
        morphemes = []
        for _, para_line in para_lines:
            if not para_line.strip():
                continue
            morphemes.extend(tokenizer.tokenize(para_line, SplitMode.C))
        content_words = [m for m in morphemes if m.part_of_speech()[0] in CONTENT_WORD_POS]
        if len(content_words) < min_content_words:
            continue

        evaluated += 1

        proper_noun_count = sum(
            1 for m in content_words if m.part_of_speech()[0] == "名詞" and m.part_of_speech()[1] == "固有名詞"
        )
        # 英字の識別子(React、useState、`config.yaml` など)も、段落を具体的にする名前として数える。
        # インラインコードは解析用テキストでは空白にしてあるので、原文の行から数える。
        # sudachipy が英字の語を固有名詞と判定した分と二重に数えないよう、多いほうを採る。
        raw_para = "\n".join(_raw_or_masked(raw_lines_by_no, no, t) for no, t in para_lines)
        raw_para = _URL_IN_TEXT_RE.sub(" ", raw_para)
        identifier_count = len(_IDENTIFIER_RE.findall(raw_para))
        latin_proper = sum(
            1 for m in content_words
            if m.part_of_speech()[1] == "固有名詞" and re.fullmatch(r"[A-Za-z][\w.\-]*", m.surface())
        )
        proper_noun_count += max(0, identifier_count - latin_proper)
        abstract_noun_count = sum(
            1
            for m in content_words
            if m.part_of_speech()[0] == "名詞" and m.dictionary_form() in ABSTRACT_NOUN_WORDS
        )
        numeric_hit_count = len(list(NUMERIC_QUANTITY_RE.finditer(para_masked)))
        has_example_marker = any(marker in para_masked for marker in EXAMPLE_MARKER_WORDS)

        n_content = len(content_words)
        proper_noun_density = proper_noun_count / n_content
        numeric_density = numeric_hit_count / n_content
        abstract_noun_ratio = abstract_noun_count / n_content

        score = (
            proper_noun_density * proper_noun_weight
            + numeric_density * numeric_weight
            + (example_marker_bonus if has_example_marker else 0.0)
            - abstract_noun_ratio * abstract_noun_weight
        )

        if score < score_threshold:
            fired += 1
            excerpt_source = _raw_or_masked(raw_lines_by_no, first_no, para_lines[0][1])
            findings.append(
                Finding(
                    line=first_no,
                    category="low_specificity",
                    excerpt=excerpt_source.strip()[:40],
                    severity="info",
                    detail=(
                        f"段落の具体性スコア={score:.3f}（閾値{score_threshold}未満）。"
                        f"固有名詞密度={proper_noun_density:.3f}, 数値密度={numeric_density:.3f}, "
                        f"抽象名詞率={abstract_noun_ratio:.3f}, 例示マーカー={'あり' if has_example_marker else 'なし'}。"
                        "固有名詞・数値・実例が乏しく一般論に留まっている疑い。"
                        "素材が足りていないサイン"
                    ),
                )
            )

    stats = {
        "paragraphs_evaluated": evaluated,
        "paragraphs_fired": fired,
    }
    return findings, stats


# nested_attributive（連体修飾の入れ子検出）は 2026-07 コーパス校正で削除した。
# sweep_nested_attributive.md: 閾値1〜6のどの値でも人間FP率が5%を切らず
# （閾値3で人間85.4%が発火、AIも100%発火。閾値6まで緩めても人間51.2%が発火）、
# deep-analysis.md でも essay同ジャンルで人間100% vs AI 92〜100%とほぼ差がない
# 「全発火・弁別力なし」と判定された。閾値調整では救えないノイズだったため、
# 検出器そのものと専用ヘルパー（旧 build_line_to_paragraph_map）を削除している。
# 経緯は corpus/reports/archive/sweep_nested_attributive.md に記載。

# ---------------------------------------------------------------------------
# 英語統語の検出（挑戦枠）
# ---------------------------------------------------------------------------

# 無生物主語（＋こと/事実など形式名詞化）+ 他動詞的な述語、という
# 「英語を日本語に直訳した構文」のシグナルをまず正規表現で粗く拾う。
# sudachipy で主語の生物性判定を厳密にやるのは困難なため、
# 「これ/それ/この事実/〜こと/〜という事実」+ 「は/が」+ 文末近くの
# 他動詞（〜を〜する系）という表層パターンでヒューリスティックに検出する。
INANIMATE_SUBJECT_PATTERNS = [
    re.compile(r"(これ|それ|この事実|そのこと)(は|が).{0,40}(もたらす|示す|意味する|証明する|生み出す|反映する)"),
    re.compile(r".{0,20}(こと|事実)(は|が).{0,40}(もたらす|示す|意味する|証明する|生み出す|反映する)"),
]


# 「それは〜である。なぜなら〜だ」構文（隣接する2文にまたがるので
# 文リストを走査して検出する）
CLEFT_BECAUSE_HEAD = re.compile(r"^(それ|これ|この)は.{0,60}(である|だ)$")


BECAUSE_HEAD = re.compile(r"^(なぜなら|というのも)")


def detect_english_syntax_smell(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    findings = []
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for pat in INANIMATE_SUBJECT_PATTERNS:
            for m in re.finditer(pat, line):
                excerpt = raw_line[m.start() : m.end()] if len(raw_line) >= m.end() else m.group(0)
                findings.append(
                    Finding(
                        line=no,
                        category="english_syntax_inanimate_subject",
                        excerpt=excerpt,
                        severity="info",
                        detail="もの・ことを主語にして他動詞で受ける、英語の構文の直訳の疑い",
                    )
                )

    # マスク済みテキストで構文マッチしつつ、excerpt は原文の文（raw）から組み立てる
    sentences = split_sentences_with_lines(lines, raw_lines_by_no)
    for i in range(len(sentences) - 1):
        no1, s1, r1 = sentences[i]
        no2, s2, r2 = sentences[i + 1]
        if CLEFT_BECAUSE_HEAD.match(s1) and BECAUSE_HEAD.match(s2):
            findings.append(
                Finding(
                    line=no1,
                    category="english_syntax_cleft_because",
                    excerpt=f"{r1}。{r2}",
                    severity="warn",
                    detail="「それは〜である。なぜなら〜だ」型の強調構文（英語 It is ... because ... の直訳調）",
                )
            )
    return findings


def detect_inanimate_subject_morph(tokenized: list[TokenizedSentence]) -> list[Finding]:
    """品詞列ベースで「無生物主語(抽象代名詞/形式名詞) + が/は + 他動詞的述語」を検出する。
    厳密な生物性判定（有情/非情の意味論）は sudachipy の POS だけでは困難なため、
    「これ/それ/この事実」等の抽象指示語、または「〜こと/〜という事実」のような
    形式名詞化された主語に限定して、他動詞辞書（TRANSITIVE_SMELL_VERBS）とマッチする
    述語が同一文内に現れる場合のみ検出する。表層正規表現版より活用の揺れに強い。
    """
    findings = []
    for ts in tokenized:
        surfaces = [m.surface() for m in ts.morphemes]
        poss = [m.part_of_speech()[0] for m in ts.morphemes]
        dict_forms = [m.dictionary_form() for m in ts.morphemes]
        n = len(ts.morphemes)
        # 2形態素の指示表現（例:「この事実」）を「この」で先にマッチさせた場合、
        # 続く「事実」単体も形式名詞として再マッチしてしまい、同じ箇所が
        # 二重に検出されてしまう。skip_until でその形態素インデックスまでの
        # 単独マッチを抑制する。
        skip_until = -1
        for i in range(n):
            if i <= skip_until:
                continue
            # 単一形態素で成立する指示語・形式名詞
            is_abstract_subject = surfaces[i] in ABSTRACT_PRONOUNS or (
                poss[i] == "名詞" and surfaces[i] in {"こと", "事実", "の"}
            )
            subject_end = i
            if not is_abstract_subject:
                # 2形態素にまたがる指示表現（「この」+「事実」等）を、
                # 隣接する形態素を連結した表層文字列で判定する
                if i + 1 < n and (surfaces[i] + surfaces[i + 1]) in ABSTRACT_PRONOUN_PHRASES:
                    is_abstract_subject = True
                    subject_end = i + 1
            if not is_abstract_subject:
                continue
            skip_until = max(skip_until, subject_end)
            j = subject_end + 1
            if j >= n or poss[j] != "助詞" or surfaces[j] not in {"が", "は"}:
                continue
            # 主語マーカーの後、文末までの間に直訳調の他動詞があるか探す
            for k in range(j + 1, n):
                if poss[k] == "動詞" and dict_forms[k] in TRANSITIVE_SMELL_VERBS:
                    # excerptはbegin/end（マスク済みテキスト内オフセット）を使い、
                    # 原文（raw_text）から同じ位置を切り出す
                    span_start = ts.morphemes[max(0, i - 3)].begin()
                    span_end = ts.morphemes[k].end()
                    excerpt = ts.raw_text[span_start:span_end]
                    subject_text = "".join(surfaces[i : subject_end + 1])
                    findings.append(
                        Finding(
                            line=ts.line,
                            category="inanimate_subject_morph",
                            excerpt=excerpt,
                            severity="info",
                            detail=(
                                f"品詞列マッチ: 抽象主語「{subject_text}」+ {surfaces[j]} "
                                f"+ 他動詞的述語「{dict_forms[k]}」（英語統語の直訳調の疑い）"
                            ),
                        )
                    )
                    break
    return findings


# ---------------------------------------------------------------------------
# 構造層検出器（2026-07 コーパス校正で新設）
#
# ここまでの検出器はすべて Markdown 構造をマスクした「地の文」に対して働く。
# しかし deep-analysis.md §4c の5文書精読では、AI 生成文（特に claude-haiku-4-5
# のtech系）に「太字の多用」「番号付きフェーズ構造」「『まとめ』『おわりに』
# 定型見出しでの締め」といった、文章そのものではなく Markdown 構造レベルの
# 教科書的な癖が繰り返し観測された。この一群は逆にマスク前の raw テキストを
# 見る必要があるため、run_lint() 内で mask_markdown_structure() より前に
# 呼び出す専用の検出器ファミリーとして新設する。
#
# 注意: この一群はまだ deep-analysis.md の定量コーパス計測を経ておらず、
# 5文書の質的観察のみが根拠（暫定閾値）。EXPERIMENTAL_CATEGORIES に含めて
# デフォルト無効化し、--experimental フラグを付けたときだけ有効にする。
# ただし太字の多用(high_bold_density)だけは 2026-10 に測って既定で有効にした。
# 行頭の「**ラベル**:」を除いた文中の太字が1000字あたり3回以上(かつ3か所以上)になるのは、生成AI以前の Qiita 2022 で6%、
# LLM-jp 由来で0%、生成記事で6%、Qiita 2026 で22%。ラベルの太字は、作者の読み比べで残したほうが読みやすく探しやすかった。
# 作者の文書を推敲した版で、文中の太字が「ノイズで読みづらい」と言われた
# (corpus/reports/readability-ooda.md の11周目)。仕事の文書でも多すぎる太字は読みにくいので、
# business ジャンルでも無効にしない。
# ---------------------------------------------------------------------------
BOLD_SPAN_RE = re.compile(r"\*\*[^*\n]+\*\*")


# 行頭(箇条の頭を含む)の「**ラベル**:」は項目を探す目印なので数えない
BOLD_LABEL_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*\*\*[^*\n]+\*\*\s*[:：]", re.M)


BOLD_DENSITY_PER_1000_THRESHOLD = 3.0


BULLET_LINE_RATIO_THRESHOLD = 0.35


BULLET_LINE_MIN_LINES = 10


# 「まとめ」「おわりに」等の定型見出し（本文の中身ではなく予告的な構成の型を示す）
BOILERPLATE_HEADING_WORDS = {
    "まとめ",
    "おわりに",
    "終わりに",
    "さいごに",
    "最後に",
    "結論",
    "総括",
    "conclusion",
}


NUMBERED_PHASE_RE = re.compile(r"(フェーズ|ステップ|段階|ステージ)\s*[0-90-9１-９]")


NUMBERED_PHASE_MIN_COUNT = 3


# 絵文字・装飾記号（代表的なものに限定。厳密な Unicode 絵文字判定は行わない）
EMOJI_SYMBOL_RE = re.compile(
    "[\U0001F300-\U0001FAFF☀-➿⭐✅❌❗❓]"
)


EMOJI_SYMBOL_PER_1000_THRESHOLD = 2.0


def detect_structural_ai_habits(raw_text: str) -> tuple[list[Finding], dict]:
    """マスク前の raw テキストに対して、Markdown 構造レベルの「教科書的AI癖」を検出する。
    太字密度・箇条書き行比率・定型見出し・番号付きフェーズ構造・絵文字/装飾記号密度の
    5種類。すべて severity="info"、EXPERIMENTAL カテゴリ扱い（デフォルト無効）。
    """
    findings: list[Finding] = []
    raw_lines = iter_lines_with_no(raw_text)
    total_chars = len(raw_text) or 1

    # 1) 太字密度
    label_starts = {m.end() - len(m.group(0).lstrip()) for m in BOLD_LABEL_RE.finditer(raw_text)}
    bold_hits = [m for m in BOLD_SPAN_RE.finditer(raw_text)
                 if not any(st <= m.start() <= st + 4 for st in label_starts)]
    bold_per_1000 = len(bold_hits) / total_chars * 1000
    if bold_per_1000 >= BOLD_DENSITY_PER_1000_THRESHOLD and len(bold_hits) >= 3:
        first_line = raw_text[: bold_hits[0].start()].count("\n") + 1
        findings.append(
            Finding(
                line=first_line,
                category="high_bold_density",
                excerpt=f"文中の太字{len(bold_hits)}箇所（1000字あたり{bold_per_1000:.2f}）",
                severity="info",
                detail=(
                    f"文中の強調の太字（**...**）が閾値（1000字あたり{BOLD_DENSITY_PER_1000_THRESHOLD}）"
                    "以上。行頭の「**ラベル**:」は数えていない"
                ),
            )
        )

    # 2) 箇条書き行比率
    non_blank_lines = [(no, line) for no, line in raw_lines if line.strip()]
    bullet_lines = [no for no, line in non_blank_lines if _LIST_ITEM_RE.match(line)]
    if len(non_blank_lines) >= BULLET_LINE_MIN_LINES:
        bullet_ratio = len(bullet_lines) / len(non_blank_lines)
        if bullet_ratio >= BULLET_LINE_RATIO_THRESHOLD:
            findings.append(
                Finding(
                    line=bullet_lines[0] if bullet_lines else 1,
                    category="high_bullet_ratio",
                    excerpt=f"箇条書き行{len(bullet_lines)}/{len(non_blank_lines)}行（{bullet_ratio:.1%}）",
                    severity="info",
                    detail=(
                        f"箇条書き行の比率が閾値{BULLET_LINE_RATIO_THRESHOLD:.0%}以上。"
                        "文章より箇条書きに頼る構成は教科書的なAI生成文に見られる傾向（実験的検出器）"
                    ),
                    related_lines=bullet_lines if len(bullet_lines) > 1 else None,
                )
            )

    # 3) 定型見出し（「まとめ」「おわりに」等）
    boilerplate_lines = []
    for no, line in iter_lines_with_no(raw_text):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        heading_text = line[m.end() :].strip().lower()
        for word in BOILERPLATE_HEADING_WORDS:
            if heading_text.startswith(word.lower()):
                boilerplate_lines.append((no, line.strip(), word))
                break
    for no, line_text, word in boilerplate_lines:
        findings.append(
            Finding(
                line=no,
                category="boilerplate_heading",
                excerpt=line_text[:40],
                severity="info",
                detail=(
                    f"定型見出し「{word}」系での締め。予告・構成の型のみで中身を語らない"
                    "教科書的なAI生成文に見られる傾向（実験的検出器）"
                ),
            )
        )

    # 4) 番号付きフェーズ構造（「フェーズ1」「ステップ2」等が3回以上）
    phase_hits = list(NUMBERED_PHASE_RE.finditer(raw_text))
    if len(phase_hits) >= NUMBERED_PHASE_MIN_COUNT:
        first_line = raw_text[: phase_hits[0].start()].count("\n") + 1
        findings.append(
            Finding(
                line=first_line,
                category="numbered_phase_structure",
                excerpt=f"番号付きフェーズ表現が{len(phase_hits)}回出現",
                severity="info",
                detail=(
                    f"「フェーズ/ステップ/段階+番号」の表現が閾値{NUMBERED_PHASE_MIN_COUNT}回以上。"
                    "機械的な段階分割は教科書的なAI生成文に見られる傾向（実験的検出器）"
                ),
            )
        )

    # 5) 絵文字・装飾記号の密度
    emoji_hits = list(EMOJI_SYMBOL_RE.finditer(raw_text))
    emoji_per_1000 = len(emoji_hits) / total_chars * 1000
    if emoji_per_1000 >= EMOJI_SYMBOL_PER_1000_THRESHOLD and len(emoji_hits) >= 3:
        first_line = raw_text[: emoji_hits[0].start()].count("\n") + 1
        findings.append(
            Finding(
                line=first_line,
                category="high_emoji_symbol_density",
                excerpt=f"絵文字/装飾記号{len(emoji_hits)}箇所（1000字あたり{emoji_per_1000:.2f}）",
                severity="info",
                detail=(
                    f"絵文字・装飾記号の使用密度が閾値（1000字あたり{EMOJI_SYMBOL_PER_1000_THRESHOLD}）"
                    "以上（実験的検出器、閾値は暫定）"
                ),
            )
        )

    stats = {
        "bold_span_count": len(bold_hits),
        "bold_per_1000_chars": bold_per_1000,
        "bullet_line_count": len(bullet_lines),
        "non_blank_line_count": len(non_blank_lines),
        "boilerplate_heading_count": len(boilerplate_lines),
        "numbered_phase_hit_count": len(phase_hits),
        "emoji_symbol_count": len(emoji_hits),
        "emoji_symbol_per_1000_chars": emoji_per_1000,
    }
    return findings, stats


def attach_hints(findings: list[Finding]) -> list[Finding]:
    for f in findings:
        if not f.hint:
            f.hint = HINTS.get(f.category, "")
    return findings
