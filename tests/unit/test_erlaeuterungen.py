import pytest

from judicataurus_rex.parlament.erlaeuterungen import (
    extract_sections,
    justification_part,
    paragraph_numbers,
)
from judicataurus_rex.ris.laws import lookup
from judicataurus_rex.text import Block, html_to_blocks
from tests.conftest import fixture_text


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("§ 67 Abs. 1 Z 6", {"67"}),
        ("§ 2 Z 9 und § 3 Z 9", {"2", "3"}),
        ("§§ 66 bis 68", {"66", "67", "68"}),
        ("§ 72a, § 76a, § 78", {"72a", "76a", "78"}),
        ("§ 67 Abs. 1 und 2", {"67"}),
        ("Art. 10 B-VG", set[str]()),
    ],
)
def test_paragraph_numbers(reference: str, expected: set[str]) -> None:
    assert paragraph_numbers(reference) == expected


def test_sections_for_ug_67_only_from_ug_article() -> None:
    law = lookup("UG")
    assert law is not None
    blocks = html_to_blocks(fixture_text("erlaeuterungen_662_auszug.html"))
    sections = extract_sections(blocks, law, "67")
    headings = [s.heading for s in sections]
    assert headings == [
        "Zu Z 103 (§ 67 Abs. 1 Z 6)",
        "Zu Z 104 (§ 67 Abs. 2)",
        "Zu Z 106 bis 108 (§§ 66 bis 68)",
    ]
    # Zwischenüberschriften innerhalb eines Abschnitts gehören zum Inhalt.
    assert "Es handelt sich dabei um folgende Bestimmungen:" in sections[0].paragraphs
    # § 67 des Hochschulgesetzes (Artikel 3) und § 67a fehlen.
    joined = " ".join(p for s in sections for p in s.paragraphs)
    assert "Erweiterungsstudien" not in joined
    assert "§ 67a" not in joined


def test_sections_matched_by_genitive_full_title() -> None:
    law = lookup("HSG 2014")
    assert law is not None
    blocks = html_to_blocks(fixture_text("erlaeuterungen_662_auszug.html"))
    sections = extract_sections(blocks, law, "67")
    assert [s.heading for s in sections] == ["Zu Z 1 (§ 67)"]


def test_no_article_structure_searches_whole_document() -> None:
    law = lookup("UG")
    assert law is not None
    html = "<p>Zu § 67:</p><p>Inhalt.</p><p>Zu § 68:</p><p>Anderes.</p>"
    sections = extract_sections(html_to_blocks(html), law, "67")
    assert [(s.heading, s.paragraphs) for s in sections] == [("Zu § 67", ("Inhalt.",))]


def _motion_blocks() -> list[Block]:
    return justification_part(html_to_blocks(fixture_text("initiativantrag_2235_auszug.html")))


def test_justification_part_skips_statute_text() -> None:
    blocks = _motion_blocks()
    assert blocks[0].text == "Allgemeiner Teil"
    # Der Gesetzestext vor der Begründung (mit „§ 55.“) ist nicht mehr dabei.
    assert all(b.text != "§ 55." for b in blocks)


def test_justification_part_without_heading_keeps_everything() -> None:
    blocks = html_to_blocks("<p>Zu § 67:</p><p>Inhalt.</p>")
    assert justification_part(blocks) == blocks


def test_sections_from_initiative_motion() -> None:
    law = lookup("UG")
    assert law is not None
    sections = extract_sections(_motion_blocks(), law, "55")
    assert [s.heading for s in sections] == ["Zu Z 15 (§ 55)"]
    assert sections[0].paragraphs[0].startswith("Die geltende Rechtslage wird grundsätzlich")


def test_motion_article_heading_in_parentheses_ends_ug_article() -> None:
    """„Zu den Änderungen des Fachhochschul-Studiengesetzes (Artikel 6):“ beendet Artikel 5."""
    law = lookup("UG")
    assert law is not None
    # § 5 gibt es im Antrag nur im HG (Artikel 1) und im FHStG (Artikel 6), nicht im UG.
    assert extract_sections(_motion_blocks(), law, "5") == []
