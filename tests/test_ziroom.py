"""Ziroom campus cards are all expanded and tied to their listing identity."""

from datetime import datetime
from pathlib import Path
from typing import Any, cast

from job_crawler.adapters.ziroom import ZiroomCampus
from job_crawler.models import Source
from job_crawler.transport import Session as TransportSession


class Locator:
    def __init__(self, page: "Page") -> None:
        self.page = page
        self.index = 0

    def nth(self, index: int) -> "Locator":
        self.index = index
        return self

    def locator(self, selector: str) -> "Locator":
        assert selector == ".profile"
        return self

    async def click(self, *, timeout: int) -> None:  # noqa: ASYNC109 - Playwright signature
        self.page.opened.add(self.index)


class Page:
    def __init__(self, mismatch: bool = False) -> None:
        self.mismatch = mismatch
        self.opened: set[int] = set()

    def locator(self, selector: str) -> Locator:
        assert selector == "div.list > ul > li"
        return Locator(self)

    async def evaluate(self, script: str, index: int | None = None) -> dict[str, Any]:
        if index is None:
            return {
                "expected": 2,
                "rows": [
                    {"title": "管家-2027秋招", "location": "北京市"},
                    {"title": "客户管家-2027秋招", "location": "上海市"},
                ],
            }
        assert index in self.opened
        return {
            "title": "错配"
            if self.mismatch and index == 1
            else ("管家-2027秋招" if index == 0 else "客户管家-2027秋招"),
            "text": (
                "【岗位职责】\n客户服务\n【岗位要求】\n本科学历\n立即投递"
                if index == 0
                else "岗位职责：\n客户服务\n任职资格：\n本科学历\n立即投递"
            ),
        }


class Session:
    last_evidence = "listing"

    def __init__(self, output: Path, mismatch: bool = False) -> None:
        self.output = output
        self.page = Page(mismatch)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://job.ziroom.com/campus/enter"

    def consume_request(self) -> None:
        pass


def source() -> Source:
    return Source(
        source_id="COM0550",
        company_id="COM0550",
        company="自如",
        url="https://job.ziroom.com/campus/enter",
    )


async def test_ziroom_expand_all_campus_cards(tmp_path: Path, now: datetime) -> None:
    session = Session(tmp_path)
    result = await ZiroomCampus(source(), cast(TransportSession, session), now).collect()
    assert not result.coverage_issues()
    assert session.page.opened == {0, 1}
    assert result.scopes[0].expected == result.scopes[0].unique == 2
    assert len(result.jobs) == 2
    assert result.jobs[0].duties == "客户服务"
    assert result.jobs[0].requirements == "本科学历"
    assert not result.jobs[0].published


async def test_ziroom_rejects_expanded_identity_mismatch(tmp_path: Path, now: datetime) -> None:
    result = await ZiroomCampus(
        source(), cast(TransportSession, Session(tmp_path, mismatch=True)), now
    ).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 1
