"""Moka's public encrypted list/detail responses are replayed without network."""

import base64
import json
from datetime import datetime
from typing import Any

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from job_crawler.adapters.moka import (
    CATL,
    HFSP,
    STO,
    Anta2027,
    ChintAnengCampus,
    Dasenlin,
    Deeproute2027,
    Digiloong,
    EastchinaPharm,
    EnvisionDigital2027,
    EnvisionEnergy2027,
    Fehorizon,
    Galbot2027,
    Hengrui,
    Hithium2027,
    Huaqin,
    Jinko,
    Lingyi2027,
    Longcheer2027,
    Lygend,
    Moka,
    Sanhua,
    Seazen2027,
    Shein2027,
    Smartmore2027,
    Stepfun2027,
    Sungrow,
    SunnyOptical,
    TrinaSolar,
    Yadea,
    Yunshenchu2027,
    Zczl2027,
    ZhongAn,
    decode,
    sections,
)
from job_crawler.models import Source
from job_crawler.transport import CrawlError

IV = "de7c21ed8d6f50fe"
KEY = "99e914439fd5dff4"


def encrypted(value: dict[str, Any]) -> dict[str, str]:
    padder = PKCS7(128).padder()
    plain = json.dumps(value, ensure_ascii=False).encode()
    padded = padder.update(plain) + padder.finalize()
    encryptor = Cipher(algorithms.AES(KEY.encode()), modes.CBC(IV.encode())).encryptor()
    data = encryptor.update(padded) + encryptor.finalize()
    return {"necromancer": KEY, "data": base64.b64encode(data).decode()}


class Page:
    async def evaluate(self, script: str) -> str:
        assert "TurboApply" in script
        return IV


class Replay:
    last_evidence = "evidence.json"
    page = Page()

    def __init__(
        self,
        org: str,
        site_id: int,
        *,
        host: str = "app.mokahr.com",
        duplicate: bool = False,
        missing_description: bool = False,
    ):
        self.org = org
        self.site_id = site_id
        self.host = host
        self.duplicate = duplicate
        self.missing_description = missing_description
        self.calls: list[dict[str, Any]] = []

    def _row(self, job_id: str) -> dict[str, Any]:
        return {
            "id": job_id,
            "orgId": self.org,
            "title": f"岗位{job_id}",
            "commitment": "实习" if job_id == "b" else "全职",
            "status": "open",
            "publishedAt": "2026-10-10T09:00:00",
            "jobDescription": "<p><strong>岗位职责</strong>：</p><p>做事</p><p><strong>任职要求</strong>：</p><p>本科</p>",
            "locations": [{"provinceName": "浙江省", "cityName": "宁波市"}],
            "department": {"name": "研发部"},
            "zhineng": {"name": "技术"},
        }

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.last_evidence = "page.json"

    async def observed_path(self, needle: str) -> dict[str, Any]:
        if needle == "/api/outer/ats-apply/website/jobs/v2":
            return {
                "url": f"https://{self.host}/api/outer/ats-apply/website/jobs/v2",
                "post_data": json.dumps(
                    {
                        "orgId": self.org,
                        "siteId": str(self.site_id),
                        "site": "campus",
                        "limit": 2,
                        "offset": 0,
                        "needStat": True,
                        "jobIdTopList": [],
                        "customFields": {},
                    }
                ),
            }
        return {
            "url": f"https://{self.host}/api/outer/ats-apply/website/job",
            "body": json.dumps(encrypted({"code": 0, "data": self._row("a")})),
        }

    async def observed(self, needle: str) -> dict[str, Any]:
        return await self.observed_path(needle)

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None
        self.calls.append(payload)
        if detail:
            row = self._row(str(payload["jobId"]))
            if self.missing_description and row["id"] == "b":
                row.pop("jobDescription")
            return encrypted({"code": 0, "data": row})
        offset = int(payload["offset"])
        ids = ("a", "b") if offset == 0 else ("b" if self.duplicate else "c",)
        rows = [self._row(job_id) for job_id in ids]
        if self.missing_description:
            for row in rows:
                if row["id"] == "b":
                    row.pop("jobDescription")
        return encrypted(
            {
                "code": 0,
                "data": {
                    "jobStats": {"orgId": self.org, "total": 3},
                    "jobs": rows,
                },
            }
        )


