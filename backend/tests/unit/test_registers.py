"""Register sources (slice 8.1): turning the SRA's register into VROS's shape."""

import json
from datetime import date

import pytest

from app.providers.errors import ProviderError
from app.registers.refresh import fingerprint
from app.registers.search import RegisterQuery
from app.registers.sources import LONDON_AREAS, company_number, postcode_area, website
from app.registers.sra import parse


def org(number: int, name: str, **extra: object) -> dict[str, object]:
    """An organisation shaped like the SRA's GetAll output (invented values)."""
    return {
        "SraNumber": number,
        "PracticeName": name,
        "AuthorisationStatus": "YES",
        "AuthorisationDate": "2015-03-01T00:00:00",
        "Constitution": "ILLP",
        "Type": "RecognisedBodyAuthorised",
        "CompanyRegNo": None,
        "NoOfOffices": 1,
        "WorkArea": ["Immigration"],
        "Websites": None,
        "TradingNames": None,
        "Offices": [
            {
                "Postcode": "SE1 1AA",
                "Town": "London",
                "PhoneNumber": "02070000000",
                "Email": "info@example.test",
                "Website": None,
                "OfficeType": "HO",
            }
        ],
        **extra,
    }


def body(*orgs: dict[str, object]) -> bytes:
    return json.dumps({"Count": len(orgs), "Organisations": list(orgs)}).encode()


def test_an_authorised_firm_becomes_an_active_entry_with_its_head_office() -> None:
    [entry] = parse(
        body(
            org(
                100001,
                "Bright  Legal LLP",
                CompanyRegNo="oc123456",
                Websites=["www.brightlegal.test"],
                NoOfOffices=2,
                WorkArea=["Immigration", "Family / Matrimonial"],
                Offices=[
                    {"Postcode": "M1 1AA", "Town": "Manchester", "OfficeType": "BRANCH"},
                    {
                        "Postcode": "EC1A 1BB",
                        "Town": "London",
                        "PhoneNumber": "02071111111",
                        "Email": "hello@brightlegal.test",
                        "OfficeType": "HO",
                    },
                ],
            )
        )
    )
    assert entry.source_id == "100001" and entry.name == "Bright Legal LLP" and entry.active
    assert entry.company_number == "OC123456"
    assert entry.website == "https://www.brightlegal.test/"
    assert (entry.postcode, entry.town, entry.phone, entry.email) == (
        "EC1A 1BB",
        "London",
        "02071111111",
        "hello@brightlegal.test",
    )
    assert entry.postcode_areas == ("EC", "M")
    assert entry.areas == ("Immigration", "Family / Matrimonial")
    assert entry.office_count == 2 and entry.authorised_on == date(2015, 3, 1)


@pytest.mark.parametrize(
    ("status", "active"),
    [("YES", True), ("CONDITION", True), ("REVOKE", False), ("CEASE", False), (None, False)],
)
def test_only_authorised_firms_are_active(status: str | None, active: bool) -> None:
    [entry] = parse(body(org(1, "Firm", AuthorisationStatus=status)))
    assert entry.active is active


def test_an_office_website_is_used_when_the_firm_lists_none() -> None:
    offices = [{"Postcode": "W1 1AA", "Website": "http://firm.test/contact", "OfficeType": "HO"}]
    [entry] = parse(body(org(1, "Firm", Offices=offices)))
    assert entry.website == "https://firm.test/"


def test_records_without_a_number_or_name_are_skipped_and_duplicates_kept_once() -> None:
    entries = parse(
        body(
            org(1, "First"),
            {"SraNumber": None, "PracticeName": "No number"},
            {"SraNumber": 2, "PracticeName": ""},
            org(1, "First again"),
        )
    )
    assert [(e.source_id, e.name) for e in entries] == [("1", "First")]


@pytest.mark.parametrize("payload", [b"not json", b"[]", b'{"Organisations": null}'])
def test_a_broken_download_is_an_error_not_an_empty_register(payload: bytes) -> None:
    with pytest.raises(ProviderError):
        parse(payload)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (RegisterQuery("sra"), "SRA: All areas"),
        (
            RegisterQuery(
                "sra", areas=("Immigration",), postcode_areas=LONDON_AREAS, offices_min=2
            ),
            "SRA: Immigration; in London; 2+ offices",
        ),
        (
            RegisterQuery("sra", postcode_areas=("M", "LS"), offices_max=3, max_areas=3),
            "SRA: All areas; in M, LS; up to 3 offices; at most 3 areas of work",
        ),
        (RegisterQuery("sra", offices_min=2, offices_max=2), "SRA: All areas; 2 offices"),
    ],
)
def test_a_search_is_named_in_plain_words(query: RegisterQuery, expected: str) -> None:
    assert query.label() == expected


def test_the_same_register_in_another_order_has_the_same_fingerprint() -> None:
    first = parse(body(org(1, "One"), org(2, "Two")))
    reordered = parse(body(org(2, "Two"), org(1, "One")))
    changed = parse(body(org(1, "One"), org(2, "Two renamed")))
    assert fingerprint(first) == fingerprint(reordered) != fingerprint(changed)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("oc338007", "OC338007"),
        ("1234567", "01234567"),
        (" 12345678 ", "12345678"),
        ("SC12345", None),
        ("not a number", None),
        (None, None),
    ],
)
def test_company_numbers_are_normalised(raw: object, expected: str | None) -> None:
    assert company_number(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("SE15 4NL", "SE"), ("m1 1aa", "M"), ("WC2H 0HF", "WC"), ("6521121", None), (None, None)],
)
def test_postcode_areas(raw: object, expected: str | None) -> None:
    assert postcode_area(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("www.firm.co.uk", "https://www.firm.co.uk/"),
        ("HTTPS://Firm.CO.UK/about", "https://firm.co.uk/"),
        ("info@firm.co.uk", None),
        ("see our site", None),
        ("localhost", None),
        ("", None),
    ],
)
def test_websites_become_homepages(raw: str, expected: str | None) -> None:
    assert website(raw) == expected
