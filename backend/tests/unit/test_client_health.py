"""Slice 4.2: each client-health rule at its boundary."""

from datetime import UTC, datetime, timedelta

from app.clients.health import Facts, ProjectFacts, assess
from app.clients.models import ClientFeedback
from app.config import Settings
from app.core.enums import HealthColour, ProjectStatus, RiskSeverity, Sentiment
from app.crm.activities import Relationship

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
SETTINGS = Settings()


def talked(days_ago: int, *, unanswered: int = 0) -> Relationship:
    at = NOW - timedelta(days=days_ago)
    return Relationship(at, at, 1 + unanswered, at, unanswered, "replied")


def facts(**kw) -> Facts:  # type: ignore[no-untyped-def]
    base = {
        "client_since": TODAY - timedelta(days=200),
        "projects": [],
        "overdue_tasks": 0,
        "relationship": talked(1),
        "feedback": None,
    }
    return Facts(**{**base, **kw})


def project(**kw) -> ProjectFacts:  # type: ignore[no-untyped-def]
    return ProjectFacts(
        **{"name": "Portal", "status": ProjectStatus.ACTIVE, "target_date": None, **kw}
    )


def colour(f: Facts) -> HealthColour:
    return assess(f, NOW, SETTINGS)[0]


def test_a_client_with_nothing_wrong_is_green() -> None:
    assert assess(facts(), NOW, SETTINGS) == (HealthColour.GREEN, [])


def test_silence_turns_yellow_at_30_days_and_red_at_60() -> None:
    assert colour(facts(relationship=talked(29))) is HealthColour.GREEN
    assert colour(facts(relationship=talked(30))) is HealthColour.YELLOW
    assert colour(facts(relationship=talked(59))) is HealthColour.YELLOW
    _, reasons = assess(facts(relationship=talked(60)), NOW, SETTINGS)
    assert [r.text for r in reasons] == ["No contact for 60 days"]


def test_without_any_contact_the_clock_starts_when_they_became_a_client() -> None:
    never = Relationship(None, None, 0, None, 0, "not_contacted")
    assert (
        colour(facts(relationship=never, client_since=TODAY - timedelta(days=10)))
        is HealthColour.GREEN
    )
    _, reasons = assess(
        facts(relationship=never, client_since=TODAY - timedelta(days=45)), NOW, SETTINGS
    )
    assert reasons[0].text == "No contact since becoming a client for 45 days"


def test_unanswered_messages() -> None:
    assert colour(facts(relationship=talked(1, unanswered=2))) is HealthColour.GREEN
    _, reasons = assess(facts(relationship=talked(1, unanswered=3)), NOW, SETTINGS)
    assert [r.text for r in reasons] == ["3 messages without a reply"]


def test_project_status_target_and_risks() -> None:
    assert colour(facts(projects=[project(status=ProjectStatus.AT_RISK)])) is HealthColour.RED
    assert colour(facts(projects=[project(status=ProjectStatus.ON_HOLD)])) is HealthColour.YELLOW
    assert colour(facts(projects=[project(target_date=TODAY)])) is HealthColour.GREEN
    assert (
        colour(facts(projects=[project(target_date=TODAY - timedelta(days=1))]))
        is HealthColour.YELLOW
    )
    assert (
        colour(facts(projects=[project(open_risks=[(RiskSeverity.LOW, "x")])]))
        is HealthColour.GREEN
    )
    assert (
        colour(facts(projects=[project(open_risks=[(RiskSeverity.MEDIUM, "x")])]))
        is HealthColour.YELLOW
    )
    assert (
        colour(facts(projects=[project(open_risks=[(RiskSeverity.HIGH, "x")])])) is HealthColour.RED
    )


def test_overdue_milestones_turn_red_at_14_days() -> None:
    def late(days: int) -> Facts:
        return facts(
            projects=[project(late_milestones=[("Designs", TODAY - timedelta(days=days))])]
        )

    assert colour(late(13)) is HealthColour.YELLOW
    _, reasons = assess(late(14), NOW, SETTINGS)
    assert [r.text for r in reasons] == ["Portal: milestone Designs is 14 days overdue"]


def test_overdue_tasks_are_yellow() -> None:
    _, reasons = assess(facts(overdue_tasks=2), NOW, SETTINGS)
    assert [(r.level, r.text) for r in reasons] == [("yellow", "2 overdue tasks")]


def test_negative_feedback_counts_for_90_days_and_only_the_latest() -> None:
    def said(sentiment: Sentiment, days_ago: int) -> ClientFeedback:
        return ClientFeedback(
            sentiment=sentiment, received_on=TODAY - timedelta(days=days_ago), note="Slow replies"
        )

    _, reasons = assess(facts(feedback=said(Sentiment.NEGATIVE, 90)), NOW, SETTINGS)
    assert (
        reasons[0].text
        == f"Negative feedback on {(TODAY - timedelta(days=90)).isoformat()}: Slow replies"
    )
    assert colour(facts(feedback=said(Sentiment.NEGATIVE, 91))) is HealthColour.GREEN
    assert colour(facts(feedback=said(Sentiment.POSITIVE, 1))) is HealthColour.GREEN


def test_red_reasons_come_first() -> None:
    _, reasons = assess(
        facts(overdue_tasks=1, projects=[project(status=ProjectStatus.AT_RISK)]), NOW, SETTINGS
    )
    assert [r.level for r in reasons] == ["red", "yellow"]


def test_the_thresholds_are_settings() -> None:
    strict = Settings(client_quiet_yellow_days=5, client_quiet_red_days=10)
    assert assess(facts(relationship=talked(10)), NOW, strict)[0] is HealthColour.RED
