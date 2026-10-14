from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.fuyao import FuyaoHeadquarters
from job_crawler.config import CrawlConfig
from job_crawler.models import Source


class Locator:
    def __init__(self, session: "Session", page: int):
        self.session = session
        self.page = page
        self.first = self

    async def click(self, *, timeout: int) -> None:  # noqa: ASYNC109 - Playwright stand-in
        self.session.current_page = self.page


class Session:
    last_evidence = "fixture"

    def __init__(self, output: Path, *, conflict: bool = False):
        self.output = output
        self.page = self
        self.config = CrawlConfig(delay=0)
        self.current_page = 1
        self.detail_key = ""
        self.conflict = conflict
        self.visited: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        if "/position/detail" in url:
            self.detail_key = parse_qs(urlsplit(url).query)["positionId"][0]
            self.visited.append(self.detail_key)
        else:
            assert "projectId=6a752162d3d9c2792c84e535" in url
            self.detail_key = ""

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("不应观察接口")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("不应直接请求 JSON")

    def consume_request(self) -> None:
        pass

    def locator(self, selector: str) -> Locator:
        page = int(selector.split('data-pagenum="')[1].split('"')[0])
        return Locator(self, page)

    async def wait_for_function(
        self,
        script: str,
        *,
        arg: str,
        timeout: int,  # noqa: ASYNC109 - Playwright stand-in
    ) -> None:
        assert arg

    async def content(self) -> str:
        if self.detail_key:
            key = self.detail_key
            title = self.title(int(key))
            application = "other" if self.conflict and key == "5" else key
            return (
                f'<h4 class="name">{title}</h4>'
                '<div class="position-details"><li class="city">福建省-福清</li>'
                '<div class="position-description"><p>岗位职责：</p><p>负责研发</p>'
                "<p>任职要求：</p><p>博士学历</p></div></div>"
                f'<a id="application" pid="{application}">申请</a>'
            )
        start = (self.current_page - 1) * 15 + 1
        cards = "".join(
            f'<div class="position-item" pid="{i}" '
            'projectid="6a752162d3d9c2792c84e535" recruitment="CAMPUSRECRUITMENT">'
            f'<h4 class="title">{self.title(i)}</h4>'
            '<li class="e-city">工作城市：福建省-福清</li>'
            '<div class="time">发布于: 2026-10-10</div></div>'
            for i in range(start, min(start + 15, 109))
        )
        return (
            '<div>共108个职位</div><li class="page-item" data-pagemax="15" data-pagenum="2"></li>'
            + cards
        )

    @staticmethod
    def title(i: int) -> str:
        unit = "集团总部" if i % 5 == 0 or i in (106, 107) else "苏州厂区"
        return f"研发工程师{i}-2027届校招-{unit}"


def source() -> Source:
    return Source(
        source_id="COM0335",
        company_id="COM0335",
        company="福耀玻璃工业集团股份有限公司",
        url="https://job.fuyaogroup.com/fuyao/position/index?projectId=6a752162d3d9c2792c84e535&recruitmentType=CAMPUSRECRUITMENT",
    )


async def test_fuyao_eight_pages_and_headquarters_scope(tmp_path: Path, now: datetime) -> None:
    session = Session(tmp_path)
    result = await FuyaoHeadquarters(source(), session, now).collect()
    assert not result.coverage_issues()
    scope = result.scopes[0]
    assert (scope.expected, scope.unique, scope.details, scope.skipped_out_of_scope) == (
        108,
        108,
        23,
        85,
    )
    assert len(session.visited) == len(result.jobs) == 23
    assert result.jobs[0].duties == "负责研发"


async def test_fuyao_rejects_application_identity_conflict(tmp_path: Path, now: datetime) -> None:
    result = await FuyaoHeadquarters(source(), Session(tmp_path, conflict=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 22
    assert any(issue.job_key == "5" for issue in result.issues)
