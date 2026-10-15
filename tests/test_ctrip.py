import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.ctrip import CtripCampus, split_ctrip_body
from job_crawler.models import Source


class Replay:
    last_evidence = "ctrip-page.json"

    def __init__(self, *, repeated: bool = False, filtered: bool = False):
        self.repeated = repeated
        self.filtered = filtered
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://careers.ctrip.com/#/campus/jobList?kind=1"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": "https://careers.ctrip.com/api/hrrecruit/getJobAd",
            "post_data": json.dumps(
                {
                    "condition": {
                        "fromId": [],
                        "keyword": "",
                        "kind": ["1"],
                        "country": [],
                        "city": ["CO0009"] if self.filtered else [],
                        "bucode": [],
                        "jobFamilyCode": [],
                        "jobFamilyGroupCode": [],
                        "category": 2,
                    },
                    "pager": {"index": "1", "size": "10"},
                    "head": {"language": "zh_CN", "version": "1"},
                }
            ),
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert payload is not None and payload["condition"]["kind"] == ["1"]
        page = int(payload["pager"]["index"])
        self.pages.append(page)
        start = 0 if self.repeated else (page - 1) * 10
        return {
            "retCode": "201",
            "retValue": {
                "total": 11,
                "recruitJobAdList": [
                    {
                        "id": str(i),
                        "fromId": f"MJ{i}",
                        "jobTitle": f"研发工程师{i}",
                        "kind": "1",
                        "kindName": "应届校招生",
                        "category": "2",
                        "buName": "Trip.com Group",
                        "jobFamilyGroupName": "研发",
                        "cityName": "上海",
                        "publishDate": "2026-10-12",
                        "requirements": "<p>招聘对象：2027届</p><p>你将会负责：</p><p>研发系统</p><p>我们期望你：</p><p>本科及以上</p>",
                    }
                    for i in range(start, min(start + 10, 11))
                ],
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0276",
        company_id="COM0276",
        company="携程集团有限公司",
        url="https://careers.ctrip.com/#/campus/jobList?kind=1",
    )


async def test_ctrip_complete_grad_catalog(now: datetime) -> None:
    replay = Replay()
    result = await CtripCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert result.scopes[0].expected == result.scopes[0].details == 11
    assert result.jobs[0].duties == "研发系统"
    assert result.jobs[0].requirements == "招聘对象：2027届\n本科及以上"
    assert result.jobs[0].source_url.endswith("/MJ0")


async def test_ctrip_repeated_page_is_incomplete(now: datetime) -> None:
    result = await CtripCampus(source(), Replay(repeated=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 10


async def test_ctrip_filtered_entry_is_incomplete(now: datetime) -> None:
    result = await CtripCampus(source(), Replay(filtered=True), now).collect()
    assert result.coverage_issues()
    assert not result.jobs


def test_ctrip_unheaded_body_remains_uninvented() -> None:
    assert split_ctrip_body("<p>参与研发</p>") == ("参与研发", "")
