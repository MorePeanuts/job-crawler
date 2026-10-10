from datetime import datetime

import pytest

from job_crawler.filtering import SHANGHAI, parse_date, select, window_start
from job_crawler.models import Job


@pytest.mark.parametrize(
    ("deadline", "kind"),
    [
        ("2026-10-10", "include"),
        ("2026-10-09", "exclude"),
        ("2026-10-10 11:59:59", "exclude"),
        ("2026-10-10T12:00:00+08:00", "include"),
        ("2026-10-10T04:00:01Z", "include"),
        ("2026年10月10日", "include"),
        ("招满即止", "review"),
        ("2026-02-30", "review"),
        ("", "include"),
    ],
)
def test_deadlines(job: Job, now: datetime, deadline: str, kind: str) -> None:
    job.deadline = deadline
    assert select(job, "all", now).kind == kind


@pytest.mark.parametrize(
    ("published", "reason"),
    [
        ("", "missing_publication"),
        ("昨天", "unparsed_publication"),
        ("2026-10-11", "future_publication"),
        ("2026-10-09 11:59:59", "outside_window"),
        ("2026-10-09 12:00:00", "eligible"),
        ("2026-10-09", "eligible"),
        ("2026-10-08", "outside_window"),
    ],
)
def test_rolling_day_uses_source_date(job: Job, now: datetime, published: str, reason: str) -> None:
    job.published = published
    assert select(job, "day", now).reason == reason


def test_unknown_publication_allowed_for_inventory(job: Job, now: datetime) -> None:
    job.published = ""
    assert select(job, "all", now).kind == "include"
    assert select(job, "week", now).kind == "review"


def test_calendar_month_and_timezone() -> None:
    assert window_start("month", datetime(2024, 3, 31, tzinfo=SHANGHAI)) == datetime(
        2024, 2, 29, tzinfo=SHANGHAI
    )
    assert window_start("month", datetime(2026, 1, 31, tzinfo=SHANGHAI)) == datetime(
        2025, 12, 31, tzinfo=SHANGHAI
    )
    with pytest.raises(ValueError):
        window_start("week", datetime(2026, 10, 10))
    assert parse_date("1791590400000") == parse_date("1791590400")


def test_inactive_and_outside_scope(job: Job, now: datetime) -> None:
    job.closed = True
    assert select(job, "all", now).reason == "not_open"
    job.closed = False
    job.work_type = "实习"
    assert select(job, "all", now).reason == "outside_campus_scope"
