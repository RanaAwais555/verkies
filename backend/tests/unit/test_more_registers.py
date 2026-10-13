"""More registers (slice 8.3): the IAA's spreadsheet, the schools CSV and the Charity Commission's
extract, each turned into VROS's shape from small files built here in the publishers' formats."""

import io
import zipfile
from datetime import date

import pytest

from app.providers.errors import ProviderError
from app.registers import charity, gias, iaa, xlsx
from app.registers.refresh import SOURCES, row_hash
from app.registers.search import RegisterQuery

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def workbook(rows: list[list[str]], sheet: str = "Sheet1") -> bytes:
    """A real .xlsx (shared strings, one sheet) as Excel writes it."""
    strings: list[str] = []
    cells_xml = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, value in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            if value.isdigit():
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            elif value:
                strings.append(value)
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        cells_xml.append(f'<row r="{r}">{"".join(cells)}</row>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as book:
        book.writestr(
            "xl/workbook.xml",
            f'<workbook {NS} {RNS}><sheets><sheet name="{sheet}" sheetId="1" r:id="rId1"/>'
            "</sheets></workbook>",
        )
        book.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>',
        )
        book.writestr(
            "xl/sharedStrings.xml",
            f"<sst {NS}>" + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>",
        )
        book.writestr(
            "xl/worksheets/sheet1.xml",
            f"<worksheet {NS}><sheetData>{''.join(cells_xml)}</sheetData></worksheet>",
        )
    return out.getvalue()


def test_the_spreadsheet_reader_returns_cell_text_and_skips_gaps() -> None:
    data = workbook([["Name", "", "Count"], ["Alpha", "x", "12"]])
    assert xlsx.rows(data) == [["Name", "", "Count"], ["Alpha", "x", "12"]]
    with pytest.raises(ProviderError):
        xlsx.rows(b"not a zip")
    with pytest.raises(ProviderError):
        xlsx.rows(data, sheet="Missing")


IAA_ROWS = [
    ["List of IAA regulated organisations"],
    [
        "Organisation Name",
        "Organisation Number",
        "Regulated Level",
        "Organisation Website",
        "Earliest Approval Date",
    ],
    ["Bright Visas Ltd", "F201900001", "Level 3", "www.brightvisas.test", "45658"],
    ["Quiet Advice", "F200500002", "Level 1", "", "2005-06-01"],
    ["", "F000", "Level 1", "", ""],
]


def test_the_iaa_list_finds_its_header_and_reads_levels_websites_and_dates() -> None:
    entries = iaa.parse(xlsx.rows(workbook(IAA_ROWS)))
    bright, quiet = entries
    assert (bright.source_id, bright.name, bright.status) == (
        "F201900001",
        "Bright Visas Ltd",
        "Level 3",
    )
    assert bright.website == "https://www.brightvisas.test/" and bright.areas == ("Level 3",)
    assert bright.authorised_on == date(2025, 1, 1)  # spreadsheet serial day 45658
    assert quiet.website is None and quiet.authorised_on == date(2005, 6, 1)
    assert all(e.active for e in entries)
    with pytest.raises(ProviderError):
        iaa.parse([["Something else"], ["a", "b"]])


QUOTE = chr(0x2019)  # a right single quotation mark, as schools' names often have
GIAS_HEADER = (
    "URN,EstablishmentName,TypeOfEstablishment (name),EstablishmentTypeGroup (name),"
    "PhaseOfEducation (name),EstablishmentStatus (name),SchoolWebsite,TelephoneNum,Postcode,"
    "Town,HeadTitle (name),HeadFirstName,HeadLastName,HeadPreferredJobTitle,NumberOfPupils,"
    "OpenDate,LA (name)"
)


def test_schools_are_read_with_their_type_phase_head_and_status() -> None:
    body = "\r\n".join(
        [
            GIAS_HEADER,
            f"100001,St Ann{QUOTE}s Primary,Voluntary aided school,"
            "Local authority maintained schools,Primary,Open,www.stanns.test,02070000001,"
            "SE1 1AA,London,Mrs,Jo,Hart,Headteacher,420,01-09-2012,Southwark",
            "100002,Old Grammar,Other independent school,Independent schools,Not applicable,"
            "Closed,,,,Leeds,,,,,,,Leeds",
        ]
    ).encode("cp1252")
    open_school, closed = gias.parse(body)
    assert open_school.name == f"St Ann{QUOTE}s Primary"  # byte 0x92 in Windows-1252
    assert open_school.active and not closed.active
    assert open_school.areas == ("Local authority maintained schools", "Primary")
    assert closed.areas == ("Independent schools",)  # "Not applicable" phase dropped
    assert open_school.website == "https://www.stanns.test/"
    assert open_school.postcode_areas == ("SE",) and open_school.authorised_on == date(2012, 9, 1)
    assert open_school.data["head"] == {
        "title": "Mrs",
        "name": "Jo Hart",
        "job_title": "Headteacher",
    }
    assert open_school.data["pupils"] == 420 and closed.data["head"] is None
    with pytest.raises(ProviderError):
        gias.parse(b"Name,Town\r\nA,B\r\n")


