"""Replay the two campus catalogs' pagination and source date semantics."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.duoyi import DuoyiCampus
from job_crawler.adapters.skywell import SkywellCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture:catalog"

    def __init__(self, kind: str):
        self.kind = kind
        self.calls: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert "duoyi.com" in url if self.kind == "duoyi" else "skywellcorp.com" in url

    async def observed(self, needle: str) -> dict[str, Any]:
        if self.kind == "duoyi":
            assert needle == DuoyiCampus.endpoint
            return {
                "url": "https://sz.duoyi.com/v40/api/index/positions/jds/page?pageIndex=1&pageSize=15&recruit=10"
            }
        assert needle == SkywellCampus.endpoint
        return {
            "url": "https://www.skywellcorp.com/api/recruit/list",
            "post_data": json.dumps(
                {
                    "pageNo": 1,
                    "pageSize": 10,
                    "langType": 1,
                    "type": "2",
                    "departIds": [],
                    "cityCodes": [],
                    "title": "",
                    "total": 0,
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        if self.kind == "duoyi":
            from urllib.parse import parse_qs, urlsplit

            page = int(parse_qs(urlsplit(url).query)["pageIndex"][0])
            self.calls.append(page)
            numbers = range(1, 16) if page == 1 else [16]
            return {
                "code": 0,
                "data": {
                    "pageIndex": page,
                    "pageSize": 15,
                    "total": 16,
                    "list": [
                        {
                            "id": str(number),
                            "category": "SCHOOL",
                            "outerNature": ["实习"] if number == 1 else ["正式"],
                            "name": f"程序员{number}",
                            "jobResponsibility": "" if number == 2 else "开发产品",
                            "jobRequirements": "本科及以上",
                            "workPlaces": ["广州"],
                            "outerType": "程序类",
                            "publishDate": "2026-10-19",
                        }
                        for number in numbers
                    ],
                },
            }
        assert payload is not None
        page = payload["pageNo"]
        self.calls.append(page)
        numbers = range(1, 11) if page == 1 else [11]
        return {
            "success": True,
            "code": 200,
            "result": {
                "total": 11,
                "pages": 2,
                "current": page,
                "size": 10,
                "records": [
                    {
                        "id": number,
                        "type": 2,
                        "langType": 1,
                        "status": 1,
                        "title": f"工程师{number}",
                        "description": "研发产品",
                        "requirements": "本科及以上",
                        "degree": "本科",
                        "workAddress": "南京市",
                        "updateTime": "2025-01-16 09:57:52",
                        "createTime": "2024-09-23 17:57:16",
                    }
                    for number in numbers
                ],
            },
        }


async def test_duoyi_excludes_interns_and_reaches_last_page(now: datetime) -> None:
    source = Source(
        source_id="COM0558",
        company_id="COM0558",
        company="多益网络",
        url="https://sz.duoyi.com/v40/#/positions?recruit=10",
    )
    replay = Replay("duoyi")
    result = await DuoyiCampus(source, replay, now).collect()
    assert replay.calls == [1, 2]
    assert not result.coverage_issues()
    assert result.scopes[0].skipped_out_of_scope == 1
    assert len(result.jobs) == 15
    assert result.jobs[0].published == "2026-10-19"
    assert result.jobs[0].duties == "" and result.warnings[0].job_key == "2"


async def test_skywell_uses_neither_update_nor_creation_as_publication(now: datetime) -> None:
    source = Source(
        source_id="COM0666",
        company_id="COM0666",
        company="开沃汽车",
        url="https://www.skywellcorp.com/website/skywellcorp/recruitment?tab=2",
    )
    replay = Replay("skywell")
    result = await SkywellCampus(source, replay, now).collect()
    assert replay.calls == [1, 2]
    assert not result.coverage_issues()
    assert len(result.jobs) == 11
    assert result.jobs[0].published == ""
