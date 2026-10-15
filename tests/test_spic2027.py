"""Replay SPIC's project, alias identities, tree gap and last page."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.spic2027 import PROJECT, Spic2027
from job_crawler.models import Source

ROOT = "root"
MEMBER = "member"
OUTSIDE = "outside"
FULL_NAME = "国家电投集团山东能源发展有限公司"


class Replay:
    last_evidence = "spic-replay.json"

    def __init__(self, *, unknown_outside: bool = False, duplicate: bool = False):
        self.unknown_outside = unknown_outside
        self.duplicate = duplicate
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://spic2027.iguopin.com/job"
        assert ready_endpoints == ("https://gp-api.iguopin.com/api/jobs/v1/project-job",)

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle.endswith("/info"):
            return {
                "body": json.dumps(
                    {
                        "code": 200,
                        "data": {
                            "company_id": ROOT,
                            "key": "spic2027",
                            "company": {"id": ROOT, "name": "国家电力投资集团有限公司"},
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
                                                "route": "/job1",
                                                "title": "培优计划",
                                                "props": {"projectId": PROJECT},
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
                                "name": "国家电力投资集团有限公司",
                                "all_job_count": 20,
                                "children": [
                                    {
                                        "company_id": MEMBER,
                                        "name": FULL_NAME,
                                        "show_name": "国家电投山东公司",
                                        "short_name": "山东公司",
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
                {"page": 1, "page_size": 20, "source": "s_job_list", "project_id": [PROJECT]}
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
        assert payload is not None and payload["project_id"] == [PROJECT]
        page = int(payload["page"])
        self.pages.append(page)
        indexes = range(1, 21) if page == 1 else [1 if self.duplicate else 21]
        rows = []
        for index in indexes:
            outside = index == 21
            name = (
                ("未知企业" if self.unknown_outside else "青铜峡铝业发电有限责任公司")
                if outside
                else "国家电投山东公司"
            )
            rows.append(
                {
                    "job_id": str(index),
                    "company_id": OUTSIDE if outside else MEMBER,
                    "company_name": name,
                    "company_info": {"name": name if outside else FULL_NAME},
                    "recruitment_type_cn": "校园招聘",
                    "nature_cn": "校招",
                    "status": 1,
                    "job_name": f"研发岗{index}",
                    "contents": "【职责描述】研发工作【任职要求】本科及以上",
                    "district_list": [{"area_cn": "北京"}],
                    "education_cn": "本科",
                    "end_time": "2027-01-01",
                }
            )
        return {"code": 200, "data": {"total": 21, "page": page, "page_size": 20, "list": rows}}


def source() -> Source:
    return Source(
        source_id="COM0068",
        company_id="COM0068",
        company="国家电力投资集团有限公司",
        url="https://spic2027.iguopin.com/job",
    )


async def test_spic_covers_tree_and_outside_project_jobs(now: datetime) -> None:
    replay = Replay()
    result = await Spic2027(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert result.scopes[0].expected == result.scopes[0].details == 21
    assert len(result.jobs) == 21
    assert result.jobs[0].unit == FULL_NAME
    assert result.jobs[-1].unit == "青铜峡铝业发电有限责任公司"
    assert result.jobs[0].published == ""


async def test_spic_unknown_outside_unit_is_incomplete(now: datetime) -> None:
    result = await Spic2027(source(), Replay(unknown_outside=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 20
    assert not result.scopes[0].terminal


async def test_spic_duplicate_last_page_is_incomplete(now: datetime) -> None:
    result = await Spic2027(source(), Replay(duplicate=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 20
