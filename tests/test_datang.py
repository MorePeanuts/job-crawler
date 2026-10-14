"""Replay Datang's announcement and employing-unit boundary."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.datang import GROUP, ROOT, Datang2027
from job_crawler.models import Source


class Replay:
    last_evidence = "entry.json"

    def __init__(self) -> None:
        names = [
            GROUP + "宁夏分公司",
            GROUP + "江西分公司",
            GROUP + "浙江分公司",
            GROUP,
            GROUP,
            GROUP,
            GROUP + "辽宁分公司",
            GROUP + "重庆分公司",
            GROUP + "福建分公司",
            GROUP,
            GROUP + "广东分公司",
        ]
        self.notices = [
            {
                "applyId": f"notice-{i}",
                "organName": name,
                "applyName": GROUP
                + (
                    "2027年在京二级单位本部管培生"
                    if i in {3, 4, 5}
                    else f"{name}2027年高校毕业生招聘公告"
                ),
                "postNumCount": 0 if i == 9 else 2,
            }
            for i, name in enumerate(names)
        ]
        self.notices += [
            {
                "applyId": f"outside-{i}",
                "organName": f"独立子公司{i}有限公司",
                "applyName": f"子公司{i}校招公告",
                "postNumCount": 1,
            }
            for i in range(33)
        ]
        self.bad_id: str | None = None
        self.calls: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == ROOT + "/zpgg_xyzp.html"
        self.last_evidence = "entry.json"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/apply/notice/xyzpHomeInfo"
        self.last_evidence = "listing.json"
        return {
            "post_data": json.dumps({"data": json.dumps({"keyWord": ""})}),
            "body": json.dumps(
                {"code": "10000", "data": json.dumps({"total": "44", "list": self.notices})}
            ),
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert url == ROOT + "/apply/notice/findInfo" and payload is not None
        notice_id = json.loads(payload["data"])["id"]
        self.calls.append(notice_id)
        self.last_evidence = notice_id + ".json"
        notice = next(n for n in self.notices if n["applyId"] == notice_id)
        rows = []
        if notice_id != "notice-9":
            unit = notice["organName"]
            if notice_id == "notice-0":
                unit = "大唐宁夏分公司新能源事业部"
            elif notice_id == "notice-6":
                unit = GROUP + "辽宁分公司新能源事业部"
            for i in range(2):
                employer = (
                    unit
                    if i == 0 and notice_id not in {"notice-1", "notice-2", "notice-8", "notice-10"}
                    else f"子公司{i}有限公司"
                )
                rows.append(
                    {
                        "applyId": "subnotice-0" if notice_id == "notice-0" else notice_id,
                        "bringId": f"job-{notice_id}-{i}",
                        "organName": unit,
                        "ownOrganName": employer,
                        "remark": "福建独立公司" if notice_id == "notice-8" else None,
                        "post": "生产管理岗",
                        "specialName": "电气工程",
                        "postDuty": "负责设备运行",
                        "postDemand": "本科及以上学历",
                        "educationBackground": "大学本科",
                        "workPlace": "重庆市",
                        "psTypeName": "生产一线岗位",
                    }
                )
        if self.bad_id == notice_id and rows:
            rows[0]["applyId"] = ""
        return {
            "code": "10000",
            "data": json.dumps(
                {
                    "applyId": notice_id,
                    "applyName": notice["applyName"],
                    "applyPublicTime": "2026-09-24 16:26:19",
                    "endDate": "2026-10-31",
                    "details": rows,
                }
            ),
        }


def source() -> Source:
    return Source(
        source_id="COM0111",
        company_id="COM0111",
        company=GROUP,
        url=ROOT + "/zpgg_xyzp.html?random=1790467200101",
    )


async def test_datang_44_notices_and_branch_employer_boundary(now: datetime) -> None:
    replay = Replay()
    result = await Datang2027(source(), replay, now).collect()
    assert result.coverage_issues() == []
    assert len(replay.calls) == 11
    assert result.scopes[0].expected == result.scopes[0].unique == 44
    assert len(result.jobs) == 3
    assert {j.unit for j in result.jobs} == {
        "大唐宁夏分公司新能源事业部",
        GROUP + "辽宁分公司新能源事业部",
        GROUP + "重庆分公司",
    }
    assert all(j.published == "2026-09-24" and j.deadline == "2026-10-31" for j in result.jobs)


async def test_datang_notice_identity_failure_is_partial(now: datetime) -> None:
    replay = Replay()
    replay.bad_id = "notice-7"
    result = await Datang2027(source(), replay, now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 2


async def test_datang_rejects_duplicate_notice_id(now: datetime) -> None:
    replay = Replay()
    replay.notices[1]["applyId"] = replay.notices[0]["applyId"]
    result = await Datang2027(source(), replay, now).collect()
    assert result.coverage_issues()
