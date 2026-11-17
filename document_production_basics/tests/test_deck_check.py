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
