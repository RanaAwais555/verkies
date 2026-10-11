"""The plain-English interpreter against the master context's own examples (§15)."""

from datetime import timedelta

from app.leads.interpret import Vocabulary, interpret

VOCAB = Vocabulary(industries=["SaaS", "Legal", "Dental"], cities=["Leeds"])


def meanings(query: str) -> dict[str, str]:
    return {u.phrase: u.meaning for u in interpret(query, VOCAB).understood}


def test_funding_and_hiring_are_both_required_within_the_window() -> None:
    f = interpret(
        "Find UK SaaS startups that raised funding within the last 12 months"
        " and are hiring developers.",
        VOCAB,
    ).filters
    assert f.country == "GB"
    assert f.industries == ["saas"]
    assert f.topics == ["startup"]
    assert sorted(f.signal_groups) == [["developer_hiring", "cto_hiring"], ["funding"]]
    assert f.signal_window == timedelta(days=360)
    assert not f.top_leads


def test_similarity_is_reported_as_not_available_rather_than_guessed() -> None:
    result = interpret("Find businesses similar to Wesbridge.", VOCAB)
    assert [u.phrase for u in result.unsupported] == ["similar to wesbridge"]
    assert result.filters.topics == []


def test_city_industry_and_any_of_several_opportunities() -> None:
    f = interpret(
        "Find London professional-service firms that could benefit from CRM and client portals.",
        VOCAB,
    ).filters
    assert f.cities == ["london"]
    assert f.categories == ["client_portal", "crm"]
    assert f.topics == ["professional"]


def test_a_likely_rebuild_means_either_rebuild_opportunity() -> None:
    f = interpret("Find companies where a product rebuild looks likely.", VOCAB).filters
    assert f.categories == ["product_rebuild"]
    assert f.topics == []


def test_who_to_contact_this_week_is_top_leads_mode_with_its_count() -> None:
    result = interpret("Find 20 companies Verkies should contact this week.", VOCAB)
    assert result.filters.top_leads
    assert result.filters.limit == 20
    assert result.filters.topics == []


def test_my_next_leads() -> None:
    f = interpret("find my next 20 leads", VOCAB).filters
    assert f.top_leads and f.limit == 20 and f.owner is None


def test_seo_and_conversion_together() -> None:
    f = interpret("Find companies with strong SEO opportunity but weak conversion.", VOCAB).filters
    assert f.categories == ["conversion_optimization", "seo"] or f.categories == [
        "seo",
        "conversion_optimization",
    ]
    assert f.topics == []


def test_every_word_is_accounted_for() -> None:
    m = meanings("unassigned dental clinics in Leeds")
    assert m == {
        "unassigned": "Accounts with no owner",
        "leeds": "Located in Leeds",
        "dental": "Industry is dental",
        "clinics": "Name, industry or description mentions “clinic”",
    }


def test_saas_is_not_singularised() -> None:
    assert interpret("saas", Vocabulary()).filters.topics == ["saas"]


def test_typographic_apostrophes_and_years_survive() -> None:
    curly = f"o{chr(0x2019)}brien bakery"
    assert interpret(curly, Vocabulary()).filters.topics == ["o'brien", "bakery"]
    assert interpret("founded 2019", Vocabulary()).filters.limit == 20  # a year is not a count
