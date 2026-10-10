"""Explicit source-date semantics; discovery time never acts as publication time."""

import calendar
import re
from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from job_crawler.models import Job, Selection

SHANGHAI = ZoneInfo("Asia/Shanghai")
Window = Literal["all", "day", "week", "month"]


def parse_date(value: str) -> tuple[datetime, bool] | None:
    text = value.strip()
    if not text:
        return None
    try:
        if re.fullmatch(r"\d{13}|\d{10}", text):
            return datetime.fromtimestamp(
                int(text) / (1000 if len(text) == 13 else 1), SHANGHAI
            ), False
        text = text.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
        day_only = bool(re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text))
        if day_only:
            result = datetime.strptime(text, "%Y-%m-%d")
        else:
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return result.replace(tzinfo=SHANGHAI) if result.tzinfo is None else result, day_only
    except (ValueError, OverflowError, OSError):
        return None


def window_start(window: Window, as_of: datetime) -> datetime | None:
    if as_of.tzinfo is None:
        raise ValueError("as_of 必须包含时区")
    if window == "all":
        return None
    if window in {"day", "week"}:
        return as_of - timedelta(days=1 if window == "day" else 7)
    year, month = (as_of.year - 1, 12) if as_of.month == 1 else (as_of.year, as_of.month - 1)
    return as_of.replace(
        year=year, month=month, day=min(as_of.day, calendar.monthrange(year, month)[1])
    )


def select(
    job: Job,
    window: Window,
    as_of: datetime,
    *,
    include_undated_new: bool = True,
) -> Selection:
    since = window_start(window, as_of)
    if not job.visible or job.closed:
        return Selection(kind="exclude", reason="not_open")
    if job.work_type != "校招":
        return Selection(kind="exclude", reason="outside_campus_scope")
    deadline = parse_date(job.deadline)
    if job.deadline.strip() and deadline is None:
        return Selection(kind="review", reason="unparsed_deadline")
    if deadline:
        end, day_only = deadline
        if day_only:
            end = datetime.combine(end.date(), time.max, end.tzinfo)
        if end < as_of:
            return Selection(kind="exclude", reason="expired")
    published = parse_date(job.published)
    if job.published.strip() and published is None:
        return Selection(kind="review", reason="unparsed_publication")
    if published:
        start, day_only = published
        if start > as_of:
            return Selection(kind="review", reason="future_publication")
        end = datetime.combine(start.date(), time.max, start.tzinfo) if day_only else start
        if since is not None and end < since:
            return Selection(kind="exclude", reason="outside_window")
    elif since is not None:
        if window == "day" and include_undated_new and job.first_seen_at is not None:
            if job.first_seen_at.tzinfo is None or job.first_seen_at > as_of:
                return Selection(kind="review", reason="invalid_discovery_time")
            if not job.discovery_eligible:
                return Selection(kind="exclude", reason="undated_baseline")
            if job.first_seen_at < since:
                return Selection(kind="exclude", reason="discovery_outside_window")
            return Selection(kind="include", reason="first_discovered_without_publication")
        return Selection(kind="review", reason="missing_publication")
    return Selection(kind="include", reason="eligible")
