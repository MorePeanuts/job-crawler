"""Replay the bounded 52-card Eastern Airlines campus catalog."""

import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs

from job_crawler.adapters.ceair import ROOT, Ceair2027
from job_crawler.models import Source


class Replay:
    last_evidence = "entry.json"

    def __init__(self) -> None:
        self.units = [
            {
                "PD_PDID": 11,
                "PD_DEPTID": 11,
                "PD_Name": "东航股份北京分公司",
                "PD_GroupName": "东航股份分公司",
            },
            {
                "PD_PDID": 12,
                "PD_DEPTID": 12,
                "PD_Name": "业务运营中心",
                "PD_GroupName": "业务运营单位",
            },
            {
                "PD_PDID": 80,
                "PD_DEPTID": 80,
                "PD_Name": "东航子公司",
                "PD_GroupName": "东航股份子公司",
            },
            {
                "PD_PDID": 104,
                "PD_DEPTID": None,
                "PD_Name": "公共事务中心",
                "PD_GroupName": "总部管理支持部门",
            },
        ]
        self.rows: list[dict[str, Any]] = []
        for i in range(52):
            dept = 11 if i < 24 else 12 if i < 33 else 80 if i < 47 else 110
            name = {
                11: "东航股份北京分公司",
                12: "业务运营中心",
                80: "东航子公司",
                110: "东航股份/东航物流",
            }[dept]
            self.rows.append(
                {
                    "zp_ActiveInfoID": 5600 + i,
                    "zp_NewsInfoID": 5800 + i,
                    "News_DeptID": dept,
                    "PD_Name": name,
                    "Active_Name": f"27年度秋招-岗位{i}",
                    "Active_Status": 2,
                    "News_CategoryId": 4000,
                    "PC_Name": "市场营销",
                }
            )
        self.api = ROOT + "/Ashx/Campus.ashx?active=GetPositionListByParams&r=1"
        self.detail_api = ROOT + "/Ashx/Campus.ashx?active=GetPositionDetailListByPosID&r=1"
        self.current_id: int | None = None
        self.fail_id: int | None = None
        self.pages: list[int] = []

    async def observed(self, needle: str) -> dict[str, Any]:
        if "GetPositionListByParams" in needle:
            self.last_evidence = "list-observed.json"
            return {
                "url": self.api,
                "post_data": "pageIndex=1&pageSize=6&positionName=&workCity=&cateId=&deptId=&banKuaiId=4000",
            }
        if "GetDeptList" in needle:
            self.last_evidence = "tree.json"
            return {"body": json.dumps({"msg": "ok", "data": self.units})}
        assert self.current_id is not None
        self.last_evidence = "first-detail.json"
        return {"url": self.detail_api, "body": json.dumps(self.detail(self.current_id))}

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        if url == ROOT + "/campus/campusJobList.html":
            self.last_evidence = "entry.json"
            return
        assert url.startswith(ROOT + "/JobDetail.html?")
        import base64
        from urllib.parse import urlsplit

        encoded = parse_qs(urlsplit(url).query)["positionId"][0]
        self.current_id = int(base64.b64decode(encoded))
        self.last_evidence = "detail-page.json"

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert payload is None and form is not None
        if not detail:
            assert url == self.api
            assert form["banKuaiId"] == "4000" and form["pageSize"] == "6"
            page = int(form["pageIndex"])
            self.pages.append(page)
            self.last_evidence = f"list-{page}.json"
            return {"total": len(self.rows), "data": self.rows[(page - 1) * 6 : page * 6]}
        assert url == self.detail_api
        position_id = int(form["positionId"])
        self.last_evidence = f"detail-{position_id}.json"
        return self.detail(position_id)

    def detail(self, position_id: int) -> dict[str, Any]:
        row = self.rows[position_id - 5600]
        data = {
            **row,
            "Active_PosDesc": "<p>【职位描述】</p><p>市场销售</p><p>【招聘条件】</p><p>本科及以上学历</p>",
            "News_CreateDate": "/Date(1791820800000)/",
            "Active_EndTime": "/Date(1793462399000)/",
            "Active_WorkAddress": "北京",
        }
        if position_id == self.fail_id:
            data["zp_NewsInfoID"] = -1
        return {"msg": "ok", "data": data}


def source() -> Source:
    return Source(
        source_id="COM0170",
        company_id="COM0170",
        company="中国东方航空股份有限公司",
        url=ROOT + "/campus/campusJobList.html",
    )


async def test_ceair_52_cards_nine_pages_and_legal_group_boundary(now: datetime) -> None:
    replay = Replay()
    result = await Ceair2027(source(), replay, now).collect()
    scope = result.scopes[0]
    assert result.coverage_issues() == []
    assert replay.pages == list(range(1, 10))
    assert (scope.expected, scope.unique, scope.details, scope.skipped_out_of_scope) == (
        52,
        52,
        33,
        19,
    )
    assert len(result.jobs) == 33
    assert all(job.company == "中国东方航空股份有限公司" for job in result.jobs)
    assert all(
        job.published and job.deadline and job.duties and job.requirements for job in result.jobs
    )
    assert {job.unit for job in result.jobs} == {"东航股份北京分公司", "业务运营中心"}


async def test_ceair_detail_identity_failure_keeps_other_jobs(now: datetime) -> None:
    replay = Replay()
    replay.fail_id = 5601
    result = await Ceair2027(source(), replay, now).collect()
    assert len(result.jobs) == 32
    assert result.coverage_issues()
    assert result.scopes[0].terminal


async def test_ceair_rejects_duplicate_list_id_and_unknown_organization(now: datetime) -> None:
    replay = Replay()
    replay.rows[2]["zp_ActiveInfoID"] = replay.rows[1]["zp_ActiveInfoID"]
    duplicate = await Ceair2027(source(), replay, now).collect()
    assert duplicate.coverage_issues()

    replay = Replay()
    replay.rows[0]["News_DeptID"] = 999
    unknown = await Ceair2027(source(), replay, now).collect()
    assert unknown.coverage_issues()