class SunnyReplay(Replay):
    def __init__(self, *, bad_commitment: bool = False):
        super().__init__("sunnyoptical", 45602)
        self.bad_commitment = bad_commitment

    def _row(self, job_id: str) -> dict[str, Any]:
        row = super()._row(job_id)
        row["commitment"] = "全职"
        return row

    async def observed_path(self, needle: str) -> dict[str, Any]:
        if needle == "/api/outer/ats-apply/website/jobs/module":
            return {
                "url": "https://campus.sunnyoptical.cn/api/outer/ats-apply/website/jobs/module",
                "post_data": json.dumps(
                    {
                        "orgId": "sunnyoptical",
                        "siteId": 45602,
                        "moduleId": "0477326749",
                        "commitments": ["实习"] if self.bad_commitment else ["全职"],
                        "needGroupType": "zhineng",
                        "keyword": "",
                        "departmentIds": [],
                        "limit": 2,
                        "offset": 0,
                    }
                ),
            }
        return await super().observed_path(needle)


class ChintReplay(Replay):
    def __init__(self, *, wrong_company: bool = False, missing_filter: bool = False):
        super().__init__("chint", 40745, host="campus.chint.com")
        self.wrong_company = wrong_company
        self.missing_filter = missing_filter

    def _row(self, job_id: str) -> dict[str, Any]:
        row = super()._row(job_id)
        row["department"] = {
            "id": 725999 if self.wrong_company and job_id == "b" else 725411,
            "name": "正泰安能数字能源（浙江）股份有限公司",
        }
        return row

    async def observed_path(self, needle: str) -> dict[str, Any]:
        response = await super().observed_path(needle)
        if needle.endswith("jobs/v2"):
            payload = json.loads(response["post_data"])
            if not self.missing_filter:
                payload["departmentIds"] = ["725411"]
            response["post_data"] = json.dumps(payload)
        return response


async def test_chint_aneng_uses_company_filter_and_rejects_other_company(
    now: datetime,
) -> None:
    source = Source(
        source_id="COM0530",
        company_id="COM0530",
        company="正泰安能",
        url="https://campus.chint.com/campus-recruitment/chint/40745/#/jobs?department%5B0%5D=725411",
    )
    replay = ChintReplay()
    result = await ChintAnengCampus(source, replay, now).collect()
    assert not result.coverage_issues()
    assert [call["departmentIds"] for call in replay.calls if "offset" in call] == [
        ["725411"],
        ["725411"],
    ]
    assert len(result.jobs) == 3

    wrong_filter = await ChintAnengCampus(source, ChintReplay(missing_filter=True), now).collect()
    assert wrong_filter.coverage_issues()
    wrong_company = await ChintAnengCampus(source, ChintReplay(wrong_company=True), now).collect()
    assert wrong_company.coverage_issues()


async def test_sunny_module_catalog(now: datetime) -> None:
    source = Source(
        source_id="COM0353",
        company_id="COM0353",
        company="舜宇光学科技（集团）有限公司",
        url="https://campus.sunnyoptical.cn/campus-recruitment/sunnyoptical/45602/#/",
    )
    replay = SunnyReplay()
    result = await SunnyOptical(source, replay, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].unique == result.scopes[0].details == 3
    assert [call["offset"] for call in replay.calls if "offset" in call] == [0, 2]
    assert all(job.work_type == "校招" for job in result.jobs)
    assert all(job.source_url.startswith("https://campus.sunnyoptical.cn/") for job in result.jobs)


async def test_sunny_rejects_internship_module(now: datetime) -> None:
    source = Source(
        source_id="COM0353",
        company_id="COM0353",
        company="舜宇光学科技（集团）有限公司",
        url="https://campus.sunnyoptical.cn/campus-recruitment/sunnyoptical/45602/#/",
    )
    result = await SunnyOptical(source, SunnyReplay(bad_commitment=True), now).collect()
    assert result.coverage_issues()


