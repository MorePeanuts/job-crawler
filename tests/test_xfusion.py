import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.xfusion import XfusionCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "xfusion-replay.json"

    def __init__(
        self, *, wrong_detail: bool = False, duplicate_leaf: bool = False, bad_page: bool = False
    ):
        self.wrong_detail = wrong_detail
        self.duplicate_leaf = duplicate_leaf
        self.bad_page = bad_page
        self.calls: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://career.xfusion.com/OfficialPortal/#/campusList"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": "https://apig.xfusion.com/api/xJob/xjobpostdeliver/osPostpagelist?pageSize=2&curPage=1&X-HW-ID=site",
            "post_data": json.dumps(
                {
                    "pubChannel": "2",
                    "postTypeList": [],
                    "belongDeptList": [],
                    "workplaceList": [],
                    "recruitNationList": [],
                    "externalNameCH": "",
                    "subChannel": "",
                }
            ),
            "public_headers": {"lang": "zh_CN", "datasource": "6", "x-hw-id": "site"},
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert headers == {"lang": "zh_CN", "datasource": "6", "X-HW-ID": "site"}
        self.calls.append(url)
        if "/osPostpagelist?" in url:
            assert payload is not None and payload["pubChannel"] == "2"
            page = int(parse_qs(urlsplit(url).query)["curPage"][0])
            rows = (
                [
                    {
                        "mainPostId": 10,
                        "postCnt": 2,
                        "postIdKey": 21,
                        "postName": "研发",
                        "jobTypeDesc": "全职",
                    },
                    {
                        "mainPostId": 0,
                        "postCnt": 0,
                        "postIdKey": 23,
                        "postName": "财务",
                        "jobTypeDesc": "全职",
                    },
                ]
                if page == 1
                else [
                    {
                        "mainPostId": 0,
                        "postCnt": 0,
                        "postIdKey": 21 if self.duplicate_leaf else 24,
                        "postName": "法务",
                        "jobTypeDesc": "全职",
                    },
                ]
            )
            return {
                "success": True,
                "code": 200,
                "data": {
                    "pageVO": {
                        "totalRows": 3,
                        "totalPages": 2,
                        "curPage": 1 if self.bad_page else page,
                        "pageSize": 2,
                    },
                    "result": rows,
                },
            }
        if "/mainPostDeliverDetail?" in url:
            assert detail
            return {
                "success": True,
                "code": 200,
                "data": {"postMain": {"id": 10}, "postList": [{"id": 21}, {"id": 22}]},
            }
        post_id = int(parse_qs(urlsplit(url).query)["postId"][0])
        assert detail
        return {
            "success": True,
            "code": 200,
            "data": {
                "id": 999 if self.wrong_detail and post_id == 22 else post_id,
                "postNameCh": f"岗位{post_id}",
                "orgName": "研发部",
                "postTypeDesc": "研发类",
                "workPlaceDesc": "深圳市",
                "firstPubTime": "2026-09-03 08:36:00",
                "postPubChannList": [
                    {
                        "pubChannel": "2",
                        "pubState": "1",
                        "jobType": "1",
                        "jobTypeDesc": "全职",
                        "jobDesc": "研发产品",
                        "jobRequirement": "本科及以上学历",
                    }
                ],
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0285",
        company_id="COM0285",
        company="超聚变数字技术股份有限公司",
        url="https://career.xfusion.com/OfficialPortal/#/campusList",
    )


async def test_xfusion_expands_all_directions_and_pages(now: datetime) -> None:
    replay = Replay()
    result = await XfusionCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert {job.source_key for job in result.jobs} == {"21", "22", "23", "24"}
    assert result.scopes[0].expected == result.scopes[0].details == 3
    assert result.jobs[0].published == "2026-09-03 08:36:00"
    assert result.jobs[0].requirements == "本科及以上学历"
    assert any("curPage=2" in url for url in replay.calls)


async def test_xfusion_detail_mismatch_keeps_partial_results(now: datetime) -> None:
    result = await XfusionCampus(source(), Replay(wrong_detail=True), now).collect()
    assert result.coverage_issues()
    assert {job.source_key for job in result.jobs} == {"21", "23", "24"}
    assert result.scopes[0].details == 2


async def test_xfusion_duplicate_direction_is_incomplete(now: datetime) -> None:
    result = await XfusionCampus(source(), Replay(duplicate_leaf=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 2
    assert {job.source_key for job in result.jobs} == {"21", "22", "23"}


async def test_xfusion_page_number_mismatch_is_incomplete(now: datetime) -> None:
    result = await XfusionCampus(source(), Replay(bad_page=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 2
