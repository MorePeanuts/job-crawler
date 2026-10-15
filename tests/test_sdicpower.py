import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.sdicpower import SdicPowerCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "sdicpower.json"

    def __init__(self, *, foreign_unit: bool = False, changed_total: bool = False):
        self.foreign_unit = foreign_unit
        self.changed_total = changed_total
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://sdicpower.iguopin.com/job-campus"

    async def observed(self, needle: str) -> dict[str, Any]:
        if "/info" in needle:
            body = {
                "code": 200,
                "data": {
                    "key": "sdicpower",
                    "company": {
                        "id": "root",
                        "name": "国投电力控股股份有限公司",
                    },
                },
            }
        elif "/tree" in needle:
            body = {
                "code": 200,
                "data": {
                    "organization_tree": {
                        "company_id": "root",
                        "name": "国投电力控股股份有限公司",
                        "all_job_count": 2,
                        "children": [{"company_id": "child", "name": "成员公司"}],
                    }
                },
            }
        else:
            return {
                "url": "https://gp-api.iguopin.com/api/jobs/v1/list",
                "post_data": json.dumps(
                    {
                        "page": 1,
                        "page_size": 20,
                        "source": "s_job_list",
                        "nature": ["115xW5oQ", "11bTac9", "114Fay7E"],
                        "company_id_with_sub": "root",
                        "sort_scene": 2,
                    }
                ),
            }
        return {"body": json.dumps(body)}

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "include",
    ) -> dict[str, Any]:
        assert credentials == "omit" and payload is not None
        page = int(payload["page"])
        self.pages.append(page)
        company = "outside" if self.foreign_unit else "child"
        return {
            "code": 200,
            "data": {
                "total": 3 if self.changed_total and page == 2 else 2,
                "page": page,
                "page_size": 20,
                "list": [
                    {
                        "job_id": str(page),
                        "job_name": "技术岗",
                        "company_id": company,
                        "company_name": "成员公司",
                        "department_cn": "研发部",
                        "recruitment_type_cn": "校园招聘",
                        "nature_cn": "校招",
                        "status": 1,
                        "contents": "【岗位职责】研发系统\n【任职资格】本科及以上",
                        "education_cn": "本科",
                        "district_list": [{"area_cn": "北京-海淀区"}],
                        "end_time": "2026-12-31 23:59:59",
                    }
                ],
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0299",
        company_id="COM0299",
        company="国投电力控股股份有限公司",
        url="https://sdicpower.iguopin.com/job-campus",
    )


async def test_sdicpower_group_tree_and_full_pages(now: datetime) -> None:
    replay = Replay()
    result = await SdicPowerCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert result.scopes[0].expected == result.scopes[0].details == 2
    assert result.jobs[0].unit == "成员公司 / 研发部"
    assert result.jobs[0].duties == "研发系统"
    assert result.jobs[0].requirements == "本科及以上"
    assert result.jobs[0].published == ""


async def test_sdicpower_foreign_unit_is_incomplete(now: datetime) -> None:
    result = await SdicPowerCampus(source(), Replay(foreign_unit=True), now).collect()
    assert result.coverage_issues()
    assert not result.jobs


async def test_sdicpower_tree_count_change_is_incomplete(now: datetime) -> None:
    result = await SdicPowerCampus(source(), Replay(changed_total=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 1
