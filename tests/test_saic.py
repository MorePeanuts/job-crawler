"""SAIC's shared corporate portal closes its campus list and validates detail identity."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.saic import SaicCampus, SaicImmotors, SaicXiangdao
from job_crawler.models import Source


class Replay:
    last_evidence = "saic-evidence.json"

    def __init__(self, *, wrong_detail: bool = False):
        self.wrong_detail = wrong_detail
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://saic-recruit.saicmotor.com/recruit/pc/#/collegeRecruit"

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle.endswith("/companyList"):
            return {
                "body": json.dumps(
                    {
                        "code": 200,
                        "data": [
                            {"id": f"c{index}", "companyName": f"上汽企业{index}"}
                            for index in range(35)
                        ],
                    }
                )
            }
        assert needle.endswith("/deliver/list")
        return {
            "url": "https://saic-recruit.saicmotor.com/recruit/api/recruit/position/deliver/list",
            "post_data": json.dumps(
                {
                    "posCity": [],
                    "posType": [1, 2],
                    "posTypeIds": [],
                    "companyId": [],
                    "size": 15,
                    "page": 1,
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        if detail:
            job_id = int(url.rsplit("=", 1)[-1])
            return {
                "code": 200,
                "data": {
                    "id": job_id + 1 if self.wrong_detail and job_id == 16 else job_id,
                    "posName": f"校招岗位{job_id}",
                    "posCompanyId": "c0",
                    "posCompanyName": "上汽企业0",
                    "posType": "1",
                    "posDesc": "研发工作",
                    "posRequire": "本科学历",
                    "posMajorTypeName": "汽车类",
                    "posCreatorDate": "2026-10-01 00:00:00",
                },
            }
        assert payload is not None and url.endswith("/deliver/list")
        page = int(payload["page"])
        self.pages.append(page)
        rows = [
            {
                "posId": str(index),
                "posName": f"校招岗位{index}",
                "posCompanyId": "c0",
                "posCompanyName": "上汽企业0",
                "posType": "实习计划" if index == 2 else "校园招聘",
                "posCity": "上海/嘉定区",
                "state": "true",
            }
            for index in range((page - 1) * 15 + 1, min(page * 15, 16) + 1)
        ]
        return {
            "code": 200,
            "data": {"total": 16, "pages": 2, "current": page, "size": 15, "records": rows},
        }


def source() -> Source:
    return Source(
        source_id="COM0036",
        company_id="COM0036",
        company="上海汽车集团股份有限公司",
        url="https://saic-recruit.saicmotor.com/recruit/pc/#/collegeRecruit",
    )


async def test_saic_complete_campus_catalog(now: datetime) -> None:
    replay = Replay()
    result = await SaicCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert result.scopes[0].expected == result.scopes[0].unique == 16
    assert result.scopes[0].skipped_out_of_scope == 1
    assert result.scopes[0].details == len(result.jobs) == 15
    assert all(job.published == "" for job in result.jobs)
    assert all(job.unit == "上汽企业0" for job in result.jobs)


async def test_saic_detail_id_mismatch_marks_partial(now: datetime) -> None:
    result = await SaicCampus(source(), Replay(wrong_detail=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 14


class ScopedReplay(Replay):
    def __init__(self, company_id: str, company_name: str, *, wrong_company: bool = False):
        super().__init__()
        self.company_id = company_id
        self.company_name = company_name
        self.wrong_company = wrong_company

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle.endswith("/companyList"):
            return {
                "body": json.dumps(
                    {
                        "code": 200,
                        "data": [
                            {"id": self.company_id, "companyName": self.company_name},
                            *(
                                {"id": f"other-{i}", "companyName": f"其他公司{i}"}
                                for i in range(34)
                            ),
                        ],
                    }
                )
            }
        return await super().observed(needle)

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        if detail:
            key = int(url.rsplit("=", 1)[-1])
            return {
                "code": 200,
                "data": {
                    "id": key,
                    "posName": f"校招岗位{key}",
                    "posCompanyId": self.company_id,
                    "posCompanyName": self.company_name,
                    "posType": "1",
                    "posDesc": "正式岗位职责",
                    "posRequire": "本科及以上",
                    "posCreatorDate": "2026-10-01 00:00:00",
                },
            }
        assert payload is not None
        assert payload["companyId"] == [self.company_id] and payload["posType"] == [1]
        rows = [
            {
                "posId": str(key),
                "posName": f"校招岗位{key}",
                "posCompanyId": "other" if self.wrong_company and key == 2 else self.company_id,
                "posCompanyName": self.company_name,
                "posType": "校园招聘",
                "posCity": "上海",
                "state": "true",
            }
            for key in (1, 2)
        ]
        return {
            "code": 200,
            "data": {"total": 2, "pages": 1, "current": 1, "size": 15, "records": rows},
        }


async def test_saic_company_scopes_and_rejects_other_company(now: datetime) -> None:
    for adapter in (SaicImmotors, SaicXiangdao):
        selected = Source(
            source_id="COM0538",
            company_id="COM0538",
            company=adapter.company_name,
            url=source().url,
        )
        result = await adapter(
            selected, ScopedReplay(adapter.company_id, adapter.company_name), now
        ).collect()
        assert not result.coverage_issues()
        assert result.scopes[0].expected == result.scopes[0].unique == result.scopes[0].details == 2
        assert all(job.unit == adapter.company_name and job.published == "" for job in result.jobs)
        failed = await adapter(
            selected,
            ScopedReplay(adapter.company_id, adapter.company_name, wrong_company=True),
            now,
        ).collect()
        assert failed.coverage_issues()
