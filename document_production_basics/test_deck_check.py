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
