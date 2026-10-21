"""Viiyong campus server pagination and inline job identity replay."""

from datetime import datetime
from typing import Any, cast

from job_crawler.adapters.viiyong import ViiyongCampus
from job_crawler.models import Source
from job_crawler.transport import Session as TransportSession


class Page:
    def __init__(self, session: "Session") -> None:
        self.session = session

    async def evaluate(self, script: str) -> dict[str, Any]:
        assert "join-list" in script
        num = self.session.current
        rows = [
            {
                "id": str(index),
                "title": f"工程师{index}",
                "html": "<p>招聘要求：本科</p><p>工作职责：研发</p>",
            }
            for index in (range(1, 10) if num == 1 else range(10, 20) if num == 2 else [20])
        ]
        if num == 1:
            rows.insert(0, {"id": "100", "title": "微容科技校招介绍", "html": "宣传材料"})
        if self.session.duplicate and num == 2:
            rows[0]["id"] = "1"
        return {"current": num, "pages": [1, 2, 3], "rows": rows}


class Session:
    last_evidence = "page-1"

    def __init__(self, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.current = 1
        self.page = Page(self)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.current = int(url.split("current=", 1)[1]) if "current=" in url else 1
        self.last_evidence = f"page-{self.current}"


def source() -> Source:
    return Source(
        source_id="COM0709",
        company_id="COM0709",
        company="微容科技",
        url="https://www.viiyong.com/cn/JobList.aspx?TypeId=10029",
    )


async def test_viiyong_traverses_pages_and_excludes_introduction(now: datetime) -> None:
    result = await ViiyongCampus(source(), cast(TransportSession, Session()), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == result.scopes[0].listed == 20
    assert result.scopes[0].terminal
    assert len(result.jobs) == 20
    assert result.jobs[0].duties == "研发"
    assert result.jobs[0].requirements == "本科"
    assert not result.jobs[0].published


async def test_viiyong_rejects_duplicate_job_id(now: datetime) -> None:
    result = await ViiyongCampus(
        source(), cast(TransportSession, Session(duplicate=True)), now
    ).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
