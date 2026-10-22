"""Replay the Xiaohongshu campus catalog's pagination and scope contract."""

import json
from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.xiaohongshu import Xiaohongshu2027
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture:public-campus-page"

    def __init__(self, *, repeated: bool = False, wrong_project: bool = False):
        self.repeated = repeated
        self.wrong_project = wrong_project
        self.calls: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://job.xiaohongshu.com/campus/position"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == Xiaohongshu2027.endpoint
        return {
            "url": f"https://{Xiaohongshu2027.host}{needle}",
            "post_data": json.dumps(
                {
                    "positionName": "",
                    "pageNum": 1,
                    "pageSize": 10,
                    "recruitType": "campus",
                    "jobProjects": ["campus_autumn_27"],
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert url.endswith(Xiaohongshu2027.endpoint)
        assert payload is not None and not detail
        page = payload["pageNum"]
        self.calls.append(page)
        ids = list(range(1, 11)) if page == 1 or self.repeated else [11]
        rows = [
            {
                "positionId": number,
                "positionName": f"【2027校招】研发工程师{number}",
                "workplace": "上海市",
                "publishTime": "2026-10-21",
                "recruitStatus": "in_recruitment",
                "duty": "研发产品",
                "qualification": "本科及以上学历",
                "jobProjectName": "其他项目"
                if self.wrong_project and number == 11
                else "2027 校园招聘",
                "directionName": "研发",
                "subDirectionName": "后端",
            }
            for number in ids
        ]
        return {
            "success": True,
            "statusCode": 200,
            "data": {"pageNum": page, "pageSize": 10, "total": 11, "totalPage": 2, "list": rows},
        }


@pytest.fixture
def source() -> Source:
    return Source(
        source_id="COM0506",
        company_id="COM0506",
        company="小红书",
        url="https://job.xiaohongshu.com/campus/position",
    )


async def test_xiaohongshu_paginates_complete_public_catalog(source: Source, now: datetime) -> None:
    replay = Replay()
    result = await Xiaohongshu2027(source, replay, now).collect()
    assert replay.calls == [1, 2]
    assert not result.coverage_issues()
    assert len(result.jobs) == 11
    assert result.jobs[-1].source_url.endswith("/11")
    assert result.jobs[-1].published == "2026-10-21"
    assert result.jobs[-1].requirements == "本科及以上学历"


@pytest.mark.parametrize("kwargs", [{"repeated": True}, {"wrong_project": True}])
async def test_xiaohongshu_rejects_duplicate_or_wrong_project(
    source: Source, now: datetime, kwargs: dict[str, bool]
) -> None:
    result = await Xiaohongshu2027(source, Replay(**kwargs), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
