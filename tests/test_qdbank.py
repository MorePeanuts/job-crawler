"""Live zero-directory shape and synthetic nonzero/login-boundary regressions."""

import json
from copy import deepcopy
from datetime import datetime
from typing import Any, cast

import pytest

from job_crawler.adapters.qdbank import (
    ANNOUNCEMENTS,
    CAMPUS,
    LIST,
    NEWS,
    NEWS_QUERY,
    QUERY,
    QdbankCampus,
)
from job_crawler.models import Source
from job_crawler.transport import Session


class Replay:
    last_evidence = "initial"

    def __init__(self, total: int = 0, fault: str = ""):
        self.total, self.fault = total, fault
        self.page = self
        self.url = ""
        self.pages: list[int] = []
        self.opened: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert (url, ready_endpoints) in {(CAMPUS, (LIST,)), (NEWS, (ANNOUNCEMENTS,))}
        self.url = url
        self.opened.append(url)

    def snapshot(self, label: str, html: str) -> str:
        return label + "-dom"

    async def content(self) -> str:
        title = "青岛银行招聘门户" if self.fault != "identity" else "其他银行"
        active = "校园招聘" if self.url == CAMPUS else "最新动态"
        if self.fault == "social_dom":
            active = "社会招聘"
        empty = "加载中" if self.fault == "loading" else "暂无职位"
        return (
            f"<h1>{title}</h1><div class='menuList'><p class='active'>{active}</p></div>"
            f"<div class='nodata'><p>{empty}</p></div>"
        )

    def catalog(self, page: int, news: bool = False) -> dict[str, Any]:
        self.last_evidence = "news-list" if news else f"list-{page}"
        if not news:
            self.pages.append(page)
        total = (1 if self.fault == "new_announcement" else 0) if news else self.total
        start = 0 if self.fault == "repeat" else (page - 1) * 10
        rows = [{"id": str(i), "plName": "技术岗"} for i in range(start, min(start + 10, total))]
        if self.fault == "missing_id" and rows:
            rows[0].pop("id")
        if self.fault == "missing_name" and rows:
            rows[0].pop("plName")
        if self.fault == "short" and page == 2:
            rows.pop()
        return {
            "code": "1"
            if self.fault == "business" or (news and self.fault == "news_business")
            else "0",
            "data": {
                "records": rows,
                "total": total + (1 if self.fault == "total_change" and page == 2 else 0),
                "size": 20 if self.fault == "size" else 10,
                "current": 1 if self.fault == "page" else page,
                "pages": 3 if self.fault == "page_count" else (total + 9) // 10,
            },
        }

    async def observed(self, endpoint: str) -> dict[str, Any]:
        assert endpoint == (ANNOUNCEMENTS if self.url == NEWS else LIST)
        news = endpoint == ANNOUNCEMENTS
        payload = deepcopy(NEWS_QUERY if news else QUERY)
        condition = payload["condition"]
        assert isinstance(condition, dict)
        if self.fault == "filter":
            condition["plName"] = "技术"
        if self.fault == "social_query" and not news:
            condition["reqType"] = "P3528000001"
        if self.fault == "network":
            raise TimeoutError("public directory timeout")
        return {
            "url": endpoint + ("?filtered=1" if self.fault == "endpoint" else ""),
            "post_data": json.dumps(payload),
            "body": json.dumps(self.catalog(1, news)),
        }

    async def request(self, url: str, *, payload: dict[str, Any]) -> dict[str, Any]:
        # No protected detail endpoint may be requested, even for synthetic nonzero rows.
        assert url == LIST
        assert payload == {**QUERY, "page": payload["page"], "total": self.total}
        return self.catalog(payload["page"])


def adapter(replay: Replay, now: datetime, url: str = CAMPUS) -> QdbankCampus:
    return QdbankCampus(
        Source(source_id="COM0482", company_id="COM0482", company="青岛银行股份有限公司", url=url),
        cast(Session, replay),
        now,
    )


async def test_zero_requires_both_public_directories_and_campus_dom(now: datetime) -> None:
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues() and not result.jobs
    assert replay.opened == [CAMPUS, NEWS]
    assert [(s.expected, s.unique, s.details, s.terminal) for s in result.scopes] == [
        (0, 0, 0, True),
        (0, 0, 0, True),
    ]
    assert "qdbank-campus-dom" in result.scopes[0].evidence
    assert {"news-list", "qdbank-news-dom"} <= set(result.scopes[1].evidence)


@pytest.mark.parametrize(
    "fault",
    [
        "identity",
        "loading",
        "social_dom",
        "social_query",
        "filter",
        "endpoint",
        "network",
        "business",
        "size",
        "page_count",
        "new_announcement",
        "news_business",
    ],
)
async def test_zero_is_not_inferred_from_failed_filtered_or_new_catalogs(
    fault: str, now: datetime
) -> None:
    result = await adapter(Replay(fault=fault), now).collect()
    assert result.coverage_issues() and not result.jobs


async def test_nonzero_paginates_but_does_not_bypass_detail_login_or_claim_completion(
    now: datetime,
) -> None:
    replay = Replay(21)
    result = await adapter(replay, now).collect()
    assert replay.pages == [1, 2, 3] and replay.opened == [CAMPUS, NEWS]
    assert result.scopes[0].unique == result.scopes[0].expected == 21
    assert result.scopes[0].terminal and result.scopes[0].details == 0
    assert {issue.job_key for issue in result.issues if issue.code == "auth_required"} == {
        str(i) for i in range(21)
    }
    assert not result.jobs and result.coverage_issues()


@pytest.mark.parametrize(
    "fault", ["repeat", "short", "page", "total_change", "missing_id", "missing_name"]
)
async def test_nonzero_catalog_failures_are_distinct_from_detail_auth(
    fault: str, now: datetime
) -> None:
    result = await adapter(Replay(21, fault), now).collect()
    assert result.coverage_issues()
    assert any(issue.code != "auth_required" for issue in result.issues)
    assert not result.scopes[0].terminal


@pytest.mark.parametrize(
    "url",
    [CAMPUS.replace(":7000", ""), CAMPUS.replace("https:", "http:"), CAMPUS + "?dept=x", NEWS],
)
async def test_wrong_origin_route_port_or_filters_never_open(url: str, now: datetime) -> None:
    replay = Replay()
    result = await adapter(replay, now, url).collect()
    assert result.coverage_issues() and not replay.opened
