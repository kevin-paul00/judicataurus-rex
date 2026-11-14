from judicataurus_rex.text import html_to_blocks, section
from tests.conftest import fixture_text


def test_skips_script_style_and_screenreader_text() -> None:
    html = (
        "<html><head><style>p{}</style><script>evil()</script></head><body>"
        '<p><span aria-hidden="true">§ 67.</span><span class="sr-only">Paragraph 67,</span></p>'
        "<p>Text <b>fett</b>&nbsp;weiter</p></body></html>"
    )
    blocks = html_to_blocks(html)
    assert [b.text for b in blocks] == ["§ 67.", "Text fett weiter"]


def test_numbering_is_joined_with_following_block() -> None:
    html = "<ol><li><div>1.</div><div>Leistung eines Zivildienstes oder</div></li></ol>"
    blocks = html_to_blocks(html)
    assert [b.text for b in blocks] == ["1. Leistung eines Zivildienstes oder"]
    assert blocks[0].level == 1


def test_ris_paragraph_text_and_remarks() -> None:
    blocks = html_to_blocks(fixture_text("NOR40232360.html"))
    text = section(blocks, "Text")
    assert text is not None
    texts = [b.text for b in text]
    assert texts[0] == "Beurlaubung"
    assert "§ 67." in texts
    assert any(t.startswith("(1) Studierende sind auf Antrag") for t in texts)
    assert any(t.startswith("1. Leistung eines Präsenz-") for t in texts)
    assert not any("Paragraph 67" in t for t in texts)  # sr-only verworfen

    remarks = section(blocks, "Beachte")
    assert remarks is not None
    assert "Studienjahr 2022/23" in remarks[0].text


def test_missing_section_is_none() -> None:
    assert section(html_to_blocks("<h1>A</h1><p>x</p>"), "Text") is None
