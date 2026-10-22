"""Replay the published AAC Optics campus card boundary."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.aacoptics import AacOpticsCampus
from job_crawler.models import Source


class Page:
    def __init__(self, html: str):
        self.html = html

    async def content(self) -> str:
        return self.html


class Replay:
    last_evidence = "fixture:aacoptics"

    def __init__(self, html: str):
        self.page = Page(html)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://www.aacoptics.com/?page_id=1517"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("static cards do not use an observed API")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("static cards do not use an API request")


def card(key: int, channel: str) -> str:
    return f"""
    <div class="aol-ad-inner-wrapper aol_ad_{key}">
      <div class="panel-heading">产品工程师</div>
      <div class="panel-body"><p>任职资格：本科及以上学历。\n工作职责：开发产品。</p>
      <a href="https://www.aacoptics.com/?aol_career=product">查看详情</a></div>
      <div class="panel-footer">
        <span class="aol-tax-wrapper">分类: 生产运营,</span>
        <span class="aol-tax-wrapper">招聘渠道: {channel},</span>
        <span class="aol-tax-wrapper">城市: 常州,</span>
      </div>
    </div>"""


async def test_aacoptics_counts_all_cards_and_keeps_only_campus(now: datetime) -> None:
    source = Source(
        source_id="COM0594",
        company_id="COM0594",
        company="辰瑞光学",
        url="https://www.aacoptics.com/?page_id=1517",
    )
    html = '<form id="aol_career_form"></form>' + card(11, "校园招聘") + card(12, "社会招聘")
    result = await AacOpticsCampus(source, Replay(html), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == 2
    assert result.scopes[0].skipped_out_of_scope == 1
    assert [job.source_key for job in result.jobs] == ["11"]
    assert result.jobs[0].requirements == "本科及以上学历。"
    assert result.jobs[0].duties == "开发产品。"


async def test_aacoptics_new_pagination_blocks_complete_claim(now: datetime) -> None:
    source = Source(
        source_id="COM0594",
        company_id="COM0594",
        company="辰瑞光学",
        url="https://www.aacoptics.com/?page_id=1517",
    )
    html = '<form id="aol_career_form"></form><div class="aol-pagination"></div>' + card(
        11, "校园招聘"
    )
    result = await AacOpticsCampus(source, Replay(html), now).collect()
    assert result.coverage_issues()
    assert not result.jobs
