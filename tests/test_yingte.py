"""Evidence backed scope and detail checks for the shared Yingte portal."""

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import pytest
from test_adapters import source

from job_crawler.adapters.yingte import LIST_PATH, ORG_PATH, YingteCampus, member_ids


def orgs() -> list[dict[str, str]]:
    return [
        {"id": "100", "parentId": "", "name": "浙江省国际贸易集团有限公司"},
        {"id": "200", "parentId": "100", "name": "浙江英特集团股份有限公司"},
        {"id": "201", "parentId": "200", "name": "药品事业部"},
        {"id": "202", "parentId": "201", "name": "金华英特药业有限公司"},
        {"id": "300", "parentId": "100", "name": "其他集团成员"},
    ]


def row(job_id: int, org: str) -> dict[str, str]:
    return {
        "id": str(job_id),
        "name": f"岗位{job_id}",
        "orgId": org,
        "orgName": "金华英特药业有限公司" if org == "202" else "其他集团成员",
        "endTime": "2027-06-30 00:00:00",
    }


class Replay:
    last_evidence = "offline:yingte"

    def __init__(self, *, wrong_detail: bool = False, drift: bool = False):
        self.wrong_detail = wrong_detail
        self.drift = drift
        self.details: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle == LIST_PATH:
            return {
                "url": f"https://recruit.zibchina.com{LIST_PATH}",
                "post_data": json.dumps(
                    {
                        "pageNo": 1,
                        "pageSize": 1000,
                        "conds": {
                            "channel": 1,
                            "name": None,
                            "orgIds": None,
                            "cityCodes": [],
                            "positionTypes": [],
                            "educations": [],
                            "salarys": [],
                            "experiences": [],
                        },
                    }
                ),
            }
        assert needle == ORG_PATH
        return {"body": json.dumps(orgs())}

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        if urlsplit(url).path == LIST_PATH:
            assert payload is not None and payload["conds"]["channel"] == 1
            assert payload["pageNo"] == 1 and payload["pageSize"] == 50
            return {
                "records": [row(1, "202"), row(2, "300"), row(3, "202")],
                "total": "4" if self.drift else "3",
                "pages": "1",
                "current": "1",
                "size": "50",
            }
        assert detail and payload is None
        job_id = url.rsplit("/", 1)[-1]
        self.details.append(job_id)
        item = row(int(job_id), "202")
        if self.wrong_detail and job_id == "3":
            item["orgId"] = "300"
        return {
            **item,
            "channel": "1,2",
            "duty": "开发医药业务",
            "demand": "大专及以上",
            "status": "进行中",
            "education": "专科",
            "province": "浙江省",
            "city": "金华市",
            "area": "",
            "address": "浙江省金华市某路",
        }


def test_org_scope_uses_ancestry_and_rejects_cycle() -> None:
    assert member_ids(orgs()) == {"200", "201", "202"}
    broken = orgs()
    broken[2]["parentId"] = "202"
    with pytest.raises(Exception, match="循环"):
        member_ids(broken)


async def test_yingte_filters_other_group_companies(now: datetime) -> None:
    replay = Replay()
    result = await YingteCampus(source(YingteCampus.host), replay, now).collect()
    assert not result.coverage_issues()
    assert [job.source_key for job in result.jobs] == ["1", "3"]
    assert replay.details == ["1", "3"]
    assert result.scopes[0].expected == result.scopes[0].details == 2
    assert result.jobs[0].published == ""


async def test_yingte_detail_mismatch_preserves_success(now: datetime) -> None:
    result = await YingteCampus(source(YingteCampus.host), Replay(wrong_detail=True), now).collect()
    assert [job.source_key for job in result.jobs] == ["1"]
    assert result.coverage_issues()


async def test_yingte_count_mismatch_fails_closed(now: datetime) -> None:
    result = await YingteCampus(source(YingteCampus.host), Replay(drift=True), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
