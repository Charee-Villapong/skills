#!/usr/bin/env python3
"""pptx の当たり前チェック：全スライドのキッカー／タイトル一覧と、版同士の差分。

標準ライブラリのみで動く（zip + XML パース）。

使い方:
  deck_check.py FILE.pptx            タイトル一覧＋flag（タイトルなし／重複）
  deck_check.py --diff OLD.pptx NEW.pptx   テキストが変わったスライド番号

flag が1つでもあれば終了コード1。
"""

import re
import sys
import xml.etree.ElementTree as ET
import zipfile

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
TOP_AREA_EMU = 3_200_000  # スライド上部（タイトル帯）とみなす y の上限
TITLE_MIN_SZ = 2000  # タイトルとみなす最小フォントサイズ（1/100 pt）


def parse_slide(xml_text):
    """スライド XML からテキスト図形の (y, 最大フォントサイズ, テキスト) を返す。"""
    root = ET.fromstring(xml_text)
    shapes = []
    for sp in root.iter("{%s}sp" % NS["p"]):
        texts = [t.text or "" for t in sp.iter("{%s}t" % NS["a"])]
        text = "".join(texts).strip()
        if not text:
            continue
        off = sp.find(".//a:xfrm/a:off", NS)
        y = int(off.get("y", "0")) if off is not None else 0
        sizes = []
        for rpr in sp.iter("{%s}rPr" % NS["a"]):
            if rpr.get("sz"):
                sizes.append(int(rpr.get("sz")))
        shapes.append({"y": y, "max_sz": max(sizes) if sizes else 0, "text": text})
    return shapes


def pick_kicker_title(shapes):
    """上部帯の図形から (キッカー, タイトル) を推定する。

    タイトル = 上部帯で最も大きいフォントの図形。キッカー = タイトルより上にある
    最も y の小さい図形。タイトル帯が無いスライド（扉など）は、スライド全体で
    最も大きいフォントの図形をタイトル扱いにする。
    """
    top = [s for s in shapes if s["y"] < TOP_AREA_EMU]
    pool = top if top else shapes
    if not pool:
        return "", ""
    title = max(pool, key=lambda s: s["max_sz"])
    above = [s for s in pool if s is not title and s["y"] <= title["y"]]
    kicker = min(above, key=lambda s: s["y"])["text"] if above else ""
    return kicker, title["text"]


def slide_xmls(pptx_path):
    """スライド XML を番号順に返す（slideN.xml の N 順）。"""
    with zipfile.ZipFile(pptx_path) as z:
        names = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        names.sort(key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        return [z.read(n).decode("utf-8") for n in names]


def slide_texts(pptx_path):
    return [
        "".join(s["text"] for s in parse_slide(xml)) for xml in slide_xmls(pptx_path)
    ]


def analyze(pptx_path):
    """スライドごとに {no, kicker, title, flags} を返す。"""
    rows = []
    seen_titles = {}
    for i, xml in enumerate(slide_xmls(pptx_path), 1):
        shapes = parse_slide(xml)
        kicker, title = pick_kicker_title(shapes)
        flags = []
        if not title or max((s["max_sz"] for s in shapes), default=0) < TITLE_MIN_SZ:
            flags.append("NO_TITLE")
        elif title in seen_titles:
            flags.append("DUP_TITLE(first=%d)" % seen_titles[title])
        else:
            seen_titles[title] = i
        rows.append({"no": i, "kicker": kicker, "title": title, "flags": flags})
    return rows


def diff(old_path, new_path):
    """テキストが変わったスライド番号（1始まり）のリストを返す。"""
    old, new = slide_texts(old_path), slide_texts(new_path)
    changed = []
    for i in range(max(len(old), len(new))):
        o = old[i] if i < len(old) else None
        n = new[i] if i < len(new) else None
        if o != n:
            changed.append(i + 1)
    return changed


def main(argv):
    if len(argv) == 4 and argv[1] == "--diff":
        changed = diff(argv[2], argv[3])
        print("changed slides:", changed if changed else "none")
        return 0
    if len(argv) == 2:
        rows = analyze(argv[1])
        bad = 0
        for r in rows:
            flag = ("  <-- " + ",".join(r["flags"])) if r["flags"] else ""
            bad += bool(r["flags"])
            print("%2d | %s | %s%s" % (r["no"], r["kicker"], r["title"], flag))
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
