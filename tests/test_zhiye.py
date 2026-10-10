import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.zhiye import Xiangyu, date_text
from job_crawler.models import Source
from job_crawler.transport import CrawlError


class Replay:
    last_evidence = "fixture"

    def __init__(
        self,
        count: int = 21,
        *,
        mismatch: bool = False,
        repeated: bool = False,
        filtered: bool = False,
    ):
        self.count = count
        self.mismatch = mismatch
        self.repeated = repeated
        self.filtered = filtered
        self.pages: list[int] = []
        self.details: list[str] = []
        self.opens: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opens.append(url)

    async def observed(self, needle: str) -> dict[str, Any]:
        if "Info" in needle:
            return {
                "url": "https://xiangyu.zhiye.com/api/JobAd/GetJobAdInfo?jobAdId=0&category=2&displayFields=Duty"
            }
        return {
            "url": "https://xiangyu.zhiye.com/api/Jobad/GetJobAdPageList",
            "post_data": json.dumps(
                {
                    "PageIndex": 0,
                    "PageSize": 20,
                    "Category": ["2"],
                    "PortalId": "tenant-specific",
                    "LocId": [1100] if self.filtered else [],
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        if payload is not None:
            assert payload["Category"] == ["2"] and payload["PortalId"] == "tenant-specific"
            page = payload["PageIndex"]
            self.pages.append(page)
            start = 0 if self.repeated else page * payload["PageSize"]
            return {
                "Code": 200,
                "Count": self.count,
                "Data": [
                    {"Id": str(i), "PostDate": "2026-09-01T00:00:00"}
                    for i in range(start, min(start + payload["PageSize"], self.count))
                ],
            }
        identity = parse_qs(urlsplit(url).query)["jobAdId"][0]
        self.details.append(identity)
        return {
            "Code": 200,
            "Data": {
                "Id": "wrong" if self.mismatch and identity == "0" else identity,
                "CategoryId": "2",
                "JobAdName": f"工程师{identity}",
                "Duty": "研发产品",
                "Require": "本科及以上",
                "EndTime": "0001-01-01T00:00:00",
                "PostDate": "0001-01-01T00:00:00",
                "LocNames": ["福建省·厦门市"],
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0056",
        company_id="COM0056",
        company="象屿",
        url="https://xiangyu.zhiye.com/campus/jobs",
    )


async def test_zhiye_all_pages_and_details(now: datetime) -> None:
    replay = Replay()
    result = await Xiangyu(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == 21 and replay.pages == [0, 1]
    assert len(set(replay.details)) == 21
    assert result.jobs[0].deadline == ""
    assert result.jobs[0].published == "2026-09-01T00:00:00"
    assert result.jobs[0].requirements == "本科及以上"
    assert "jobAdId=0" in result.jobs[0].source_url


async def test_zhiye_failed_detail_preserves_other_jobs(now: datetime) -> None:
    result = await Xiangyu(source(), Replay(mismatch=True), now).collect()
    assert len(result.jobs) == 20
    assert result.scopes[0].details == 20
    assert result.coverage_issues()


async def test_zhiye_repeated_page_never_complete(now: datetime) -> None:
    result = await Xiangyu(source(), Replay(repeated=True), now).collect()
    assert len(result.jobs) == 20
    assert any(i.code == "duplicate_page" for i in result.issues)


async def test_zhiye_shared_filter_does_not_masquerade_as_full_catalog(now: datetime) -> None:
    result = await Xiangyu(source(), Replay(filtered=True), now).collect()
    assert not result.jobs and result.coverage_issues()
    assert "LocId" in result.issues[0].message


async def test_zhiye_verified_zero(now: datetime) -> None:
    replay = Replay(count=0)
    result = await Xiangyu(source(), replay, now).collect()
    assert not result.jobs and not result.coverage_issues()
    assert not replay.details and len(replay.opens) == 1


async def test_zhiye_stops_queued_details_after_access_denied(now: datetime) -> None:
    class Denied(Replay):
        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            if detail:
                self.details.append(url)
                raise CrawlError("access_denied", "HTTP 403")
            return await super().request(url, payload=payload)

    replay = Denied()
    result = await Xiangyu(source(), replay, now).collect()
    assert len(replay.details) == 1
    assert replay.pages == [0]
    assert any(issue.code == "access_denied" for issue in result.issues)


@pytest.mark.parametrize(
    "value,expected", [(None, ""), ("0001-01-01T00:00:00", ""), ("2026-12-01", "2026-12-01")]
)
def test_zhiye_unset_dates(value: Any, expected: str) -> None:
    assert date_text(value) == expected
