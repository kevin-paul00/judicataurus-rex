"""Fremdes HTML (RIS, Parlament) in einfache Textblöcke umwandeln.

Die Oberfläche bettet nie fremdes HTML ein, sondern nur diese Blöcke. Jinja escaped sie
beim Ausgeben, Skripte und Stile werden schon hier verworfen.
"""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

type BlockKind = Literal["heading", "paragraph"]

_BLOCK_TAGS = frozenset(
    {"p", "div", "li", "tr", "td", "th", "table", "ol", "ul", "br", "blockquote", "section"}
)
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TAGS = frozenset({"script", "style", "head", "title", "noscript", "template"})
_VOID_TAGS = frozenset({"br", "img", "hr", "meta", "link", "input", "col", "wbr", "area", "base"})
_LIST_TAGS = frozenset({"ol", "ul"})
# Nur eine Nummerierung, z. B. "1.", "(2)", "a)"; wird mit dem folgenden Block verbunden.
_NUMBERING_ONLY = re.compile(r"^(?:\(\d+[a-z]?\)|\d+[a-z]?\.|[a-z]{1,2}\)|[-\u2013\u2022])$")


@dataclass(frozen=True, slots=True)
class Block:
    kind: BlockKind
    text: str
    level: int = 0  # Verschachtelungstiefe in Listen (für die Einrückung)
    rank: int = 0  # Überschriftenebene (h1 = 1); 0 bei Absätzen


def _clean(text: str) -> str:
    return " ".join(text.split())


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._buffer: list[str] = []
        self._heading_rank = 0
        self._list_depth = 0
        # Offene Elemente, deren Inhalt verworfen wird (script, sr-only …); Wert = Tag-Name.
        self._skip_stack: list[str] = []

    def _flush(self) -> None:
        text = _clean("".join(self._buffer))
        self._buffer.clear()
        if not text:
            return
        kind: BlockKind = "heading" if self._heading_rank else "paragraph"
        previous = self.blocks[-1] if self.blocks else None
        if previous is not None and _NUMBERING_ONLY.fullmatch(previous.text):
            self.blocks[-1] = Block(
                previous.kind, f"{previous.text} {text}", previous.level, previous.rank
            )
            return
        self.blocks.append(Block(kind, text, self._list_depth, self._heading_rank))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_stack:
            if tag not in _VOID_TAGS:
                self._skip_stack.append(tag)
            return
        classes = (dict(attrs).get("class") or "").split()
        if tag in _SKIP_TAGS or "sr-only" in classes:
            # Der verworfene Text trennte oft zwei Wörter, z. B. „(1)“ und „Studierende“.
            self._buffer.append(" ")
            if tag not in _VOID_TAGS:
                self._skip_stack.append(tag)
            return
        if tag in _HEADING_TAGS:
            self._flush()
            self._heading_rank = int(tag[1])
        elif tag in _BLOCK_TAGS:
            self._flush()
            if tag in _LIST_TAGS:
                self._list_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._skip_stack:
            # Nicht wohlgeformtes HTML: bis zum passenden Tag zurückgehen.
            if tag in self._skip_stack:
                while self._skip_stack and self._skip_stack.pop() != tag:
                    pass
            return
        if tag in _HEADING_TAGS:
            self._flush()
            self._heading_rank = 0
        elif tag in _BLOCK_TAGS:
            self._flush()
            if tag in _LIST_TAGS:
                self._list_depth = max(0, self._list_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self._skip_stack:
            self._buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def html_to_blocks(html: str) -> list[Block]:
    """HTML → Textblöcke (Überschriften und Absätze) in Dokumentreihenfolge."""
    parser = _Parser()
    parser.feed(html)
    parser.close()
    return parser.blocks


def section(blocks: list[Block], heading: str) -> list[Block] | None:
    """Die Blöcke unter der Überschrift ``heading`` bis zur nächsten gleich- oder höherrangigen.

    RIS-Dokumente gliedern Metadaten und Text mit ``<h1>``-Überschriften („Kurztitel“,
    „Beachte“, „Text“, „Schlagworte“ …). ``None``, wenn es die Überschrift nicht gibt.
    """
    start = next(
        (i for i, b in enumerate(blocks) if b.kind == "heading" and b.text == heading), None
    )
    if start is None:
        return None
    rank = blocks[start].rank
    result: list[Block] = []
    for block in blocks[start + 1 :]:
        if block.kind == "heading" and 0 < block.rank <= rank:
            break
        result.append(block)
    return result
