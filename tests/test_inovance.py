import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.inovance import InovanceCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "inovance-page.json"

    def __init__(self, *, duplicate: bool = False, early_end: bool = False):
        self.duplicate = duplicate
        self.early_end = early_end
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://recruit.inovance.com/#/campus/jobs"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": "https://recruit.inovance.com/prod-portal-api/position/ad/search",
            "portal_id": "019daf7d-4d1a-7634-87af-1f089498b6f2",
            "post_data": json.dumps(
                {
                    "keyword": "",
                    "recruitTypes": [1],
                    "hotOnly": False,
                    "topOnly": False,
                    "longTermOnly": False,
                    "pageNum": 1,
                    "pageSize": 1,
                    "sortBy": "recommended",
                }
            ),
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert payload is not None
        assert payload["recruitTypes"] == [1] and payload["keyword"] == ""
        assert headers == {"X-Portal-Id": "019daf7d-4d1a-7634-87af-1f089498b6f2"}
        page = int(payload["pageNum"])
        self.pages.append(page)
        key = "id-1" if self.duplicate or page == 1 else "id-2"
        return {
            "code": 200,
            "data": {
                "total": 2,
                "pageNum": page,
                "pageSize": 1,
                "hasMore": page == 1 and not self.early_end,
                "records": [
                    {
                        "adId": key,
                        "recruitType": "1",
                        "adJobName": "研发工程师",
                        "segment": "分子公司-联合动力",
                        "degreeDesc": "本科",
                        "workLocation": [{"name": "南京市"}],
                        "jobDescription": "负责研发",
                        "jobRequirement": "本科及以上",
                        "publishTime": "2026-10-12T19:45:57",
                    }
                ],
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0341",
        company_id="COM0341",
        company="深圳市汇川技术股份有限公司",
        url="https://recruit.inovance.com/#/campus/jobs",
    )


async def test_inovance_complete_catalog(now: datetime) -> None:
    replay = Replay()
    result = await InovanceCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert result.scopes[0].expected == result.scopes[0].details == 2
    assert len(result.jobs) == 2
    assert result.jobs[0].unit == "分子公司-联合动力"
    assert result.jobs[0].education == "本科"
    assert result.jobs[0].published == "2026-10-12T19:45:57"


async def test_inovance_duplicate_page_is_incomplete(now: datetime) -> None:
    result = await InovanceCampus(source(), Replay(duplicate=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 1


async def test_inovance_early_end_is_incomplete(now: datetime) -> None:
    result = await InovanceCampus(source(), Replay(early_end=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 1
