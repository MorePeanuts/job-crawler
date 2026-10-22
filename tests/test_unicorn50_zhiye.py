"""Replay the independently verified vivo and Weidian campus tenants."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhiye import (
    AdoptACow2027,
    Bananain2027,
    Cansemi2027,
    Esign2027,
    JlcEhr2027,
    KkGroup2027,
    Megarobo2027,
    ShukunCampus,
    StarChargeCampus,
    UnitreeCampus,
    Vivo2027,
    Weidian2027,
    ZhuanzhuanCampus,
)
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture:campus-list"

    def __init__(self, host: str, count: int):
        self.host = host
        self.count = count
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert self.host in url

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/api/Jobad/GetJobAdPageList"
        return {
            "url": f"https://{self.host}{needle}",
            "post_data": json.dumps(
                {
                    "PageIndex": 0,
                    "PageSize": 20,
                    "Category": ["2"],
                    "KeyWords": "",
                    "SpecialType": 0,
                    "PortalId": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        assert payload["Category"] == ["2"]
        page = int(payload["PageIndex"])
        self.pages.append(page)
        rows = []
        for number in range(page * 20, min((page + 1) * 20, self.count)):
            intern = self.host == "hr.weidian.com" and number == 2
            if self.host == "hr-campus.vivo.com":
                title = f"27届秋招工程师{number}"
            elif self.host == "kkguan.zhiye.com":
                title = f"【27技术管培生】工程师{number}"
            else:
                title = f"工程师（2027校招）{number}"
            rows.append(
                {
                    "Id": str(number),
                    "CategoryId": "2",
                    "JobAdName": title,
                    "Kind": "实习" if intern else "全职",
                    "Duty": "研发产品",
                    "Require": "本科及以上",
                    "PostDate": (
                        "0001-01-01T00:00:00"
                        if self.host == "hr-campus.vivo.com"
                        else "2026-09-20T16:42:27"
                    ),
                    "EndTime": "0001-01-01T00:00:00",
                    "LocNames": ["广东省·深圳市"],
                }
            )
        return {"Code": 200, "Count": self.count, "Data": rows}


async def test_vivo_entire_catalog_and_sentinel_dates(now: datetime) -> None:
    source = Source(
        source_id="COM0511",
        company_id="COM0511",
        company="Vivo",
        url="https://hr-campus.vivo.com/campus/jobs",
    )
    replay = Replay("hr-campus.vivo.com", 21)
    result = await Vivo2027(source, replay, now).collect()
    assert replay.pages == [0, 1]
    assert not result.coverage_issues()
    assert len(result.jobs) == 21
    assert result.jobs[0].published == ""
    assert result.jobs[0].deadline == ""
    assert result.jobs[0].unit == "vivo"


async def test_bananain_2027_full_catalog_and_intern_boundary(now: datetime) -> None:
    class BananaReplay(Replay):
        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            response = await super().request(url, payload=payload, detail=detail)
            if payload is not None and payload["PageIndex"] == 1:
                response["Data"][-1]["Kind"] = "实习"
            return response

    source = Source(
        source_id="COM0620",
        company_id="COM0620",
        company="蕉内",
        url="https://bananain.zhiye.com/campus/jobs",
    )
    replay = BananaReplay("bananain.zhiye.com", 23)
    result = await Bananain2027(source, replay, now).collect()
    assert replay.pages == [0, 1]
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 23
    assert result.scopes[0].terminal
    assert len(result.jobs) == 23
    assert result.jobs[-1].work_type == "实习"
    assert result.jobs[0].unit == "蕉内"


async def test_jlcehr_2027_excludes_old_and_non_fulltime(now: datetime) -> None:
    class JlcReplay(Replay):
        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            response = await super().request(url, payload=payload, detail=detail)
            response["Data"][0]["Require"] = "2027 届本科应届生"
            response["Data"][1]["Require"] = "2026 届本科应届生"
            response["Data"][1]["JobAdName"] = "旧管培生"
            response["Data"][2]["Require"] = "2027 届本科应届生"
            response["Data"][2]["Kind"] = "其他"
            return response

    source = Source(
        source_id="COM0529",
        company_id="COM0529",
        company="嘉立创",
        url="https://jlcehr.zhiye.com/campus/jobs",
    )
    result = await JlcEhr2027(source, JlcReplay("jlcehr.zhiye.com", 3), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert result.scopes[0].skipped_out_of_scope == 2
    assert result.scopes[0].details == 1
    assert result.jobs[0].unit == "嘉立创"


async def test_shukun_fixed_catalog_and_detail_identity(now: datetime) -> None:
    class ShukunReplay(Replay):
        def __init__(self, mismatch: bool = False):
            super().__init__("shukun.zhiye.com", 3)
            self.mismatch = mismatch
            self.details: list[str] = []

        async def observed(self, needle: str) -> dict[str, Any]:
            assert needle == "/api/JobAd/GetJobAdInfo?"
            return {"url": f"https://{self.host}{needle}"}

        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            if payload is not None:
                assert ShukunCampus.catalog_payload is not None
                assert payload["DisplayFields"] == ShukunCampus.catalog_payload["DisplayFields"]
                response = await super().request(url, payload=payload, detail=detail)
                response["Data"][0]["JobAdName"] = "【校招】算法工程师"
                response["Data"][1]["JobAdName"] = "【实习】算法工程师"
                response["Data"][1]["Kind"] = "实习"
                response["Data"][2]["JobAdName"] = "旧管培生"
                return response
            assert detail and "jobAdId=" in url
            job_id = url.split("jobAdId=", 1)[1]
            self.details.append(job_id)
            return {
                "Code": 200,
                "Data": {
                    "Id": "wrong" if self.mismatch else job_id,
                    "CategoryId": "2",
                    "JobAdName": "【校招】算法工程师" if job_id == "0" else "【实习】算法工程师",
                    "Kind": "全职" if job_id == "0" else "实习",
                    "Duty": "研发产品",
                    "Require": "本科及以上",
                    "PostDate": "2026-09-20T16:42:27",
                    "EndTime": "0001-01-01T00:00:00",
                    "LocNames": ["北京市"],
                },
            }

    source = Source(
        source_id="COM0707",
        company_id="COM0707",
        company="数坤",
        url="https://shukun.zhiye.com/campus/detail?jobAdId=24544e10-8954-4ff6-ad43-ae646a4c5c04",
    )
    replay = ShukunReplay()
    result = await ShukunCampus(source, replay, now).collect()
    assert replay.pages == [0]
    assert replay.details == ["0", "1"]
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert result.scopes[0].details == 2 and result.scopes[0].skipped_out_of_scope == 1
    assert [job.work_type for job in result.jobs] == ["校招", "实习"]

    bad = await ShukunCampus(source, ShukunReplay(mismatch=True), now).collect()
    assert bad.coverage_issues()


async def test_cansemi_full_text_catalog_and_kind_guard(now: datetime) -> None:
    class CansemiReplay(Replay):
        async def observed(self, needle: str) -> dict[str, Any]:
            raise AssertionError(f"Unexpected observed endpoint: {needle}")

        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            assert payload is not None and not detail
            assert Cansemi2027.catalog_payload is not None
            assert payload["DisplayFields"] == Cansemi2027.catalog_payload["DisplayFields"]
            response = await super().request(url, payload=payload, detail=detail)
            if payload["PageIndex"] == 0:
                response["Data"][1]["Kind"] = "实习"
            return response

    source = Source(
        source_id="COM0611",
        company_id="COM0611",
        company="粤芯半导体",
        url="https://cansemitech.zhiye.com/campus/jobs",
    )
    result = await Cansemi2027(source, CansemiReplay("cansemitech.zhiye.com", 21), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 21
    assert result.scopes[0].terminal
    assert result.jobs[0].unit == "粤芯半导体技术股份有限公司"
    assert result.jobs[1].work_type == "实习"


async def test_unitree_two_page_official_campus_catalog(now: datetime) -> None:
    class UnitreeReplay(Replay):
        async def observed(self, needle: str) -> dict[str, Any]:
            raise AssertionError(f"Unexpected observed endpoint: {needle}")

    source = Source(
        source_id="COM0540",
        company_id="COM0540",
        company="宇树科技",
        url="https://unitree.zhiye.com/campus/jobs",
    )
    replay = UnitreeReplay("unitree.zhiye.com", 35)
    result = await UnitreeCampus(source, replay, now).collect()
    assert replay.pages == [0, 1]
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 35
    assert result.scopes[0].terminal
    assert all(job.unit == "杭州宇树科技股份有限公司" for job in result.jobs)


async def test_weidian_excludes_listed_internship(now: datetime) -> None:
    source = Source(
        source_id="COM0784",
        company_id="COM0784",
        company="微店",
        url="https://hr.weidian.com/campus/jobs",
    )
    replay = Replay("hr.weidian.com", 3)
    result = await Weidian2027(source, replay, now).collect()
    assert replay.pages == [0]
    assert not result.coverage_issues()
    assert len(result.jobs) == 3
    assert result.jobs[0].published == "2026-09-20T16:42:27"
    assert [job.work_type for job in result.jobs] == ["校招", "校招", "实习"]


async def test_kkgroup_uses_official_tenant_identity_and_27_project(now: datetime) -> None:
    source = Source(
        source_id="COM0575",
        company_id="COM0575",
        company="KK集团",
        url="https://kkguan.zhiye.com/campus/jobs",
    )
    replay = Replay("kkguan.zhiye.com", 9)
    result = await KkGroup2027(source, replay, now).collect()
    assert replay.pages == [0]
    assert not result.coverage_issues()
    assert len(result.jobs) == 9
    assert all(job.unit == "KK集团" for job in result.jobs)


async def test_zhuanzhuan_campus_catalog_rejects_category_drift(now: datetime) -> None:
    source = Source(
        source_id="COM0585",
        company_id="COM0585",
        company="转转",
        url="https://zhuanzhuan.zhiye.com/campus/jobs",
    )
    replay = Replay("zhuanzhuan.zhiye.com", 2)
    result = await ZhuanzhuanCampus(source, replay, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].terminal and result.scopes[0].unique == 2
    assert all(job.unit == "转转" and job.work_type == "校招" for job in result.jobs)

    class DriftReplay(Replay):
        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            response = await super().request(url, payload=payload, detail=detail)
            response["Data"][0]["CategoryId"] = "1"
            return response

    drift = await ZhuanzhuanCampus(source, DriftReplay("zhuanzhuan.zhiye.com", 2), now).collect()
    assert drift.coverage_issues()


async def test_adopt_a_cow_keeps_only_2027_offers(now: datetime) -> None:
    class CowReplay(Replay):
        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            response = await super().request(url, payload=payload, detail=detail)
            response["Data"][0]["Require"] = "2027届本科及以上学历"
            return response

    source = Source(
        source_id="COM0682",
        company_id="COM0682",
        company="认养一头牛",
        url="https://ryytn.zhiye.com/campus/jobs",
    )
    result = await AdoptACow2027(source, CowReplay("ryytn.zhiye.com", 2), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].unique == 2 and result.scopes[0].skipped_out_of_scope == 1
    assert len(result.jobs) == 1 and result.jobs[0].unit == "认养一头牛"


async def test_star_charge_crosses_last_page(now: datetime) -> None:
    source = Source(
        source_id="COM0603",
        company_id="COM0603",
        company="星星充电",
        url="https://talent.wbstar.com/campus/jobs",
    )
    replay = Replay("talent.wbstar.com", 22)
    result = await StarChargeCampus(source, replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [0, 1]
    assert result.scopes[0].expected == result.scopes[0].unique == 22
    assert result.scopes[0].terminal
    assert all(job.unit == "星星充电" for job in result.jobs)


async def test_megarobo_2027_scope_and_last_page(now: datetime) -> None:
    class MixedReplay(Replay):
        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            response = await super().request(url, payload=payload, detail=detail)
            if response["Data"] and payload and payload["PageIndex"] == 1:
                response["Data"][0]["JobAdName"] = "往届岗位"
            return response

    source = Source(
        source_id="COM0679",
        company_id="COM0679",
        company="镁伽",
        url="https://megarobo.zhiye.com/campus/jobs",
    )
    replay = MixedReplay("megarobo.zhiye.com", 21)
    result = await Megarobo2027(source, replay, now).collect()
    assert replay.pages == [0, 1]
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 21
    assert result.scopes[0].skipped_out_of_scope == 1
    assert result.scopes[0].terminal
    assert len(result.jobs) == 20 and all(job.unit == "镁伽" for job in result.jobs)


async def test_esign_official_catalog_keeps_source_missing_date(now: datetime) -> None:
    class EsignReplay(Replay):
        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            response = await super().request(url, payload=payload, detail=detail)
            for row in response["Data"]:
                row["JobAdName"] = f"AI 工程师-27届({row['Id']})"
                row["PostDate"] = "0001-01-01T00:00:00"
            return response

    source = Source(
        source_id="COM0748",
        company_id="COM0748",
        company="e签宝",
        url="https://esign.zhiye.com/campus/jobs",
    )
    result = await Esign2027(source, EsignReplay("esign.zhiye.com", 7), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 7
    assert all(job.unit == "e签宝" and job.published == "" for job in result.jobs)
