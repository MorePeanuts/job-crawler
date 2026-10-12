import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.bankcomm import envelope
from job_crawler.adapters.bilibili import sections
from job_crawler.adapters.meituan import Meituan
from job_crawler.adapters.tencent import graduate_mapping
from job_crawler.models import Collection, Scope, Source


class MeituanReplay:
    last_evidence = "fixture"

    def __init__(self) -> None:
        self.payload = {
            "page": {"pageNo": 1, "pageSize": 10},
            "jobShareType": "1",
            "keywords": "",
            "cityList": [],
            "department": [],
            "jfJgList": [],
            "jobType": [{"code": "4", "subCode": ["1"]}],
            "typeCode": ["1"],
            "specialCode": [],
        }
        self.responses = [
            {
                "url": "https://zhaopin.meituan.com/api/official/job/getJobList",
                "post_data": json.dumps(self.payload),
            }
        ]

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith("/web/position?hiringType=4_1")

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/api/official/job/getJobList"
        return self.responses[0]

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert payload is not None and payload["page"] == {"pageNo": 1, "pageSize": 200}
        return {
            "status": 1,
            "data": {
                "page": {"pageNo": 1, "pageSize": 200, "totalPage": 1, "totalCount": 2},
                "list": [
                    {
                        "jobUnionId": str(i),
                        "jobType": "1",
                        "jobStatus": "000",
                        "name": f"岗位{i}",
                        "jobDuty": "研发软件",
                        "jobRequirement": "本科及以上",
                        "jobFamily": "技术类",
                        "cityList": [{"name": "北京市"}],
                        "firstPostTime": None,
                        "refreshTime": 1790000000000,
                    }
                    for i in (1, 2)
                ],
            },
        }


async def test_meituan_large_page_and_refresh_is_not_publish_time(now: datetime) -> None:
    source = Source(
        source_id="COM0076",
        company_id="COM0076",
        company="美团公司",
        url="https://zhaopin.meituan.com/web/campus",
    )
    result = await Meituan(source, MeituanReplay(), now).collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == 2
    assert all(job.published == "" for job in result.jobs)
    assert result.jobs[0].source_url.endswith("jobUnionId=1&highlightType=campus")


def test_tencent_project_mapping_excludes_internships() -> None:
    payload = {
        "status": 0,
        "data": [
            {"subProjectList": [{"mappingId": 1, "recruitType": 1, "projectName": "校园招聘"}]},
            {"subProjectList": [{"mappingId": 2, "recruitType": 2, "projectName": "日常实习"}]},
            {
                "subProjectList": [
                    {"mappingId": 14, "recruitType": 999, "projectName": "青云计划-应届生"},
                    {"mappingId": 20, "recruitType": 999, "projectName": "青云计划-实习生"},
                ]
            },
        ],
    }
    assert graduate_mapping(payload) == {1: "校园招聘", 14: "青云计划-应届生"}


def test_bilibili_sections_and_unheaded_text() -> None:
    assert sections("工作职责:\n开发软件\n工作要求:\n本科") == ("开发软件", "本科")
    assert sections("开发软件") == ("开发软件", "")


def test_bankcomm_envelope_keeps_public_fields() -> None:
    result = json.loads(envelope({"params": {"positionId": "39068"}}))
    assert result["REQ_BODY"]["params"]["positionId"] == "39068"
    assert result["REQ_HEAD"] == {"TRAN_PROCESS": "", "TRAN_ID": ""}


def test_confirmed_closed_listing_counts_as_accounted_for() -> None:
    scope = Scope(
        name="graduate", expected=2, listed=2, unique=2, details=1, skipped_closed=1, terminal=True
    )
    assert Collection(scopes=[scope]).coverage_issues() == []
