"""Replay Wind's server-rendered 2027 project and status checks."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.wind import Wind2027
from job_crawler.models import Source


class Page:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    async def content(self) -> str:
        data = {
            "props": {
                "pageProps": {
                    "locale": {
                        "notice": [{"title": "2027年校园招聘", "id": "school"}],
                        "channelPositions": self.rows,
                    }
                }
            }
        }
        return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


class Replay:
    last_evidence = "fixture:wind"

    def __init__(self, rows: list[dict[str, Any]]):
        self.page = Page(rows)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://www.wind.com.cn/mobile/JoinUS/RecruitDetail/zh.html?entry=school"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("Wind uses server-rendered job data")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("Wind uses server-rendered job data")


def row(key: int, project: str, *, closed: bool = False) -> dict[str, Any]:
    return {
        "ChannelPositionID": key,
        "ChannelPositionName": "平面设计师",
        "Projects": [{"Name": project}],
        "PositionTypeText": "校招" if project == "2027年校园招聘" else "社招",
        "InUse": True,
        "ExpireFlag": closed,
        "Source": [{"Name": "Wind官网"}],
        "ChannelPositionDesc": "设计产品",
        "ChannelPositionRequirement": "本科及以上学历",
        "WorkPlace": [{"Name": "上海"}],
        "PositionClassName": "设计类",
        "PublishDate": "2025-05-23 00:00:00.0000",
    }


def source() -> Source:
    return Source(
        source_id="COM0535",
        company_id="COM0535",
        company="万得",
        url="https://www.wind.com.cn/mobile/JoinUS/RecruitDetail/zh.html?entry=school",
    )


async def test_wind_keeps_old_source_date_and_only_2027_project(now: datetime) -> None:
    result = await Wind2027(
        source(), Replay([row(1204, "2027年校园招聘"), row(2, "实习生招聘")]), now
    ).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == 2
    assert result.scopes[0].skipped_out_of_scope == 1
    assert len(result.jobs) == 1
    assert result.jobs[0].published == "2025-05-23 00:00:00.0000"
    assert result.jobs[0].source_url.endswith("ChannelPositionID=1204")


async def test_wind_closed_2027_job_blocks_complete_claim(now: datetime) -> None:
    result = await Wind2027(
        source(), Replay([row(1204, "2027年校园招聘", closed=True)]), now
    ).collect()
    assert result.coverage_issues()
    assert not result.jobs
