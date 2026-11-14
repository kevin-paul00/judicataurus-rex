"""Die zu einem Paragraphen passenden Abschnitte aus den Erläuterungen herauslösen.

Aufbau der Erläuterungen zu einer Regierungsvorlage (Beispiel RV 662 d.B. XXVII. GP):

* „Allgemeiner Teil“, danach „Besonderer Teil“
* bei Sammelnovellen je Gesetz ein Artikel, z. B. „Artikel 1“ mit dem Zusatz
  „Änderung des UG“ (im Original durch einen Gedankenstrich getrennt)
* darin je Novellierungsanordnung ein Abschnitt: „Zu Z 104 (§ 67 Abs. 2):“, manchmal
  auch ohne „Zu“ („Z 21 (§ 35 Z 30):“) oder als „Zu § 67:“

Ohne Artikelgliederung (Novelle nur eines Gesetzes) wird das ganze Dokument durchsucht.

Bei einem Initiativantrag gibt es kein eigenes Dokument mit Erläuterungen: Der Antrag
enthält zuerst den Gesetzestext und danach unter „Begründung“ die Erläuterungen, gegliedert
wie bei einer Regierungsvorlage. Dort kommen Artikelüberschriften auch in der Form
„Zu den Änderungen des Fachhochschul-Studiengesetzes (Artikel 6):“ vor.
"""

import re
from dataclasses import dataclass

from judicataurus_rex.ris.laws import LawAliases
from judicataurus_rex.text import Block

_ARTICLE_HEADING = re.compile(
    r"^(?:(?:Zu\s+)?Artikel\s+\d+[a-z]?\b|Zu\s+den\s+Änderungen\b.*\(Artikel\s+\d+[a-z]?\)\s*:?$)",
    re.IGNORECASE,
)
_JUSTIFICATION_HEADING = "begründung"
_SECTION_HEADING = re.compile(
    r"^(?:Zu\s+(?:den\s+)?(?:Z(?:iffer)?n?\s*\d|§)|Z\s*\d+[a-z]?(?:\s*(?:,|und|bis)\s*\d+[a-z]?)*\s*\()",
    re.IGNORECASE,
)
_MAX_HEADING_LENGTH = 300
_TOKEN = re.compile(
    r"§§?|Abs\.?|Z\b|Ziffer|lit\.?|Nr\.?|Art\.?|Satz|bis|\d+[a-z]?\b", re.IGNORECASE
)
_SUB_MARKERS = frozenset({"abs", "z", "ziffer", "lit", "nr", "art", "satz"})


@dataclass(frozen=True, slots=True)
class ExplanationSection:
    heading: str
    paragraphs: tuple[str, ...]


def _is_section_heading(block: Block) -> bool:
    text = block.text
    return (
        len(text) <= _MAX_HEADING_LENGTH
        and text.rstrip().endswith(":")
        and _SECTION_HEADING.match(text) is not None
    )


def _is_article_heading(block: Block) -> bool:
    return len(block.text) <= _MAX_HEADING_LENGTH and _ARTICLE_HEADING.match(block.text) is not None


def _law_key(text: str) -> str:
    """Vergleichsschlüssel: Kleinschreibung, Genitiv („Gesetzes“) → „Gesetz“."""
    key = " ".join(text.split()).casefold()
    return re.sub(r"(gesetz)(?:es|s)\b", r"\1", key)


def _mentions_law(heading: str, law: LawAliases) -> bool:
    key = _law_key(heading)
    for name in (law.full_title, *law.names, *law.all_citations):
        pattern = r"(?<![\w-])" + re.escape(_law_key(name)) + r"(?![\w-])"
        if re.search(pattern, key) is not None:
            return True
    return False


def _number_value(token: str) -> int | None:
    digits = re.match(r"\d+", token)
    return int(digits.group(0)) if digits else None


def paragraph_numbers(reference: str) -> set[str]:
    """Paragraphennummern in einer Fundstelle wie „§ 2 Z 9 und § 3“ oder „§§ 66 bis 68“.

    Nummern nach „Abs.“, „Z“, „lit.“ usw. sind Untergliederungen und zählen nicht.
    Bei „bis“ zwischen zwei Paragraphen werden die Nummern dazwischen ergänzt.
    """
    found: list[str] = []
    marker: str | None = None
    pending_range_from: str | None = None
    for raw in _TOKEN.findall(reference):
        token = raw.casefold().rstrip(".")
        if token.startswith("§"):
            marker = "para"
        elif token in _SUB_MARKERS:
            marker = "sub"
        elif token == "bis":
            if marker == "para" and found:
                pending_range_from = found[-1]
        elif marker == "para":
            if pending_range_from is not None:
                start, end = _number_value(pending_range_from), _number_value(token)
                if start is not None and end is not None and start < end:
                    found.extend(str(n) for n in range(start + 1, end))
                pending_range_from = None
            found.append(token)
    return set(found)


def _reference(heading: str) -> str:
    inner = re.search(r"\((.*)\)", heading)
    return inner.group(1) if inner else heading


def _article_blocks(blocks: list[Block], law: LawAliases) -> list[Block]:
    """Die Blöcke des Artikels, der ``law`` ändert; ohne Artikelgliederung alle."""
    articles = [i for i, b in enumerate(blocks) if _is_article_heading(b)]
    if not articles:
        return blocks
    selected: list[Block] = []
    for position, start in enumerate(articles):
        end = articles[position + 1] if position + 1 < len(articles) else len(blocks)
        if _mentions_law(blocks[start].text, law):
            selected.extend(blocks[start + 1 : end])
    return selected


def justification_part(blocks: list[Block]) -> list[Block]:
    """Die Blöcke nach der Überschrift „Begründung“ eines Antrags; ohne sie alle Blöcke."""
    for index, block in enumerate(blocks):
        if block.text.strip().rstrip(":").casefold() == _JUSTIFICATION_HEADING:
            return blocks[index + 1 :]
    return blocks


def extract_sections(
    blocks: list[Block], law: LawAliases, paragraph: str
) -> list[ExplanationSection]:
    """Abschnitte der Erläuterungen, die ``§ paragraph`` von ``law`` betreffen."""
    wanted = paragraph.strip().casefold()
    candidates = _article_blocks(blocks, law)
    sections: list[ExplanationSection] = []
    current_heading: str | None = None
    current: list[str] = []

    def finish() -> None:
        if current_heading is not None:
            sections.append(ExplanationSection(current_heading, tuple(current)))

    for block in candidates:
        if _is_section_heading(block) or _is_article_heading(block):
            finish()
            current.clear()
            matches = wanted in paragraph_numbers(_reference(block.text))
            current_heading = block.text.rstrip(" :") if matches else None
            continue
        if current_heading is not None:
            current.append(block.text)
    finish()
    return sections
