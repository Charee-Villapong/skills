"""lint_reading.py — 読みにくそうな箇所の検査（読解負荷レーン）の検出器群。

AI臭さは測らない独立レーン（経緯は移設元のレーン冒頭コメント参照）。
統括関数 run_reading_load() は lint.py 側に残し、ここには検出器と
その定数・補助関数だけを置く。

C-002 の分割で lint.py からそのまま移したもの（ロジック変更なし）。
lint.py は従来の import 面を保つため、ここの名前をすべて再exportする。
"""

from __future__ import annotations

import re

from lint_detectors import (
    TRAILING_SYMBOL_POS,
    TokenizedSentence,
    attach_hints,
)
from textcore import (
    _CODE_FENCE_RE,
    Finding,
    _blank_inline_code_spans,
    iter_lines_with_no,
    mask_html_comments,
)

# ---------------------------------------------------------------------------
# 読みにくそうな箇所の検査（推敲で見る箇所を示すだけ）
#
# ここに並ぶ検出器は「AI臭さ」を測らない。自然度スコアにも、by_category 集計にも、
# --baseline 比較にも一切入らない。目的は「読みやすい文章に直す」ことだけで、
# 出力は「この文を見る」と示すだけにする（severity は常に info）。
#
# なぜ別レーンなのか:
#     corpus/reports/readability-sweep.md は、ここに実装した指標のほとんど
#     （文長・読点密度・二重否定・漢字比率）を候補として検証し、すべて NO-GO と
#     判定している。ただしその判定基準は「AI か人間かを弁別できるか」「下手な人間の
#     文章を当てられるか」であり、分類器としての採否基準だった。文長の AI 検出率が
#     1.0% だったのは「長い文は AI の証拠にならない」という意味であって、
#     「長い文は読みやすい」という意味ではない。レポート自身が結論している
#     とおり、検証した14候補は「『AIらしさ』の代理指標であり『文章の読みにくさ』の
#     直接的な代理指標にはなっていない」。
#
#     したがってこのレーンの採否基準は弁別力ではなく、「指摘に従って直した文が、
#     原文より読みやすくなるか」に置く。その基準での校正が済むまでは opt-in
#     （--reading-load）に留め、既存の findings / stats / baseline には混ぜない。
#     混ぜた瞬間に「AI臭さの採点」と「読みやすさの推敲」という別目的の指標が
#     同じスコアに合算され、どちらの判断にも使いにくくなる。
#
# このレーンが存在する理由（検出器を足すかどうかの判断基準）:
#     lint.py 本体が機械検出を要求するのは「AI は自分の AI 臭さを認識できない」からである。
#     しかし読解負荷は AI に見える。142字の文は、読めば長いと分かる。
#     ではなぜ検出器が要るのか——**網羅性**のためである。15,000字の文書を読む AI は、
#     11本ある長文のうち何本かには気づくが、全部には気づかない。機械なら全部を決定的に拾う。
#
#     したがって、このレーンに検出器を足してよいのは「AI が読み流すと見落とすもの」だけ。
#     読めば確実に気づくものに検出器を足しても、指摘が増えるだけで判断は良くならない。
#     この基準により、接続助詞「が」の連鎖を指す doubled_conjunctive_ga は削除した
#     （AI生成9,889文で1件・人間執筆379文で0件。見落とし以前に、そもそも起きていない）。
#
# 各検出器の直し方は SKILL.md §5「読みやすさの点検」と HINTS に書いてある。
# 閾値は当面 textlint-rule-preset-ja-technical-writing の既定値に合わせた暫定値で、
# 上記の基準で校正して調整する。
# ---------------------------------------------------------------------------
READING_LOAD_SENTENCE_MAX_CHARS = 90  # B1: これを超える文を指さす


# F1: 読点区切りの名詞句がこの個数以上連続し、かつ文がこの長さ以上なら埋もれた列挙とみなす。
# 当初は「読点が4個以上（B4）」で実装したが、artifactshare コーパス241本の校正で
# 62% の文書が発火し、しかも中身はほぼ全部が同格の列挙だった（「一覧、件数、絞り込み、
# アクセス判定では〜」など）。読点の打ち方の問題ではなく列挙の構造化の問題なので、
# カタログ B4 ではなく F1 を指す検出器に置き換えた。
READING_LOAD_BURIED_LIST_MIN_ITEMS = 3


READING_LOAD_BURIED_LIST_MIN_CHARS = 50


# 同じ校正で、項目3個の指摘は精度が落ちた（括弧の中だけの列挙や、並列の条件節を
# 列挙と誤認する例が混ざる。4個以上はほぼ全件が真の列挙だった）。3個のときだけ
# 対象をより長い文に絞る。短い3項目は箇条書きにするまでもないことが多い。
READING_LOAD_BURIED_LIST_3ITEM_MIN_CHARS = 80