@pytest.mark.parametrize(
    "adapter",
    [
        CATL,
        Huaqin,
        Jinko,
        Sungrow,
        STO,
        Lygend,
        Digiloong,
        HFSP,
        Sanhua,
        EastchinaPharm,
        Yadea,
        Fehorizon,
        Dasenlin,
        TrinaSolar,
        Anta2027,
        Hengrui,
        Hithium2027,
        Shein2027,
        Stepfun2027,
        Smartmore2027,
        Galbot2027,
        Yunshenchu2027,
        Deeproute2027,
        Seazen2027,
        Lingyi2027,
        Zczl2027,
    ],
)
async def test_moka_pagination_detail_and_job_type(adapter: type[Moka], now: datetime) -> None:
    session = Replay(adapter.org, adapter.site_id, host=adapter.host)
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url=f"https://{adapter.host}/{adapter.route}/{adapter.org}/{adapter.site_id}",
    )
    result = await adapter(source, session, now).collect()
    assert result.coverage_issues() == []
    assert [j.source_key for j in result.jobs] == ["a", "b", "c"]
    assert result.jobs[0].duties == "做事"
    assert result.jobs[0].requirements == "本科"
    assert result.jobs[0].location == "浙江省/宁波市"
    assert result.jobs[1].work_type == "实习"
    assert result.jobs[0].published == "2026-10-10T09:00:00"
    assert result.jobs[0].source_url.startswith(
        f"https://{adapter.host}/{adapter.route}/{adapter.org}/{adapter.site_id}#/job/"
    )
    assert [call["offset"] for call in session.calls if "offset" in call] == [0, 2]


async def test_moka_rejects_duplicate_page(now: datetime) -> None:
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url="https://app.mokahr.com/campus-recruitment/catlhr/142020",
    )
    result = await CATL(source, Replay("catlhr", 142020, duplicate=True), now).collect()
    assert "duplicate_page" in {issue.code for issue in result.coverage_issues()}


class EnvisionReplay(Replay):
    def __init__(self) -> None:
        super().__init__("envisiongroup", 43123)

    def _row(self, job_id: str) -> dict[str, Any]:
        row = super()._row(job_id)
        row["department"] = (
            {"id": 967570, "name": "远景动力"}
            if job_id == "b"
            else {"id": 958964, "name": "远景能源"}
        )
        return row


async def test_envision_energy_excludes_other_group_departments(now: datetime) -> None:
    source = Source(
        source_id="COM0516",
        company_id="COM0516",
        company="远景能源",
        url="https://app.mokahr.com/campus-recruitment/envisiongroup/43123#/jobs",
    )
    result = await EnvisionEnergy2027(source, EnvisionReplay(), now).collect()
    assert not result.coverage_issues()
    assert [job.source_key for job in result.jobs] == ["a", "c"]
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert result.scopes[0].skipped_out_of_scope == 1


class EnvisionDigitalReplay(EnvisionReplay):
    def _row(self, job_id: str) -> dict[str, Any]:
        row = super()._row(job_id)
        if job_id == "a":
            row["department"] = {"id": 958965, "name": "远景智能"}
        return row


async def test_envision_digital_is_distinct_from_energy_and_power(now: datetime) -> None:
    source = Source(
        source_id="COM0561",
        company_id="COM0561",
        company="远景智能",
        url="https://app.mokahr.com/campus-recruitment/envisiongroup/43123#/jobs",
    )
    result = await EnvisionDigital2027(source, EnvisionDigitalReplay(), now).collect()
    assert not result.coverage_issues()
    assert [job.source_key for job in result.jobs] == ["a"]
    assert result.scopes[0].skipped_out_of_scope == 2


class TitleMismatch(Replay):
    async def observed_path(self, needle: str) -> dict[str, Any]:
        response = await super().observed_path(needle)
        if needle == "/api/outer/ats-apply/website/job":
            row = self._row("a")
            row["title"] = "错误详情标题"
            response["body"] = json.dumps(encrypted({"code": 0, "data": row}))
        return response


