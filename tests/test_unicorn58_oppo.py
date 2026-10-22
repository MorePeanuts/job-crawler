"""Replay OPPO's mixed 2027 campus catalog and project boundaries."""

import json
from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.oppo import Oppo2027
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture:oppo"

    def __init__(self, *, duplicate: bool = False):
        self.duplicate = duplicate
        self.calls: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://careers.oppo.com/university/oppo/campus/post"

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle == Oppo2027.project_endpoint:
            return {
                "body": json.dumps(
                    {
                        "code": 0,
                        "data": [
                            {
                                "idRecruitProject": number,
                                "projectName": name,
                                "recruitmentType": kind,
                            }
                            for number, name, kind in [
                                (29, "2027届寻梦实习招聘", "Intern"),
                                (30, "2027届应届生校园招聘", "Graduate"),
                                (31, "2027届博士生招聘", "doctor"),
                            ]
                        ],
                    }
                )
            }
        assert needle == Oppo2027.list_endpoint
        return {
            "url": f"https://careers.oppo.com{needle}",
            "post_data": json.dumps(
                {
                    "pageNum": 1,
                    "pageSize": 10,
                    "positionName": "",
                    "projectList": [],
                    "positionTypeList": [],
                    "workCityCodeList": [],
                    "shareId": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        page = payload["pageNum"]
        self.calls.append(page)
        numbers = range(1, 11) if page == 1 else [1 if self.duplicate else 11]
        records = []
        for number in numbers:
            project = 29 if number <= 8 else 31 if number == 10 else 30
            name = {
                29: "2027届寻梦实习招聘",
                30: "2027届应届生校园招聘",
                31: "2027届博士生招聘",
            }[project]
            records.append(
                {
                    "idRecruitPosition": number,
                    "projectId": project,
                    "projectName": name,
                    "recruitmentType": {29: "Intern", 30: "Graduate", 31: "doctor"}[project],
                    "positionStatus": 0,
                    "positionName": f"工程师{number}",
                    "positionDesc": "开发产品",
                    "knowledgeSkill": "本科及以上",
                    "workCityName": "深圳市",
                    "releaseTime": "2026-10-21",
                    "positionTypeName": "研发类",
                }
            )
        return {
            "code": 0,
            "data": {"total": 11, "pages": 2, "current": page, "size": 10, "records": records},
        }


@pytest.fixture
def source() -> Source:
    return Source(
        source_id="COM0507",
        company_id="COM0507",
        company="Oppo",
        url="https://careers.oppo.com/university/oppo/campus/post",
    )


async def test_oppo_enumerates_both_regular_projects_and_excludes_internships(
    source: Source, now: datetime
) -> None:
    replay = Replay()
    result = await Oppo2027(source, replay, now).collect()
    assert replay.calls == [1, 2]
    assert not result.coverage_issues()
    assert result.scopes[0].expected == 11
    assert result.scopes[0].skipped_out_of_scope == 8
    assert [job.source_key for job in result.jobs] == ["9", "10", "11"]
    assert result.jobs[-1].published == "2026-10-21"


async def test_oppo_duplicate_page_cannot_be_complete(source: Source, now: datetime) -> None:
    result = await Oppo2027(source, Replay(duplicate=True), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
