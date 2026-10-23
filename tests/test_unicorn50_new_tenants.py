"""Scope boundaries observed on the 2026-10-23 campus tenants."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.feishu import Modelbest2027
from job_crawler.adapters.zhiye import Sanan2027, Title2027Campus
from job_crawler.models import Source
from job_crawler.transport import CrawlError


def source() -> Source:
    return Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url="https://example.com/campus/jobs",
    )


class NoNetworkSession:
    last_evidence = ""

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        raise AssertionError("范围断言不应访问网络")

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("范围断言不应访问网络")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("范围断言不应访问网络")


def test_beisen_year_and_employment_scope(now: datetime) -> None:
    adapter = Title2027Campus(source(), NoNetworkSession(), now)
    assert adapter.in_scope({"CategoryId": "2", "Kind": "全职", "JobAdName": "2027届工程师"})
    assert not adapter.in_scope(
        {"CategoryId": "2", "Kind": "实习", "JobAdName": "2027届实习工程师"}
    )
    assert not adapter.in_scope({"CategoryId": "2", "Kind": "全职", "JobAdName": "2026届工程师"})
    sanan = Sanan2027(source(), NoNetworkSession(), now)
    assert not sanan.in_scope({"CategoryId": "2", "Kind": "实习", "JobAdName": "2027届工程师"})
    try:
        adapter.in_scope({"CategoryId": "1", "Kind": "全职", "JobAdName": "2027届工程师"})
    except CrawlError:
        pass
    else:
        raise AssertionError("北森校招目录混入社招时应拒绝")


def test_modelbest_requires_current_campus_project(now: datetime) -> None:
    adapter = Modelbest2027(source(), NoNetworkSession(), now)
    assert adapter.in_scope({}, "2027届校园招聘")
    assert not adapter.in_scope({}, "2026届校园招聘")
    assert not adapter.in_scope({}, "日常实习")