READING_LOAD_KANJI_RUN_MAX = 6  # C1: 連続漢字がこれを超える（7字以上）


READING_LOAD_NO_CHAIN_MIN = 3  # C2: 格助詞「の」がこの回数以上連鎖する


# A1/A2: 2つの否定形態素がこの距離以内に並ぶと二重否定の候補とみなす。
# 「招かないとは言えません」（招か/ない/と/は/言え/ませ/ん = 距離5）まで拾える値。
READING_LOAD_NEGATION_MAX_GAP = 6


READING_LOAD_CATEGORIES: set[str] = {
    "sentence_too_long",
    "buried_list",
    "kanji_run",
    "double_negative",
    "no_chain",
    "sentence_in_paren",
}


_KANJI_RUN_RE = re.compile(rf"[一-鿿々]{{{READING_LOAD_KANJI_RUN_MAX + 1},}}")


# 否定を表す形態素。sudachi は形容詞の「ない」を「無い」に、助動詞の「ん」（「言えません」の
# 「ん」）を「ず」に正規化するため、表層ではなく正規化形で判定する。
# 「ぬ」（「知らぬ」）も同系統だが正規化形は「ぬ」のまま出るので両方持つ。
_NEGATION_NORMALIZED = {"ない", "無い", "ぬ", "ず"}


_NEGATION_POS = {"助動詞", "形容詞"}


_WHITESPACE_RUN_RE = re.compile(r"\s{2,}")


def _reading_length(text: str) -> int:
    """読み手が実際に読む文字数の近似を返す。

    mask_markdown_structure() は Markdown リンクの URL 部分とインラインコード
    スパンを「同じ文字数の空白」に置換して行内オフセットを保つ。その空白は
    読み手の目には映らないので、素の len() で数えると URL の長い文ほど不当に
    長く見積もられる（実測 50字ほどの文が 90字超と判定された）。
    2文字以上続く空白を1文字に畳んでから数えることで、URL・コードスパンの
    見かけの長さを取り除く。英単語のあいだの単独スペースは読む対象なので残す。
    """
    return len(_WHITESPACE_RUN_RE.sub(" ", text).strip())


def _span_contains_proper_noun(morphemes: list, start: int, end: int) -> bool:
    """文字オフセット [start, end) に重なる形態素に固有名詞が含まれるか。

    sudachi の Morpheme.begin()/end() は解析対象文字列上のオフセットを返すので、
    同じ文字列に対する正規表現マッチの位置とそのまま突き合わせられる。
    """
    for m in morphemes:
        if m.end() > start and m.begin() < end and m.part_of_speech()[1] == "固有名詞":
            return True
    return False


def _is_negation(morpheme) -> bool:
    return (
        morpheme.part_of_speech()[0] in _NEGATION_POS
        and morpheme.normalized_form() in _NEGATION_NORMALIZED
    )


# 形の上では否定が二重に掛かるが、義務・必然を表す語彙化した定型で、読み手が
# 符号の反転を計算することはない表現。実測（音楽レーベル記事の「同じ顔を保たないと
# いけません」）で誤検知したため除外する。二重否定の litotes（「ないわけではない」
# 「ないとは言えない」）はこれらの部分文字列を含まないので取りこぼさない。
_OBLIGATION_SPANS = (
    "といけ",
    "とだめ",
    "とダメ",
    "ばならな",
    "ばなりま",
    "ばいけな",
    "てはならな",
    "てはなりま",
    "てはいけな",
    "ざるを得",
    "ざるをえ",
)


def _is_obligation_form(span: str) -> bool:
    return any(s in span for s in _OBLIGATION_SPANS)


# 「〜ないと動かない」「〜なければ意味がない」のような、条件節の否定と帰結の否定が
# 並ぶ形。形の上では否定が2つあるが、日本語で必要条件を述べる標準的な言い方であり、
# 読み手が符号の反転を計算することはない。artifactshare コーパス241本の校正で、
# double_negative の誤検知のうち最大の塊がこの形だった。
# 「〜ないとは言えない」（真の litotes）は「と」の直後に「は」が来るので除外しない。
_CONDITIONAL_NEGATION_RE = re.compile(r"^(?:ない|なけれ|なく)(?:と(?!は)|ば|ければ)")


def _is_conditional_negation(span: str) -> bool:
    return bool(_CONDITIONAL_NEGATION_RE.match(span))


_OPEN_PARENS = ("（", "(", "「", "『", "【", "［", "[")


_CLOSE_PARENS = ("）", ")", "」", "』", "】", "］", "]")