@pytest.mark.parametrize(
    "adapter",
    [Seazen2027, Lingyi2027, Zczl2027, Hithium2027, Shein2027, Stepfun2027, Smartmore2027],
)
async def test_moka_rejects_detail_title_mismatch(adapter: type[Moka], now: datetime) -> None:
    source = Source(
        source_id="TEST",
        company_id="TEST",
        company="企业",
        url=f"https://{adapter.host}{adapter.path}",
    )
    result = await adapter(source, TitleMismatch(adapter.org, adapter.site_id), now).collect()
    assert result.coverage_issues()
    assert "a" not in {job.source_key for job in result.jobs}
    assert {"b", "c"} == {job.source_key for job in result.jobs}


async def test_moka_keeps_job_with_missing_description(now: datetime) -> None:
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url="https://app.mokahr.com/campus-recruitment/hq/45417",
    )
    result = await Huaqin(source, Replay("hq", 45417, missing_description=True), now).collect()
    assert result.coverage_issues() == []
    assert len(result.jobs) == 3
    assert any(w.message == "源站详情没有岗位正文" for w in result.warnings)


def test_moka_decoder_and_section_boundaries() -> None:
    assert decode(encrypted({"code": 0, "data": {"value": 1}}), IV)["data"] == {"value": 1}
    with pytest.raises(CrawlError, match="解码失败"):
        decode(encrypted({"code": 0, "data": {"value": 1}}), "wrong-iv-1234567")
    assert sections("<p>无小标题正文</p>") == ("无小标题正文", "")
    assert sections("<p>【岗位职责】</p><p>做事</p><p>二、岗位要求：</p><p>本科</p>") == (
        "做事",
        "本科",
    )


def test_explicit_intern_title_overrides_fulltime_commitment(now: datetime) -> None:
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url="https://app.mokahr.com/campus-recruitment/jinkosolar/41896",
    )
    adapter = Jinko(source, Replay("jinkosolar", 41896), now)
    row = {"id": "intern", "title": "人力资源实习生", "commitment": "全职"}
    assert adapter._job(row, row, "evidence.json").work_type == "实习"
    row = {"id": "graduate", "title": "研发管培生"}
    assert adapter._job(row, row, "evidence.json").work_type == "校招"


class ZhongAnReplay(Replay):
    def __init__(self, *, unknown: bool = False):
        super().__init__("zhongan", 71908)
        self.unknown = unknown

    def _row(self, job_id: str) -> dict[str, Any]:
        row = super()._row(job_id)
        row["title"] = {
            "a": "[2027届秋招-上海]数据开发工程师",
            "b": "[实习可留用-杭州]保险产品实习生",
            "c": "未知正式项目" if self.unknown else "众安校园大使",
        }[job_id]
        return row


async def test_zhongan_excludes_non_jobs_and_detects_unknown_project(now: datetime) -> None:
    source = Source(
        source_id="COM0400",
        company_id="COM0400",
        company="众安在线财产保险股份有限公司",
        url="https://app.mokahr.com/campus-recruitment/zhongan/71908#/jobs",
    )
    result = await ZhongAn(source, ZhongAnReplay(), now).collect()
    assert not result.coverage_issues()
    assert [job.source_key for job in result.jobs] == ["a"]
    assert result.scopes[0].skipped_out_of_scope == 2

    unknown = await ZhongAn(source, ZhongAnReplay(unknown=True), now).collect()
    assert unknown.coverage_issues()


async def test_longcheer_campus_apply_site_uses_full_unfiltered_directory(now: datetime) -> None:
    source = Source(
        source_id="COM0360",
        company_id="COM0360",
        company="上海龙旗科技股份有限公司",
        url="https://app.mokahr.com/campus_apply/longcheer/166561#/jobs",
    )
    session = Replay("longcheer", 166561)
    result = await Longcheer2027(source, session, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert session.calls[0]["orgId"] == "longcheer"
    assert session.calls[0]["siteId"] == "166561"
    assert session.calls[0]["site"] == "campus"
    assert session.calls[-1]["jobId"] == "c"
    assert all("campus_apply/longcheer/166561" in job.source_url for job in result.jobs)
