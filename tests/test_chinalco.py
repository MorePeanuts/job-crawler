"""Replay Chinalco's public project, member tree and full pagination contract."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.chinalco import PROJECT, Chinalco2027
from job_crawler.models import Source

ROOT = "10685286989326120"
CHILD = "10685286989326121"


class Replay:
    last_evidence = "chinalco-evidence.json"

    def __init__(self, *, wrong_unit: bool = False):
        self.wrong_unit = wrong_unit
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://chinalco2027.iguopin.com/job"
        assert ready_endpoints == ("https://gp-api.iguopin.com/api/jobs/v1/project-job",)

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle.endswith("/info"):
            return {
                "body": json.dumps(
                    {
                        "code": 200,
                        "data": {
                            "company_id": ROOT,
                            "key": "chinalco2027",
                            "company": {"id": ROOT, "name": "中国铝业集团有限公司"},
                            "content": json.dumps(
                                {
                                    "params": {
                                        "nav": [
                                            {
                                                "route": "/job",
                                                "title": "校园招聘",
                                                "props": {"projectId": PROJECT},
                                            },
                                            {
                                                "route": "/job2",
                                                "props": {"projectId": "195434479274167937"},
                                            },
                                        ]
                                    }
                                }
                            ),
                        },
                    }
                )
            }
        if needle.endswith("/project-company"):
            return {
                "post_data": json.dumps({"project_ids": [PROJECT], "show_all_company": 0}),
                "body": json.dumps(
                    {
                        "code": 200,
                        "data": {
                            "list": {
                                "company_id": ROOT,
                                "name": "中国铝业集团有限公司",
                                "all_job_count": 21,
                                "children": [
                                    {
                                        "company_id": CHILD,
                                        "name": "中铝测试成员企业",
                                        "children": [],
                                    }
                                ],
                            }
                        },
                    }
                ),
            }
        assert needle.endswith("/project-job")
        return {
            "url": "https://gp-api.iguopin.com/api/jobs/v1/project-job",
            "post_data": json.dumps(
                {
                    "page": 1,
                    "page_size": 20,
                    "source": "s_job_list",
                    "company_id_with_sub": ROOT,
                    "project_id": [PROJECT],
                }
            ),
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "omit",
    ) -> dict[str, Any]:
        assert url.endswith("/project-job") and credentials == "omit" and not detail
        assert payload is not None
        assert payload["project_id"] == [PROJECT] and payload["company_id_with_sub"] == ROOT
        page = int(payload["page"])
        self.pages.append(page)
        indexes = range(1, 21) if page == 1 else range(21, 22)
        return {
            "code": 200,
            "data": {
                "total": 21,
                "page": page,
                "page_size": 20,
                "list": [
                    {
                        "job_id": str(index),
                        "company_id": CHILD,
                        "company_name": "错误单位"
                        if self.wrong_unit and index == 21
                        else "中铝测试成员企业",
                        "recruitment_type_cn": "校园招聘",
                        "nature_cn": "校招",
                        "status": 1,
                        "job_name": f"研发岗{index}",
                        "contents": "【职责描述】研发工作【任职要求】本科及以上",
                        "district_list": [{"area_cn": "北京"}],
                        "education_cn": "本科",
                        "end_time": "2027-01-01",
                    }
                    for index in indexes
                ],
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0051",
        company_id="COM0051",
        company="中国铝业集团有限公司",
        url="https://chinalco2027.iguopin.com/job",
    )


async def test_chinalco_full_member_catalog(now: datetime) -> None:
    replay = Replay()
    result = await Chinalco2027(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert len(result.jobs) == 21
    assert result.scopes[0].expected == result.scopes[0].details == 21
    assert result.jobs[0].unit == "中铝测试成员企业"
    assert result.jobs[0].published == ""


async def test_chinalco_rejects_unknown_member(now: datetime) -> None:
    result = await Chinalco2027(source(), Replay(wrong_unit=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 20
    assert not result.scopes[0].terminal
