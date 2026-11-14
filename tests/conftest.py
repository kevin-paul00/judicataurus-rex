"""Gemeinsame pytest-Fixtures."""

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

RIS_API = "https://data.bka.gv.at/ris/api/v2.6"
PARLAMENT = "https://www.parlament.gv.at"
UG_67_HTML = "https://ogd.ris.bka.gv.at/Dokumente/Bundesnormen/NOR40232360/NOR40232360.html"
RV_662_EXPLANATIONS = f"{PARLAMENT}/dokument/XXVII/I/662/fnameorig_884977.html"
IA_2235_TEXT = f"{PARLAMENT}/dokument/XXV/A/2235/fnameorig_641352.html"
_EMPTY_RESULT = (
    b'{"OgdSearchResult":{"OgdDocumentResults":'
    b'{"Hits":{"@pageNumber":"1","@pageSize":"100","#text":"0"}}}}'
)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


type Handler = Callable[[httpx.Request], httpx.Response]


def fake_upstream(*, parlament_status: int = 200) -> Handler:
    """Antwortet wie RIS und Parlament, mit den gespeicherten Originalantworten."""

    def handle(request: httpx.Request) -> httpx.Response:
        url = request.url
        if str(url.copy_with(query=None)) == f"{RIS_API}/Bundesrecht":
            app = url.params.get("Applikation")
            if app == "BrKons" and url.params.get("Abschnitt.Von") == "67":
                return httpx.Response(200, content=fixture_bytes("brkons_ug_67.json"))
            if app == "BrKons" and url.params.get("Abschnitt.Von") == "55":
                return httpx.Response(200, content=fixture_bytes("brkons_ug_55.json"))
            if app == "BgblAuth" and url.params.get("Bgblnummer") == "93/2021":
                return httpx.Response(200, content=fixture_bytes("bgblauth_93_2021.json"))
            if app == "BgblAuth" and url.params.get("Bgblnummer") == "129/2017":
                return httpx.Response(200, content=fixture_bytes("bgblauth_129_2017.json"))
            return httpx.Response(200, content=_EMPTY_RESULT)
        if str(url) == UG_67_HTML:
            return httpx.Response(
                200,
                content=fixture_bytes("NOR40232360.html"),
                headers={"content-type": "text/html; charset=utf-8"},
            )
        if str(url.copy_with(query=None)) == f"{PARLAMENT}/gegenstand/XXVII/I/662":
            if parlament_status != 200:
                return httpx.Response(parlament_status)
            return httpx.Response(200, content=fixture_bytes("parlament_rv_662.json"))
        if str(url) == RV_662_EXPLANATIONS:
            return httpx.Response(
                200,
                content=fixture_bytes("erlaeuterungen_662_auszug.html"),
                headers={"content-type": "text/html; charset=utf-8"},
            )
        if str(url.copy_with(query=None)) == f"{PARLAMENT}/gegenstand/XXV/A/2235":
            if parlament_status != 200:
                return httpx.Response(parlament_status)
            return httpx.Response(200, content=fixture_bytes("parlament_ia_2235.json"))
        if str(url) == IA_2235_TEXT:
            return httpx.Response(
                200,
                content=fixture_bytes("initiativantrag_2235_auszug.html"),
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return httpx.Response(404)

    return handle


@pytest.fixture
def upstream() -> Handler:
    return fake_upstream()
