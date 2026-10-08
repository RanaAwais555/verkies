"""Pure rules used by approval: business-day due dates and buying roles from job titles."""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.enums import DecisionMakerRole, TaskStatus
from app.crm.models import Opportunity, Task
from app.crm.service import attention_reasons
from app.prospects.service import add_business_days, role_for


@pytest.mark.parametrize(
    ("start", "days", "due"),
    [
        ("2026-10-05", 2, "2026-10-07"),  # Monday -> Wednesday
        ("2026-10-08", 2, "2026-10-12"),  # Thursday -> Monday, skipping the weekend
        ("2026-10-09", 1, "2026-10-12"),  # Friday -> Monday
        ("2026-10-10", 2, "2026-10-13"),  # Saturday -> Tuesday
        ("2026-10-11", 0, "2026-10-12"),  # due "today" on a Sunday -> Monday
    ],
)
def test_due_dates_count_business_days(start: str, days: int, due: str) -> None:
    begin = datetime.fromisoformat(start).replace(hour=9, tzinfo=UTC)
    result = add_business_days(begin, days)
    assert result.date().isoformat() == due and result.time() == begin.time()


@pytest.mark.parametrize(
    ("title", "role"),
    [
        ("Founder and Senior Immigration Adviser", DecisionMakerRole.DECISION_MAKER),
        ("Managing Director", DecisionMakerRole.DECISION_MAKER),
        ("CTO", DecisionMakerRole.TECHNICAL_BUYER),
        ("Head of Engineering", DecisionMakerRole.TECHNICAL_BUYER),
        ("Head of Operations", DecisionMakerRole.OPERATIONS_BUYER),
        ("Marketing Manager", DecisionMakerRole.MARKETING_BUYER),
        ("Product Lead", DecisionMakerRole.PRODUCT_BUYER),
        ("Paralegal", None),  # no rule: Unknown, not a guess
        (None, None),
    ],
)
def test_roles_come_from_titles_or_stay_unknown(
    title: str | None, role: DecisionMakerRole | None
) -> None:
    assert role_for(title) == role


def test_opportunity_attention_rule() -> None:
    opportunity = Opportunity(name="x", problem="y")
    due = datetime(2026, 10, 12, tzinfo=UTC)
    good = Task(title="t", status=TaskStatus.OPEN, owner_id=None, due_at=due)
    assert attention_reasons(opportunity, None) == ["no next action"]
    assert attention_reasons(opportunity, good) == ["next action has no owner"]
    good.owner_id = uuid.uuid4()
    assert attention_reasons(opportunity, good) == []
    good.due_at = None
    assert attention_reasons(opportunity, good) == ["next action has no due date"]
    good.status = TaskStatus.DONE
    assert attention_reasons(opportunity, good) == ["next action is closed; set a new one"]
