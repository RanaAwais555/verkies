"""Slice 3.3: the small rules behind report labels and periods."""

from datetime import UTC, datetime
from decimal import Decimal

from app.reports.service import _bucket, _icp_band, _words, window


def test_stored_keys_read_as_words() -> None:
    assert _words("csv_import") == "CSV import"
    assert _words("unsuitable_company_size") == "Unsuitable company size"
    assert _words("research") == "Research"


def test_periods() -> None:
    now = datetime(2026, 10, 11, 12, tzinfo=UTC)
    assert window("30d", now) == (datetime(2026, 9, 11, 12, tzinfo=UTC), now)
    assert window("ytd", now)[0] == datetime(2026, 1, 1, tzinfo=UTC)


def test_score_buckets_and_icp_bands_at_their_edges() -> None:
    dash = chr(0x2013)
    assert _bucket(Decimal("9.99")) == f"0{dash}9"
    assert _bucket(Decimal("90")) == f"90{dash}100"
    assert _bucket(Decimal("100")) == f"90{dash}100"
    assert _icp_band(Decimal("70")) == f"ICP 70{dash}100"
    assert _icp_band(Decimal("69.99")) == f"ICP 40{dash}69"
    assert _icp_band(None) == "Unknown ICP"
