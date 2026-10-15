"""Replay the two independently scoped Guopin campus project tenants."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.iguopin_projects import Ceec2027, Cosco2027, GuopinProjectCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "guopin-project-replay.json"

    def __init__(
        self, tenant: type[GuopinProjectCampus], *, wrong_unit: bool = False, filtered: bool = False
    ):
        self.tenant = tenant
        self.wrong_unit = wrong_unit
        self.filtered = filtered
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == f"https://{self.tenant.host}/job"
        assert ready_endpoints == ("https://gp-api.iguopin.com/api/jobs/v1/project-job",)

    async def observed(self, needle: str) -> dict[str, Any]:
        tenant = self.tenant
        if needle.endswith("/info"):
            return {
                "body": json.dumps(
                    {
                        "code": 200,
                        "data": {
                            "key": tenant.campaign_key,
                            "company_id": tenant.campaign_company_id,
                            "company": {
                                "id": tenant.campaign_company_id,
                                "name": tenant.campaign_company,
                            },
                            "content": json.dumps(
                                {
                                    "params": {
                                        "nav": [
                                            {
                                                "route": "/job",
                                                "title": tenant.nav_title,
                                                "props": {"projectId": tenant.project_id},
                                            }
                                        ]
                                    }
                                }
                            ),
                        },
                    }
                )
            }
        if needle.endswith("/project-company"):
            payload: dict[str, object] = {"project_ids": [tenant.project_id], "show_all_company": 0}
            if tenant.nature_codes:
                payload["job_nature"] = list(tenant.nature_codes)
            return {
                "post_data": json.dumps(payload),
                "body": json.dumps(
                    {
                        "code": 200,
                        "data": {
                            "list": {
                                "company_id": tenant.campaign_company_id,
                                "name": tenant.campaign_company,
                                "all_job_count": 21,
                                "children": [
                                    {"company_id": "member", "name": "校招成员企业", "children": []}
                                ],
                            }
                        },
                    }
                ),
            }
        assert needle.endswith("/project-job")
        payload = {
            "page": 1,
            "page_size": 20,
            "source": "s_job_list",
            "project_id": [tenant.project_id],
        }
        if tenant.nature_codes:
            payload["nature"] = list(tenant.nature_codes)
            payload["company_id_with_sub"] = tenant.campaign_company_id
        if self.filtered:
            payload["keyword"] = "仅部分岗位"
        return {
            "url": "https://gp-api.iguopin.com/api/jobs/v1/project-job",
            "post_data": json.dumps(payload),
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "omit",
    ) -> dict[str, Any]:
        assert url.endswith("/project-job") and not detail and credentials == "omit"
        assert payload is not None
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
                        "company_id": "member",
                        "company_name": "错误企业"
                        if self.wrong_unit and index == 21
                        else "校招成员企业",
                        "company_info": {"name": "校招成员企业"},
                        "recruitment_type_cn": "校园招聘",
                        "nature_cn": "校招",
                        "status": 1,
                        "job_name": f"研发岗{index}",
                        "contents": "【职责描述】研发工作【任职要求】本科以上",
                        "district_list": [{"area_cn": "北京"}],
                        "education_cn": "本科",
                        "end_time": "2027-01-01",
                    }
                    for index in indexes
                ],
            },
        }


def source(tenant: type[GuopinProjectCampus]) -> Source:
    source_id, company = (
        ("COM0059", "中国能源建设集团有限公司")
        if tenant is Ceec2027
        else ("COM0060", "中国远洋海运集团有限公司")
    )
    return Source(
        source_id=source_id, company_id=source_id, company=company, url=f"https://{tenant.host}/job"
    )


async def test_iguopin_project_tenants_close_all_pages(now: datetime) -> None:
    for tenant in (Ceec2027, Cosco2027):
        replay = Replay(tenant)
        result = await tenant(source(tenant), replay, now).collect()
        assert not result.coverage_issues()
        assert replay.pages == [1, 2]
        assert len(result.jobs) == 21
        assert result.scopes[0].expected == result.scopes[0].details == 21
        assert result.jobs[0].published == ""


async def test_iguopin_project_rejects_unknown_member(now: datetime) -> None:
    result = await Cosco2027(source(Cosco2027), Replay(Cosco2027, wrong_unit=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 20
    assert not result.scopes[0].terminal


async def test_iguopin_project_rejects_local_filter(now: datetime) -> None:
    result = await Ceec2027(source(Ceec2027), Replay(Ceec2027, filtered=True), now).collect()
    assert result.coverage_issues()
    assert not result.jobs