def _segment_ends_with_noun(segment: list) -> bool:
    """読点で区切られた1区画が名詞で終わる（＝述語を持たない名詞句）かを判定する。

    末尾の補助記号を落とすだけでは「確認ポイント（どのアプリが前面に出るか）」のような
    括弧付きの項目を取りこぼすため、末尾の括弧グループごと遡ってから品詞を見る。
    """
    i = len(segment)
    while i > 0:
        m = segment[i - 1]
        if m.part_of_speech()[0] not in TRAILING_SYMBOL_POS:
            break
        if m.surface() in _CLOSE_PARENS:
            depth = 1
            j = i - 1
            while j > 0 and depth:
                j -= 1
                s = segment[j].surface()
                if s in _CLOSE_PARENS:
                    depth += 1
                elif s in _OPEN_PARENS:
                    depth -= 1
            i = j
        else:
            i -= 1
    return i > 0 and segment[i - 1].part_of_speech()[0] == "名詞"


def _longest_noun_phrase_run(morphemes: list) -> tuple[int, int, int] | None:
    """読点区切りの区画のうち、名詞で終わる区画が連続する最長の並びを返す。

    戻り値は (開始形態素index, 終了形態素index, 区画数)。
    READING_LOAD_BURIED_LIST_MIN_ITEMS 個に満たなければ None。
    """
    bounds: list[tuple[int, int]] = []
    start = 0
    for i, m in enumerate(morphemes):
        if m.surface() == "、":
            bounds.append((start, i))
            start = i + 1
    bounds.append((start, len(morphemes)))

    # 列挙の最後の項目は述語に溶けるのが普通なので（「A、B、C を行います」の C）、
    # 裸の名詞句で終わる区画は項目数より1つ少なく数えられる。連続する名詞句区画が
    # (MIN_ITEMS - 1) 個あり、そのあとに区画が続いていれば、その続きを最後の項目
    # とみなして列挙と判定する。
    need = READING_LOAD_BURIED_LIST_MIN_ITEMS - 1
    best: tuple[int, int, int] | None = None
    run: list[tuple[int, int]] = []
    for idx, (s, e) in enumerate(bounds):
        if e > s and _segment_ends_with_noun(morphemes[s:e]):
            run.append((s, e))
        else:
            run = []
        has_tail = idx + 1 < len(bounds)
        if len(run) >= need and has_tail:
            items = len(run) + 1
            if best is None or items > best[2]:
                best = (run[0][0], bounds[idx + 1][1], items)
    return best


def _has_punctuation_between(morphemes: list, i: int, j: int) -> bool:
    """morphemes[i] と morphemes[j] のあいだに読点などの補助記号があるか。

    「行かないし、来ない」のように、読点をまたいで別々の節がそれぞれ否定されている
    ケースを二重否定（「〜ないわけではない」）と誤認しないためのガード。
    """
    return any(m.part_of_speech()[0] == "補助記号" for m in morphemes[i + 1 : j])


