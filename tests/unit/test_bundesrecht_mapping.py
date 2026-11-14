from datetime import date

from judicataurus_rex.ris.mapping import to_bgbl_info, to_law_version
from judicataurus_rex.ris.raw_models import Envelope
from judicataurus_rex.statute import select_version
from tests.conftest import fixture_bytes


def test_law_versions_of_ug_67() -> None:
    envelope = Envelope.model_validate_json(fixture_bytes("brkons_ug_67.json"))
    assert envelope.body.results is not None
    versions = [v for r in envelope.body.results.references if (v := to_law_version(r))]
    assert len(versions) == 7
    first = min(versions, key=lambda v: v.valid_from or date.min)
    assert first.label == "§ 67"
    assert first.amending_bgbl is None
    assert first.source_bgbl == "BGBl. I Nr. 120/2002"
    current = next(v for v in versions if v.id == "NOR40232360")
    assert current.valid_from == date(2021, 5, 28)
    assert current.valid_to is None
    assert current.amending_bgbl == "BGBl. I Nr. 93/2021"
    assert current.html_url is not None and current.html_url.endswith("NOR40232360.html")


def test_bgbl_info_links_to_parliament() -> None:
    envelope = Envelope.model_validate_json(fixture_bytes("bgblauth_93_2021.json"))
    assert envelope.body.results is not None
    infos = [i for r in envelope.body.results.references if (i := to_bgbl_info(r))]
    info = next(i for i in infos if i.id == "BGBLA_2021_I_93")
    assert info.bgbl == "BGBl. I Nr. 93/2021"
    assert info.legislative_period == "XXVII"
    assert info.rv_numbers == ("662",)
    assert info.ab_numbers == ("705",)
    assert info.ia_numbers == ()
    assert info.nr_session == "89"
    assert info.nr_session_date == date(2021, 3, 24)


def test_bgbl_info_with_initiative_motion() -> None:
    envelope = Envelope.model_validate_json(fixture_bytes("bgblauth_129_2017.json"))
    assert envelope.body.results is not None
    infos = [i for r in envelope.body.results.references if (i := to_bgbl_info(r))]
    info = next(i for i in infos if i.id == "BGBLA_2017_I_129")
    assert info.legislative_period == "XXV"
    assert info.rv_numbers == ()
    assert info.ia_numbers == ("2235",)
    assert info.ab_numbers == ("1705",)


def test_select_version() -> None:
    envelope = Envelope.model_validate_json(fixture_bytes("brkons_ug_67.json"))
    assert envelope.body.results is not None
    versions = tuple(
        sorted(
            (v for r in envelope.body.results.references if (v := to_law_version(r))),
            key=lambda v: v.valid_from or date.min,
        )
    )
    today = date(2026, 11, 10)
    assert select_version(versions, None, None, today).id == "NOR40232360"
    assert select_version(versions, None, date(2019, 6, 3), today).id == "NOR40196464"
    assert select_version(versions, "NOR40033961", date(2019, 6, 3), today).id == "NOR40033961"
    # Unbekannte ID: Stichtag bzw. heute gilt.
    assert select_version(versions, "NOR99999999", None, today).id == "NOR40232360"
