import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from deck_check import parse_slide, pick_kicker_title  # noqa: E402

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def slide_xml(shapes):
    body = "".join(
        '<p:sp><p:spPr><a:xfrm><a:off x="0" y="%d"/></a:xfrm></p:spPr>'
        '<p:txBody><a:p><a:r><a:rPr sz="%d"/><a:t>%s</a:t></a:r></a:p></p:txBody></p:sp>'
        % (y, sz, text)
        for y, sz, text in shapes
    )
    return '<p:sld xmlns:p="%s" xmlns:a="%s"><p:cSld><p:spTree>%s</p:spTree></p:cSld></p:sld>' % (
        P,
        A,
        body,
    )


def test_parse_and_pick_title():
    xml = slide_xml([(100000, 1200, "関連する取り組み"), (300000, 2800, "ルールのコード化")])
    shapes = parse_slide(xml)
    assert len(shapes) == 2
    kicker, title = pick_kicker_title(shapes)
    assert kicker == "関連する取り組み"
    assert title == "ルールのコード化"


def test_no_title_sized_text():
    xml = slide_xml([(100000, 1200, "小さい文字だけ")])
    shapes = parse_slide(xml)
    assert max(s["max_sz"] for s in shapes) < 2000


def test_empty_slide():
    assert parse_slide(slide_xml([])) == []
    assert pick_kicker_title([]) == ("", "")


def test_slide_order_follows_presentation(tmp_path):
    """ファイル名の番号順ではなく presentation.xml の発表順に従うこと。"""
    import zipfile

    from deck_check import slide_texts

    path = tmp_path / "deck.pptx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "ppt/presentation.xml",
            '<p:presentation xmlns:p="%s" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<p:sldIdLst><p:sldId id="1" r:id="rId2"/><p:sldId id="2" r:id="rId1"/></p:sldIdLst></p:presentation>'
            % P,
        )
        z.writestr(
            "ppt/_rels/presentation.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="slides/slide1.xml"/>'
            '<Relationship Id="rId2" Target="slides/slide2.xml"/></Relationships>',
        )
        z.writestr("ppt/slides/slide1.xml", slide_xml([(100000, 2800, "二番目")]))
        z.writestr("ppt/slides/slide2.xml", slide_xml([(100000, 2800, "一番目")]))
    assert slide_texts(str(path)) == ["一番目", "二番目"]


def build_deck(path, titles):
    """各スライドのタイトル文言だけが違う pptx を作る。"""
    import zipfile

    sld_ids = "".join(
        '<p:sldId id="%d" r:id="rId%d"/>' % (i, i) for i in range(1, len(titles) + 1)
    )
    rels = "".join(
        '<Relationship Id="rId%d" Target="slides/slide%d.xml"/>' % (i, i)
        for i in range(1, len(titles) + 1)
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "ppt/presentation.xml",
            '<p:presentation xmlns:p="%s" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<p:sldIdLst>%s</p:sldIdLst></p:presentation>" % (P, sld_ids),
        )
        z.writestr(
            "ppt/_rels/presentation.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            "%s</Relationships>" % rels,
        )
        for i, title in enumerate(titles, 1):
            z.writestr(
                "ppt/slides/slide%d.xml" % i, slide_xml([(100000, 2800, title)])
            )


def test_main_exit_code_with_dup_title_only(tmp_path):
    """重複タイトルだけでも、docstring の仕様どおり終了コード1になること。"""
    from deck_check import main

    path = tmp_path / "deck.pptx"
    build_deck(path, ["同じタイトル", "同じタイトル"])
    assert main(["deck_check.py", str(path)]) == 1


def test_main_exit_code_with_no_title(tmp_path):
    from deck_check import main

    path = tmp_path / "deck.pptx"
    build_deck(path, ["タイトルあり", ""])
    assert main(["deck_check.py", str(path)]) == 1


def test_main_exit_code_clean_deck(tmp_path):
    from deck_check import main

    path = tmp_path / "deck.pptx"
    build_deck(path, ["タイトル1", "タイトル2"])
    assert main(["deck_check.py", str(path)]) == 0


def test_slide_order_with_target_before_id(tmp_path):
    """rels の属性が Target → Id の順で書かれていてもスライドを認識できること。"""
    import zipfile

    from deck_check import slide_texts

    path = tmp_path / "deck.pptx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "ppt/presentation.xml",
            '<p:presentation xmlns:p="%s" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<p:sldIdLst><p:sldId id="1" r:id="rId2"/><p:sldId id="2" r:id="rId1"/></p:sldIdLst></p:presentation>'
            % P,
        )
        z.writestr(
            "ppt/_rels/presentation.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="slides/slide1.xml" Id="rId1"/>'
            '<Relationship Target="slides/slide2.xml" Id="rId2"/></Relationships>',
        )
        z.writestr("ppt/slides/slide1.xml", slide_xml([(100000, 2800, "二番目")]))
        z.writestr("ppt/slides/slide2.xml", slide_xml([(100000, 2800, "一番目")]))
    assert slide_texts(str(path)) == ["一番目", "二番目"]