def detect_reading_load(
    tokenized: list[TokenizedSentence],
    sentence_max_chars: int = READING_LOAD_SENTENCE_MAX_CHARS,
) -> list[Finding]:
    """読解負荷の高い箇所を指さす（判定もスコアも出さない）。

    直し方は SKILL.md §5「読みやすさの点検」と HINTS。
    """
    findings: list[Finding] = []
    for ts in tokenized:
        text = ts.text
        excerpt = (ts.raw_text or text).strip()[:40]

        # --- B1: 一文が長すぎる ---
        reading_len = _reading_length(text)
        if reading_len > sentence_max_chars:
            findings.append(
                Finding(
                    line=ts.line,
                    category="sentence_too_long",
                    excerpt=excerpt,
                    severity="info",
                    detail=(
                        f"一文が{reading_len}字（目安{sentence_max_chars}字）。"
                        "一文に主張が二つ以上入っていないかを確かめる"
                    ),
                )
            )


        # --- C1: 連続漢字 ---
        for m in _KANJI_RUN_RE.finditer(text):
            # 固有名詞を含む連なりは除外する（「東京地方裁判所」「特定商取引法表示」など）。
            # 分解できない名前であって、書き手が直せる読みにくさではない。
            # 241本の校正では、拾いたい側（「初回課金転換率」「視覚回帰受領証」のような
            # AI が作る圧縮漢語）はいずれも普通名詞だけで構成されていた。
            if _span_contains_proper_noun(ts.morphemes, m.start(), m.end()):
                continue
            findings.append(
                Finding(
                    line=ts.line,
                    category="kanji_run",
                    excerpt=m.group(0),
                    severity="info",
                    detail=(
                        f"漢字が{len(m.group(0))}字連続（目安{READING_LOAD_KANJI_RUN_MAX}字）。"
                        "語の切れ目が読み取りにくい疑い"
                    ),
                )
            )

        morphemes = ts.morphemes

        # --- F1: 埋もれた列挙 ---
        run = _longest_noun_phrase_run(morphemes)
        if run is not None:
            start, end, items = run
            min_chars = (
                READING_LOAD_BURIED_LIST_3ITEM_MIN_CHARS
                if items <= 3
                else READING_LOAD_BURIED_LIST_MIN_CHARS
            )
        if run is not None and reading_len >= min_chars:
            findings.append(
                Finding(
                    line=ts.line,
                    category="buried_list",
                    excerpt="".join(m.surface() for m in morphemes[start:end])[:40],
                    severity="info",
                    detail=(
                        f"同格の名詞句が読点で{items}個並んでいる（一文{reading_len}字）。"
                        "並んだ項目を読み手が頭の中で組み立て直すことになる"
                    ),
                )
            )

        # --- A1/A2: 二重否定・否定の入れ子 ---
        negation_idx = [i for i, m in enumerate(morphemes) if _is_negation(m)]
        for a, b in zip(negation_idx, negation_idx[1:]):
            span = "".join(m.surface() for m in morphemes[a : b + 1])
            if (
                b - a <= READING_LOAD_NEGATION_MAX_GAP
                and not _has_punctuation_between(morphemes, a, b)
                and not _is_obligation_form(span)
                and not _is_conditional_negation(span)
            ):
                findings.append(
                    Finding(
                        line=ts.line,
                        category="double_negative",
                        excerpt=span,
                        severity="info",
                        detail=(
                            "否定が二重に掛かっている疑い"
                        ),
                    )
                )
                break

        # --- C2: 「の」の連鎖 ---
        no_idx = [
            i
            for i, m in enumerate(morphemes)
            if m.surface() == "の" and m.part_of_speech()[:2] == ("助詞", "格助詞")
        ]
        for k in range(len(no_idx) - READING_LOAD_NO_CHAIN_MIN + 1):
            window = no_idx[k : k + READING_LOAD_NO_CHAIN_MIN]
            gaps_ok = all(y - x <= 3 for x, y in zip(window, window[1:]))
            if gaps_ok and not _has_punctuation_between(morphemes, window[0], window[-1]):
                findings.append(
                    Finding(
                        line=ts.line,
                        category="no_chain",
                        excerpt="".join(m.surface() for m in morphemes[window[0] : window[-1] + 1]),
                        severity="info",
                        detail=(
                            f"格助詞「の」が{READING_LOAD_NO_CHAIN_MIN}つ以上続いている。係り受けが分かりにくい疑い"
                        ),
                    )
                )
                break

    findings.sort(key=lambda f: f.line)
    attach_hints(findings)
    return findings


# 括弧の中に文が入っているか。括弧の中の「」『』は引用なので先に外し、残りに句点が
# あるかを見る。末尾の句点だけ(「(〜です。)」)も文として扱う。
# 2026-10 の実測(人の文章 245 本、Opus 5.5 の仕事の文書 40 本)では、人の文章でも1割前後の
# 文書に1件は出る(余談の括弧、エッセイ)。文書単位の多用の判定に使うほどの差はないので、
# AI らしさのレーンには入れず、ここで1件ずつ見る箇所として示す。
_PAREN_RE = re.compile(r"[（(]([^（()）\n]{2,200})[)）]")


_PAREN_QUOTE_RE = re.compile(r"「[^「」]*」|『[^『』]*』")


_JA_CHAR_RE = re.compile(r"[ぁ-んァ-ヶ一-鿿]")


def detect_sentence_in_paren(raw_text: str) -> list[Finding]:
    """括弧の中に文が入っている箇所を指さす。

    文分割は句点で切るので括弧の中の文を割ってしまう。そのため文単位ではなく行単位で見る。
    箇条書きの項目は対象に含め、コードブロック・表・引用・インラインコードは除く。
    """
    findings: list[Finding] = []
    in_fence = False
    for no, line in iter_lines_with_no(mask_html_comments(raw_text)):
        if _CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        stripped = line.lstrip()
        if in_fence or stripped.startswith(("|", ">")) or line.startswith("    "):
            continue
        for m in _PAREN_RE.finditer(_blank_inline_code_spans(line)):
            inner = _PAREN_QUOTE_RE.sub("", m.group(1))
            if "。" not in inner or not _JA_CHAR_RE.search(inner):
                continue
            findings.append(
                Finding(
                    line=no,
                    category="sentence_in_paren",
                    excerpt=line[m.start() : m.end()][:60],
                    severity="info",
                    detail="括弧の中に文が入っている。括弧の中は読み飛ばされやすい",
                )
            )
    return findings
