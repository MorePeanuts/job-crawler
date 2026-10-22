"""Replay Mihoyo's 2027 project pagination and detail identity checks."""

import json
from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.mihoyo import Mihoyo2027
from job_crawler.models import Source


class Page:
    def __init__(self, session: "Replay"):
        self.session = session

    async def evaluate(self, script: str) -> dict[str, Any]:
        key = self.session.opened.rsplit("/", 1)[-1]
        return {
            "url": self.session.opened,
            "title": "错误职位" if self.session.wrong_title and key == "11" else f"职位{key}",
            "sections": [
                {"heading": "工作职责", "body": "开发产品"},
                {"heading": "任职要求", "body": "本科及以上"},
                {"heading": "面向对象", "body": "2027届毕业生"},
            ],
        }


class Replay:
    last_evidence = "fixture:mihoyo"

    def __init__(self, *, wrong_title: bool = False):
        self.wrong_title = wrong_title
        self.opened = ""
        self.calls: list[int] = []
        self.page = Page(self)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opened = url

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == Mihoyo2027.endpoint
        return {
            "url": "https://ats.openout.mihoyo.com/ats-portal/v1/job/list",
            "post_data": json.dumps(
                {
                    "jobName": "",
                    "projectIds": ["13"],
                    "pageNo": 1,
                    "pageSize": 10,
                    "channelDetailIds": [1],
                    "hireType": 1,
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        page = payload["pageNo"]
        self.calls.append(page)
        numbers = range(1, 11) if page == 1 else [11]
        return {
            "code": 0,
            "success": True,
            "data": {
                "pageNo": page,
                "pageSize": 10,
                "total": 11,
                "list": [
                    {
                        "id": str(number),
                        "title": f"职位{number}",
                        "projectName": "2027届秋招",
                        "jobNature": "全职",
                        "jobNatureId": 1,
                        "objectName": "2027届毕业生",
                        "addressDetailList": [{"addressDetail": "上海"}],
                        "competencyType": "程序&技术类",
                    }
                    for number in numbers
                ],
            },
        }


@pytest.fixture
def source() -> Source:
    return Source(
        source_id="COM0509",
        company_id="COM0509",
        company="米哈游",
        url="https://jobs.mihoyo.com/#/campus/position?jobName=&projectIds%5B0%5D=13",
    )


async def test_mihoyo_completes_project_and_preserves_missing_date(
    source: Source, now: datetime
) -> None:
    replay = Replay()
    result = await Mihoyo2027(source, replay, now).collect()
    assert replay.calls == [1, 2]
    assert not result.coverage_issues()
    assert len(result.jobs) == 11
    assert result.jobs[-1].source_key == "11"
    assert result.jobs[-1].published == ""
    assert result.jobs[-1].requirements == "本科及以上"


async def test_mihoyo_detail_title_mismatch_keeps_partial_coverage(
    source: Source, now: datetime
) -> None:
    result = await Mihoyo2027(source, Replay(wrong_title=True), now).collect()
    assert len(result.jobs) == 10
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
