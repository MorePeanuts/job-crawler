"""Lansus public campus pagination and detail identity replay."""

from datetime import datetime
from typing import Any, cast

from job_crawler.adapters.lansus import LansusCampus
from job_crawler.models import Source
from job_crawler.transport import Session as TransportSession


class Page:
    def __init__(self, session: "Replay") -> None:
        self.session = session

    async def evaluate(self, script: str) -> dict[str, Any]:
        assert "campus-jobs/campus-" in script
        page = self.session.current
        keys = range(1, 10) if page == 1 else range(10, 16)
        rows = [
            {
                "id": f"campus-engineer-{number}",
                "url": f"https://www.lansus.com/about/careers/campus-jobs/campus-engineer-{number}",
                "title": f"工程师{number}",
                "fields": ["硕士", "产品研发", "上海/西安"],
            }
            for number in keys
        ]
        if self.session.duplicate and page == 2:
            rows[0]["id"] = "campus-engineer-1"
        return {
            "path": "/about/careers/campus-jobs",
            "current": page,
            "pages": [2] if page == 1 else [1],
            "rows": rows,
        }


class Replay:
    last_evidence = "fixture:list"

    def __init__(self, *, duplicate: bool = False, mismatch: bool = False) -> None:
        self.current = 1
        self.duplicate = duplicate
        self.mismatch = mismatch
        self.page = Page(self)
        self.details: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.current = 2 if "page=2" in url else 1
        self.last_evidence = f"fixture:page-{self.current}"

    async def request_html(self, url: str, *, detail: bool = False) -> str:
        assert detail
        self.details.append(url)
        self.last_evidence = f"fixture:detail-{len(self.details)}"
        number = int(url.rsplit("-", 1)[-1])
        title = f"工程师{number + 1 if self.mismatch and number == 2 else number}"
        return (
            f"<h1>{title}</h1><h4>岗位职责</h4><div>设计芯片</div>"
            '<h4>岗位要求</h4><div>硕士学历</div><a href="https://example.com/apply">立即申请</a>'
        )


def source() -> Source:
    return Source(
        source_id="COM0756",
        company_id="COM0756",
        company="飞骧科技",
        url="https://www.lansus.com/about/careers/campus-jobs",
    )


async def test_lansus_traverses_two_pages_and_details(now: datetime) -> None:
    replay = Replay()
    result = await LansusCampus(source(), cast(TransportSession, replay), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == result.scopes[0].details == 15
    assert result.scopes[0].terminal and len(replay.details) == 15
    assert result.jobs[0].requirements == "硕士学历"
    assert result.jobs[0].apply_url == "https://example.com/apply"
    assert result.jobs[0].published == ""


async def test_lansus_rejects_duplicate_and_mismatched_details(now: datetime) -> None:
    duplicate = await LansusCampus(
        source(), cast(TransportSession, Replay(duplicate=True)), now
    ).collect()
    assert duplicate.coverage_issues()
    assert not duplicate.scopes[0].terminal

    mismatch = await LansusCampus(
        source(), cast(TransportSession, Replay(mismatch=True)), now
    ).collect()
    assert mismatch.coverage_issues()
    assert mismatch.scopes[0].details == 14
