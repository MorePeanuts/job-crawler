"""Astronergy campus category and load-more terminal replay."""

from datetime import datetime
from typing import cast

from job_crawler.adapters.astronergy import AstronergyCampus
from job_crawler.models import Source
from job_crawler.transport import Session as TransportSession


class Page:
    def __init__(self, more_visible: bool = False) -> None:
        self.more_visible = more_visible

    async def content(self) -> str:
        style = "" if self.more_visible else "display: none"
        return f"""
        <div class="join-list"><div class="item">
          <div class="info">
            <div class="name" id="506d6f66-ae81-45ef-b5a1-734873ae16e7">HRBP【2027届校招】</div>
            <div class="type">专业职能类【校招】</div>
            <div class="address">嘉兴市海宁市</div>
            <div class="time">2026/09/21</div>
          </div>
          <div class="erify"><div class="content"><div class="txt">
            <p>岗位职责：</p><p>协助招聘</p><p>任职要求：</p><p>应届毕业生</p>
          </div></div></div>
        </div></div><a class="load-more" style="{style}"></a>
        """


class Session:
    last_evidence = "campus-page"

    def __init__(self, more_visible: bool = False) -> None:
        self.page = Page(more_visible)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://astronergy.com.cn/join/index/mode/campus.html"


def source() -> Source:
    return Source(
        source_id="COM0604",
        company_id="COM0604",
        company="正泰新能",
        url="https://astronergy.com.cn/join/index/mode/campus.html",
    )


async def test_astronergy_terminal_and_update_date_not_publication(now: datetime) -> None:
    result = await AstronergyCampus(source(), cast(TransportSession, Session()), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 1
    assert result.scopes[0].terminal
    assert len(result.jobs) == 1
    assert result.jobs[0].duties.endswith("协助招聘")
    assert result.jobs[0].requirements == "应届毕业生"
    assert not result.jobs[0].published


async def test_astronergy_rejects_unfinished_pagination(now: datetime) -> None:
    result = await AstronergyCampus(
        source(), cast(TransportSession, Session(more_visible=True)), now
    ).collect()
    assert result.coverage_issues()