def extract(name: str, header: list[str], rows: list[list[str]]) -> bytes:
    """A Charity Commission extract: one tab-separated text file in a zip."""
    text = "\r\n".join("\t".join(r) for r in [header, *rows]) + "\r\n"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as book:
        book.writestr(f"publicextract.{name}.txt", "﻿" + text)
    return out.getvalue()


CHARITY_HEADER = [
    "organisation_number",
    "registered_charity_number",
    "linked_charity_number",
    "charity_name",
    "charity_type",
    "charity_registration_status",
    "date_of_registration",
    "latest_income",
    "charity_contact_address2",
    "charity_contact_address3",
    "charity_contact_postcode",
    "charity_contact_phone",
    "charity_contact_email",
    "charity_contact_web",
    "charity_company_registration_number",
    "charity_activities",
]
CLASS_HEADER = [
    "registered_charity_number",
    "linked_charity_number",
    "classification_code",
    "classification_type",
    "classification_description",
]


def test_charities_keep_registered_main_charities_with_income_and_what_they_do() -> None:
    charities = extract(
        "charity",
        CHARITY_HEADER,
        [
            [
                "1",
                "1100001",
                "0",
                "Hope Trust",
                "Charitable company",
                "Registered",
                "2003-04-01 00:00:00.0000000",
                "512000.60",
                "Chumleigh Street",
                "London",
                "E1 6AN",
                "0207",
                "info@hope.test",
                "www.hope.test",
                "4567890",
                "Helps families",
            ],
            [
                "2",
                "1100001",
                "1",
                "Hope Trust branch",
                "",
                "Registered",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "3",
                "1100002",
                "0",
                "Gone Fund",
                "",
                "Removed",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
        ],
    )
    classified = extract(
        "charity_classification",
        CLASS_HEADER,
        [
            ["1100001", "0", "102", "What", "Education/training"],
            ["1100001", "0", "104", "What", "The Advancement Of Health Or Saving Of Lives"],
            ["1100001", "0", "201", "Who", "Children/young People"],
            ["1100001", "1", "102", "What", "Linked charity's purpose"],
        ],
    )
    [hope] = charity.parse(charities, classified)
    assert (hope.source_id, hope.name, hope.legal_form) == (
        "1100001",
        "Hope Trust",
        "Charitable company",
    )
    assert hope.income == 512001 and hope.company_number == "04567890"
    assert hope.website == "https://www.hope.test/" and hope.postcode_areas == ("E",)
    assert hope.areas == ("Education/training", "The Advancement Of Health Or Saving Of Lives")
    assert hope.authorised_on == date(2003, 4, 1) and hope.town == "London"
    with pytest.raises(ProviderError):
        charity.parse(extract("charity", CHARITY_HEADER, []), classified)


def test_every_register_says_what_its_filters_mean() -> None:
    assert set(SOURCES) == {"sra", "iaa", "gias", "charity"}
    assert SOURCES["iaa"].has_location is False and SOURCES["charity"].has_income is True
    assert {s.short_name for s in SOURCES.values()} == {"SRA", "IAA", "Schools", "Charities"}


def test_income_reads_plainly_in_a_search_title() -> None:
    query = RegisterQuery("charity", income_min=250_000, income_max=10_000_000)
    assert query.label("Charities") == "Charities: All areas; income £250k-£10m"
    assert (
        RegisterQuery("charity", income_min=1_500_000).label()
        == "CHARITY: All areas; income £1.5m+"
    )


def test_a_row_hash_changes_with_content_only() -> None:
    [a] = iaa.parse(xlsx.rows(workbook(IAA_ROWS[:3])))
    [b] = iaa.parse(xlsx.rows(workbook(IAA_ROWS[:3])))
    assert row_hash(a) == row_hash(b)
    changed = [*IAA_ROWS[:2], ["Bright Visas Ltd", "F201900001", "Level 2", "", ""]]
    assert row_hash(iaa.parse(xlsx.rows(workbook(changed)))[0]) != row_hash(a)
