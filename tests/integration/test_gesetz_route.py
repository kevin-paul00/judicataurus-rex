from datetime import date

import httpx
import pytest

from judicataurus_rex.config import Settings
from judicataurus_rex.parlament.client import ParlamentClient
from judicataurus_rex.ris.client import RateLimiter, RisClient
from judicataurus_rex.web.app import create_app
from judicataurus_rex.web.routes import statute_link
from tests.conftest import Handler, fake_upstream


def _client(handler: Handler) -> httpx.AsyncClient:
    settings = Settings()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ris = RisClient(settings, http=http, limiter=RateLimiter(0.0))
    parlament = ParlamentClient(
        settings,
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        limiter=RateLimiter(0.0),
    )
    app = create_app(settings, client=ris, parlament_client=parlament)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_ug_67_shows_versions_text_and_explanations(upstream: Handler) -> None:
    client = _client(upstream)
    async with client:
        response = await client.get("/gesetz", params={"norm": "UG § 67"})
    assert response.status_code == 200
    html = response.text
    assert html.count('href="/gesetz?norm=') >= 7  # alle Fassungen verlinkt
    assert "geändert durch BGBl. I Nr. 93/2021" in html
    assert "Studierende sind auf Antrag" in html
    assert "662 d.B." in html
    assert "89. Sitzung des Nationalrats am 24.03.2021" in html
    assert "Zu Z 104 (§ 67 Abs. 2)" in html
    assert "Erweiterungsstudien" not in html  # § 67 eines anderen Gesetzes
    assert "<script>alert" not in html


async def test_without_government_bill_uses_initiative_motion(upstream: Handler) -> None:
    """UG § 55 idF BGBl. I Nr. 129/2017 beruht auf dem Initiativantrag 2235/A (XXV. GP)."""
    client = _client(upstream)
    async with client:
        response = await client.get("/gesetz", params={"norm": "UG § 55"})
    assert response.status_code == 200
    html = response.text
    assert "geändert durch BGBl. I Nr. 129/2017" in html
    assert "<dt>Initiativantrag</dt>" in html
    assert "https://www.parlament.gv.at/gegenstand/XXV/A/2235" in html
    assert "Antrag mit Begründung" in html
    assert "Zu Z 15 (§ 55)" in html
    assert "Die geltende Rechtslage wird grundsätzlich übernommen" in html
    assert "Initiativantrag 2235/A (XXV. GP), Begründung" in html
    assert "keine Regierungsvorlage zugrunde" not in html
    assert "Ausschussbericht 1705 d.B. (XXV. GP)" in html


async def test_parliament_error_is_a_notice_not_a_500() -> None:
    client = _client(fake_upstream(parlament_status=503))
    async with client:
        response = await client.get("/gesetz", params={"norm": "UG § 67"})
    assert response.status_code == 200
    assert "Materialien des Parlaments konnten nicht geladen werden" in response.text
    assert "Studierende sind auf Antrag" in response.text


async def test_unknown_law_and_bad_input(upstream: Handler) -> None:
    client = _client(upstream)
    async with client:
        unknown = await client.get("/gesetz", params={"norm": "ABGB § 1"})
        no_paragraph = await client.get("/gesetz", params={"norm": "UG"})
        bad_version = await client.get("/gesetz", params={"norm": "UG § 67", "fassung": "../x"})
    assert "noch keine Gesetzesansicht hinterlegt" in unknown.text
    assert "Bitte einen Paragraphen angeben" in no_paragraph.text
    assert "Ungültige Fassung" in bad_version.text


@pytest.mark.parametrize(
    ("norm", "as_of", "expected"),
    [
        ("UG §67 Abs1", date(2024, 2, 15), "/gesetz?norm=UG+%C2%A7+67&stichtag=2024-02-15"),
        ("UniversitätsG 2002 §51 Abs2, §63 Abs1", None, "/gesetz?norm=UG+%C2%A7+51"),
        ("HSG 2014 §31", None, "/gesetz?norm=HSG+2014+%C2%A7+31"),
        ("B-VG Art133 Abs4", None, None),
        ("ZDG §14", None, None),
    ],
)
def test_statute_link(norm: str, as_of: date | None, expected: str | None) -> None:
    assert statute_link(norm, as_of) == expected
