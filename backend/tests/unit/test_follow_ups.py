"""Slice 3.2: relationship tracking and the follow-up engine's boundaries, as pure functions."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.enums import ActivityDirection, ActivityKind, CallOutcome, StageOutcome
from app.core.errors import ValidationFailed
from app.crm.activities import NewActivity, classify, relationship
from app.crm.follow_ups import is_quiet, last_touch
from app.deals.models import Deal
from app.deals.service import attention_reasons

OUT, IN, TALK, NOTE = (
    ActivityDirection.OUTBOUND,
    ActivityDirection.INBOUND,
    ActivityDirection.CONVERSATION,
    ActivityDirection.INTERNAL,
)
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def at(hours: int) -> datetime:
    return T0 + timedelta(hours=hours)


def test_no_interactions_means_not_contacted() -> None:
    r = relationship([])
    assert r.response_status == "not_contacted" and r.interactions == 0
    assert r.first_interaction_at is None and r.latest_interaction_at is None


def test_notes_are_not_interactions() -> None:
    r = relationship([(at(0), NOTE), (at(1), NOTE)])
    assert r.response_status == "not_contacted" and r.interactions == 0


def test_attempts_without_any_reply() -> None:
    r = relationship([(at(0), OUT), (at(24), OUT), (at(5), NOTE)])
    assert r.response_status == "no_reply"
    assert r.attempts_since_reply == 2 and r.interactions == 2
    assert r.first_interaction_at == at(0) and r.latest_interaction_at == at(24)


def test_a_reply_resets_attempts_and_later_attempts_await_one() -> None:
    replied = relationship([(at(0), OUT), (at(1), IN)])
    assert replied.response_status == "replied" and replied.attempts_since_reply == 0
    assert replied.last_reply_at == at(1)

    waiting = relationship([(at(0), OUT), (at(1), TALK), (at(48), OUT)])
    assert waiting.response_status == "awaiting_reply" and waiting.attempts_since_reply == 1
    assert waiting.last_reply_at == at(1) and waiting.interactions == 3


def test_order_does_not_depend_on_input_order_and_ties_favour_the_reply() -> None:
    r = relationship([(at(2), OUT), (at(0), OUT), (at(2), IN)])
    assert r.response_status == "replied"


@pytest.mark.parametrize(
    ("elapsed", "quiet"),
    [
        (timedelta(days=14) - timedelta(seconds=1), False),
        (timedelta(days=14), True),
        (timedelta(days=30), True),
    ],
)
def test_quiet_from_exactly_the_threshold(elapsed: timedelta, quiet: bool) -> None:
    assert is_quiet(T0, T0 + elapsed, 14) is quiet


def test_last_touch_is_the_latest_known_moment() -> None:
    assert last_touch(at(0)) == at(0)
    assert last_touch(at(0), None, at(5), at(3)) == at(5)
    assert last_touch(at(9), at(5)) == at(9)  # a record can't be touched before it existed


def _deal(**kw: object) -> Deal:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "outcome": StageOutcome.OPEN,
        "owner_id": uuid.uuid4(),
        "expected_close": date(2027, 1, 31),
        "stage_entered_at": T0,
    }
    return Deal(**(defaults | kw))


def test_a_deal_goes_inactive_at_the_threshold_and_activity_resets_it() -> None:
    task = object()  # any next task will do
    deal = _deal()
    just_before = T0 + timedelta(days=21) - timedelta(seconds=1)
    assert attention_reasons(deal, task, now=just_before, inactive_days=21) == []  # type: ignore[arg-type]
    on_the_day = T0 + timedelta(days=21)
    assert attention_reasons(deal, task, now=on_the_day, inactive_days=21) == [  # type: ignore[arg-type]
        "inactive for 21 days"
    ]
    touched = T0 + timedelta(days=10)
    assert attention_reasons(deal, task, touched, now=on_the_day, inactive_days=21) == []  # type: ignore[arg-type]
    closed = _deal(outcome=StageOutcome.WON)
    assert attention_reasons(closed, None, now=on_the_day, inactive_days=21) == []


def test_each_kind_implies_its_channel_and_direction() -> None:
    acct = uuid.uuid4()

    def kinds(**kw: object) -> tuple[str, str]:
        channel, direction = classify(NewActivity(account_id=acct, summary="x", **kw))  # type: ignore[arg-type]
        return channel.value, direction.value

    assert kinds(kind=ActivityKind.CALL, call_outcome=CallOutcome.CONNECTED) == (
        "call",
        "conversation",
    )
    assert kinds(kind=ActivityKind.CALL, call_outcome=CallOutcome.VOICEMAIL) == (
        "call",
        "outbound",
    )
    assert kinds(kind=ActivityKind.MEETING) == ("meeting", "conversation")
    assert kinds(kind=ActivityKind.NOTE) == ("manual", "internal")
    assert kinds(kind=ActivityKind.MESSAGE, message_channel="linkedin") == ("linkedin", "outbound")
    assert kinds(kind=ActivityKind.MESSAGE, message_channel="email", received=True) == (
        "email",
        "inbound",
    )


@pytest.mark.parametrize(
    "kw",
    [
        {"kind": ActivityKind.CALL},  # a call needs an outcome
        {"kind": ActivityKind.MESSAGE},  # a message needs a channel
        {"kind": ActivityKind.NOTE, "call_outcome": CallOutcome.CONNECTED},
        {"kind": ActivityKind.MEETING, "message_channel": "email"},
    ],
)
def test_kind_specific_detail_is_checked(kw: dict[str, object]) -> None:
    with pytest.raises(ValidationFailed):
        classify(NewActivity(account_id=uuid.uuid4(), summary="x", **kw))  # type: ignore[arg-type]
