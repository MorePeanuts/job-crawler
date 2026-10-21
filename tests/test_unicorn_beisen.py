"""Observed Category=2 catalog contract for the first unicorn Beisen tenants."""

import json
from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.zhiye import (
    AescCampus,
    AispeechCampus,
    CasSpaceCampus,
    CxmtCampus,
    DreameCampus,
    FoxEssCampus,
    GalaxeaCampus,
    GalaxyCampus,
    HairoboticsCampus,
    HellobikeCampus,
    HuiceCampus,
    IrootechCampus,
    JunlebaoCampus,
    LeheCampus,
    NarwalCampus,
    SpacesailCampus,
    SvoltCampus,
    XagCampus,
    YmtcCampus,
    ZhihuiyaCampus,
    Zhiye,
)
from job_crawler.models import Source


class CampusReplay:
    last_evidence = "campus-list"

    def __init__(self, *, filtered: bool = False) -> None:
        self.filtered = filtered
        self.pages: list[int] = []
        self.opens: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opens.append(url)

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": "https://tenant.zhiye.com/api/Jobad/GetJobAdPageList",
            "post_data": json.dumps(
                {
                    "PageIndex": 0,
                    "PageSize": 2,
                    "Category": ["2"],
                    "KeyWords": "",
                    "PortalId": "",
                    "LocId": [1] if self.filtered else [],
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        assert payload["Category"] == ["2"]
        page = payload["PageIndex"]
        self.pages.append(page)
        return {
            "Code": 200,
            "Count": 21,
            "Data": [
                {
                    "Id": f"job-{index}",
                    "CategoryId": "2",
                    "JobAdName": f"工程师{index}",
                    "Kind": "实习" if index == 20 else "全职",
                    "Duty": "研发产品",
                    "Require": "本科及以上",
                    "PostDate": "2026-10-01T09:00:00",
                    "EndTime": "0001-01-01T00:00:00",
                    "LocNames": ["上海市"],
                }
                for index in range(
                    page * payload["PageSize"], min((page + 1) * payload["PageSize"], 21)
                )
            ],
        }


@pytest.mark.parametrize(
    ("adapter", "host"),
    [
        (YmtcCampus, "ymtc.zhiye.com"),
        (CxmtCampus, "cxmt.zhiye.com"),
        (DreameCampus, "dreame.zhiye.com"),
        (AescCampus, "aesc-group.zhiye.com"),
        (GalaxyCampus, "galaxy.zhiye.com"),
        (LeheCampus, "lehe.zhiye.com"),
        (AispeechCampus, "aispeech.zhiye.com"),
        (ZhihuiyaCampus, "zhihuiya.zhiye.com"),
        (HellobikeCampus, "hellobike.zhiye.com"),
        (CasSpaceCampus, "cas-space.zhiye.com"),
        (IrootechCampus, "irootech.zhiye.com"),
        (JunlebaoCampus, "junlebaoruye.zhiye.com"),
        (SvoltCampus, "svolt.zhiye.com"),
        (HairoboticsCampus, "hairobotics.zhiye.com"),
        (FoxEssCampus, "fox-ess.zhiye.com"),
        (GalaxeaCampus, "galaxea.zhiye.com"),
        (HuiceCampus, "huicecom.zhiye.com"),
        (SpacesailCampus, "spacesail.zhiye.com"),
        (XagCampus, "zhaopin.xa.com"),
    ],
)
async def test_unicorn_beisen_full_catalog_and_internship(
    now: datetime, adapter: type[Zhiye], host: str
) -> None:
    replay = CampusReplay()
    source = Source(source_id="NEW", company_id="NEW", company="候选企业", url=f"https://{host}/")
    result = await adapter(source, replay, now).collect()
    assert replay.opens == [f"https://{host}/campus/jobs"]
    assert replay.pages == [0, 1]
    assert not result.coverage_issues()
    assert len(result.jobs) == 21
    assert result.jobs[20].work_type == "实习"
    assert result.jobs[0].deadline == ""
    assert result.jobs[0].duties == "研发产品"


async def test_unicorn_beisen_rejects_partial_location_filter(now: datetime) -> None:
    replay = CampusReplay(filtered=True)
    source = Source(
        source_id="NEW", company_id="NEW", company="候选企业", url="https://ymtc.zhiye.com/"
    )
    result = await YmtcCampus(source, replay, now).collect()
    assert not result.jobs and result.coverage_issues()
    assert "LocId" in result.issues[0].message


class MixedCampusReplay(CampusReplay):
    async def observed(self, needle: str) -> dict[str, Any]:
        result = await super().observed(needle)
        payload = json.loads(result["post_data"])
        payload.pop("Category")
        payload["SpecialType"] = 0
        result["post_data"] = json.dumps(payload)
        return result


async def test_narwal_mixed_catalog_filters_exact_campus_category(now: datetime) -> None:
    replay = MixedCampusReplay()
    source = Source(
        source_id="COM0688",
        company_id="COM0688",
        company="云鲸智能",
        url="https://careers.narwal.com/jobs",
    )
    result = await NarwalCampus(source, replay, now).collect()
    assert replay.opens == ["https://careers.narwal.com/jobs"]
    assert replay.pages == [0, 1]
    assert not result.coverage_issues()
    assert len(result.jobs) == 21
    assert result.jobs[-1].work_type == "实习"
