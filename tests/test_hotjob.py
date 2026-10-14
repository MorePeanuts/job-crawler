"""Offline replay of Hotjob's observed campus list/detail contract."""

import json
from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.hotjob import (
    GF,
    Goertek,
    HaiTian,
    Hotjob,
    Huatai,
    HuaXia,
    Huayou,
    JinTian,
    LiuGong,
    Minth,
    Skyworth,
    Tbea,
    TclIndustries,
    detail_body,
    location_paths,
)
from job_crawler.models import Source


class Replay:
    last_evidence = "evidence.json"

    def __init__(
        self,
        *,
        repeated: bool = False,
        empty: bool = False,
        missing_body: bool = False,
        no_places: bool = False,
    ):
        self.repeated = repeated
        self.empty = empty
        self.missing_body = missing_body
        self.no_places = no_places
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.opens: list[str] = []
        self.suite = ""

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opens.append(url)
        self.suite = url.split("/")[3]

    async def observed(self, needle: str) -> dict[str, Any]:
        if "listSearchTerm" in needle:
            return {
                "url": self._url("listSearchTerm"),
                "body": json.dumps(
                    {
                        "state": "200",
                        "data": {
                            "provinceList": []
                            if self.no_places
                            else [
                                {
                                    "nameCh": "浙江省",
                                    "childNodes": [{"nameCh": "宁波市"}],
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
            }
        if "listPositionDetail" in needle:
            first = self._detail("a")
            return {
                "url": self._url("listPositionDetail"),
                "body": json.dumps(first, ensure_ascii=False),
            }
        return {
            "url": self._url("listPosition"),
            "post_data": "isFrompb=true&recruitType=1&pageSize=2&currentPage=1",
        }

    def _url(self, endpoint: str) -> str:
        return (
            f"https://wecruit.hotjob.cn/wecruit/positionInfo/{endpoint}/{self.suite}?iSaJAx=isAjax"
        )

    def _listing(self, post_id: str) -> dict[str, Any]:
        return {
            "postId": post_id,
            "recruitType": 1,
            "postName": f"校招岗位{post_id}",
            "company": "某业务单位",
            "workPlaceStr": "宁波市",
            "educationStr": "本科及以上",
            "publishFirstDate": "2026-10-10 09:00:00",
            "publishDate": "2026-10-11 10:00:00",
            "endDate": "2026-12-31 23:59:59",
        }

    def _detail(self, post_id: str) -> dict[str, Any]:
        row = self._listing(post_id)
        row.update(
            {
                "orgName": "某业务单位",
                "education": "本科及以上",
                "workContent": f"岗位{post_id}的职责",
                "serviceCondition": f"岗位{post_id}的要求",
            }
        )
        if self.missing_body:
            row.pop("serviceCondition")
        return {"state": "200", "data": row}

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert payload is None and form is not None
        self.calls.append((url, form))
        if detail:
            return self._detail(form["postId"])
        page = int(form["currentPage"])
        rows = [] if self.empty else [self._listing("a"), self._listing("b")]
        if page == 2 and not self.empty:
            rows = [self._listing("b" if self.repeated else "c")]
        return {
            "state": "200",
            "data": {
                "pageForm": {
                    "dataCount": 0 if self.empty else 3,
                    "totalPage": 0 if self.empty else 2,
                    "currentPage": page,
                    "pageData": rows,
                }
            },
        }


@pytest.mark.parametrize("adapter", [HuaXia, JinTian, GF, LiuGong, HaiTian, Minth])
async def test_hotjob_paginates_and_joins_detail(adapter: type[Hotjob], now: datetime) -> None:
    replay = Replay()
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url=f"https://wecruit.hotjob.cn/{adapter.suite}/pb/school.html",
    )
    result = await adapter(source, replay, now).collect()
    assert result.coverage_issues() == []
    assert [job.source_key for job in result.jobs] == ["a", "b", "c"]
    assert [job.duties for job in result.jobs] == ["岗位a的职责", "岗位b的职责", "岗位c的职责"]
    assert all(job.published == "2026-10-10 09:00:00" for job in result.jobs)
    assert all(job.location == "浙江省/宁波市" for job in result.jobs)
    assert all(job.source_url.endswith("postType=campus") for job in result.jobs)
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert len([url for url, form in replay.calls if "currentPage" in form]) == 2
    assert len([url for url, form in replay.calls if "postId" in form]) == 2


async def test_hotjob_uses_returned_page_size_before_advancing(now: datetime) -> None:
    class ChangedFirstPage(Replay):
        async def request(
            self,
            url: str,
            *,
            payload: dict[str, Any] | None = None,
            form: dict[str, str] | None = None,
            detail: bool = False,
        ) -> dict[str, Any]:
            assert payload is None and form is not None
            if detail:
                return await super().request(url, form=form, detail=True)
            self.calls.append((url, form))
            page = int(form["currentPage"])
            return {
                "state": "200",
                "data": {
                    "pageForm": {
                        "dataCount": 3,
                        "pageSize": 1,
                        "totalPage": 3,
                        "currentPage": page,
                        "pageData": [self._listing("abc"[page - 1])],
                    }
                },
            }

    replay = ChangedFirstPage()
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url=f"https://wecruit.hotjob.cn/{HuaXia.suite}/pb/school.html",
    )
    result = await HuaXia(source, replay, now).collect()
    assert result.coverage_issues() == []
    assert [job.source_key for job in result.jobs] == ["a", "b", "c"]
    assert [form["pageSize"] for _, form in replay.calls if "currentPage" in form] == [
        "2",
        "1",
        "1",
        "1",
    ]


async def test_goertek_restricts_listings_to_legal_company(now: datetime) -> None:
    class CompanyReplay(Replay):
        def _listing(self, post_id: str) -> dict[str, Any]:
            row = super()._listing(post_id)
            row["company"] = "其他公司" if post_id == "b" else "歌尔股份"
            return row

    replay = CompanyReplay()
    source = Source(
        source_id="COM0208",
        company_id="COM0208",
        company="歌尔股份有限公司",
        url=f"https://goertek.hotjob.cn/{Goertek.suite}/pb/school.html",
    )
    result = await Goertek(source, replay, now).collect()
    assert result.coverage_issues() == []
    assert [job.source_key for job in result.jobs] == ["a", "c"]
    assert result.scopes[0].skipped_out_of_scope == 1
    assert all("goertek.hotjob.cn" in job.source_url for job in result.jobs)

    class MissingCompany(CompanyReplay):
        def _listing(self, post_id: str) -> dict[str, Any]:
            row = super()._listing(post_id)
            if post_id == "b":
                row["company"] = ""
            return row

    assert (await Goertek(source, MissingCompany(), now).collect()).coverage_issues()


@pytest.mark.parametrize(
    ("options", "code"),
    [
        ({"repeated": True}, "duplicate_page"),
    ],
)
async def test_hotjob_rejects_unproven_coverage(
    options: dict[str, bool], code: str, now: datetime
) -> None:
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url="https://wecruit.hotjob.cn/SU645b0d18bef57c0907e9fbc8/pb/school.html",
    )
    result = await HuaXia(source, Replay(**options), now).collect()
    assert code in {issue.code for issue in result.coverage_issues()}


async def test_hotjob_accepts_a_counted_empty_campus_catalog(now: datetime) -> None:
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url="https://wecruit.hotjob.cn/SU645b0d18bef57c0907e9fbc8/pb/school.html",
    )
    result = await HuaXia(source, Replay(empty=True), now).collect()

    assert result.jobs == []
    assert result.coverage_issues() == []
    assert result.scopes[0].expected == result.scopes[0].unique == 0
    assert result.scopes[0].terminal


def test_combined_hotjob_body_uses_visible_section_heading() -> None:
    duties, requirements = detail_body(
        {"workContent": "【岗位职责】\n办理业务。\n【任职资格】\n硕士及以上。"}
    )
    assert duties == "办理业务。"
    assert requirements == "硕士及以上。"


def test_location_tree_does_not_guess_ambiguous_city() -> None:
    paths = location_paths(
        [
            {"nameCh": "甲省", "childNodes": [{"nameCh": "同名市"}]},
            {"nameCh": "乙省", "childNodes": [{"nameCh": "同名市"}]},
        ]
    )
    assert "同名市" not in paths


async def test_huayou_excludes_intern_and_ambassador_projects(now: datetime) -> None:
    class ProjectReplay(Replay):
        def _listing(self, post_id: str) -> dict[str, Any]:
            row = super()._listing(post_id)
            row["projectName"] = {
                "a": "应届生招聘",
                "b": "实习生招聘",
                "c": "校园大使招聘",
            }[post_id]
            return row

    source = Source(
        source_id="COM0230",
        company_id="COM0230",
        company="浙江华友钴业股份有限公司",
        url=f"https://wecruit.hotjob.cn/{Huayou.suite}/pb/school.html",
    )
    result = await Huayou(source, ProjectReplay(), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 3
    assert [job.work_type for job in result.jobs] == ["校招", "实习", "校园大使"]


async def test_skyworth_rejects_other_listing_company(now: datetime) -> None:
    class CompanyReplay(Replay):
        def _listing(self, post_id: str) -> dict[str, Any]:
            row = super()._listing(post_id)
            row["company"] = "其他法人" if post_id == "c" else "创维集团有限公司"
            return row

    src = Source(
        source_id="COM0252",
        company_id="COM0252",
        company="创维集团有限公司",
        url=f"https://skyworth.hotjob.cn/{Skyworth.suite}/pb/school.html",
    )
    result = await Skyworth(src, CompanyReplay(), now).collect()
    assert len(result.jobs) == 2
    assert result.coverage_issues()
    assert any("所属公司" in issue.message for issue in result.issues)


async def test_huatai_accounts_for_other_legal_entity_without_collecting_it(
    now: datetime,
) -> None:
    class OrganizationReplay(Replay):
        async def observed(self, needle: str) -> dict[str, Any]:
            if "listSearchTerm" in needle:
                return {
                    "url": self._url("listSearchTerm"),
                    "body": json.dumps(
                        {
                            "state": "200",
                            "data": {
                                "orgList": [
                                    {"code": "0/80", "nameCh": "总部部门", "positionsNum": 1},
                                    {"code": "0/100102", "nameCh": "子公司", "positionsNum": 1},
                                    {"code": "0/100103", "nameCh": "分公司", "positionsNum": 1},
                                ]
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
            return await super().observed(needle)

        def _listing(self, post_id: str) -> dict[str, Any]:
            row = super()._listing(post_id)
            row["orgCode"] = {"a": "0/80/124", "b": "0/100102/81", "c": "0/100103"}[post_id]
            return row

    src = Source(
        source_id="COM0327",
        company_id="COM0327",
        company="华泰证券股份有限公司",
        url=f"https://wecruit.hotjob.cn/{Huatai.suite}/pb/school.html",
    )
    result = await Huatai(src, OrganizationReplay(), now).collect()
    assert not result.coverage_issues()
    assert [job.source_key for job in result.jobs] == ["a", "c"]
    assert result.scopes[0].skipped_out_of_scope == 1


async def test_tbea_requires_explicit_company_for_unlisted_institution(now: datetime) -> None:
    class InstitutionReplay(Replay):
        other_company = "特变电工股份有限公司"

        async def observed(self, needle: str) -> dict[str, Any]:
            if "listSearchTerm" in needle:
                return {
                    "url": self._url("listSearchTerm"),
                    "body": json.dumps(
                        {
                            "state": "200",
                            "data": {
                                "orgList": [
                                    {"code": "0/3", "nameCh": "特变总部", "positionsNum": 1},
                                    {"code": "0/7", "nameCh": "天池能源", "positionsNum": 1},
                                ]
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
            return await super().observed(needle)

        def _listing(self, post_id: str) -> dict[str, Any]:
            row = super()._listing(post_id)
            row["orgCode"] = {"a": "0/3/25", "b": "0/7/2", "c": "0/1727/1"}[post_id]
            row["company"] = self.other_company if post_id == "c" else "业务公司"
            return row

    src = Source(
        source_id="COM0205",
        company_id="COM0205",
        company="特变电工股份有限公司",
        url=f"https://wecruit.hotjob.cn/{Tbea.suite}/pb/school.html",
    )
    accepted = await Tbea(src, InstitutionReplay(), now).collect()
    assert not accepted.coverage_issues()
    assert [job.source_key for job in accepted.jobs] == ["a", "c"]
    assert accepted.scopes[0].skipped_out_of_scope == 1
    uncertain = InstitutionReplay()
    uncertain.other_company = "其他法人"
    rejected = await Tbea(src, uncertain, now).collect()
    assert rejected.coverage_issues()


async def test_tcl_industries_only_collects_verified_group_branch(now: datetime) -> None:
    class GroupReplay(Replay):
        unknown_code = False

        async def observed(self, needle: str) -> dict[str, Any]:
            if "listSearchTerm" in needle:
                return {
                    "url": self._url("listSearchTerm"),
                    "body": json.dumps(
                        {
                            "state": "200",
                            "data": {
                                "orgList": [
                                    {"code": "0/1", "nameCh": "TCL科技", "positionsNum": 1},
                                    {"code": "0/41", "nameCh": "TCL实业", "positionsNum": 1},
                                    {
                                        "code": "0/36",
                                        "nameCh": "TCL财务共享中心",
                                        "positionsNum": 1,
                                    },
                                ]
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
            return await super().observed(needle)

        def _listing(self, post_id: str) -> dict[str, Any]:
            row = super()._listing(post_id)
            row["orgCode"] = {"a": "0/41/5", "b": "0/1/6", "c": "0/36/7"}[post_id]
            if self.unknown_code and post_id == "c":
                row["orgCode"] = "0/999/1"
            return row

    src = Source(
        source_id="COM0153",
        company_id="COM0153",
        company="TCL实业控股股份有限公司",
        url=f"https://wecruit.hotjob.cn/{TclIndustries.suite}/pb/school.html",
    )
    result = await TclIndustries(src, GroupReplay(), now).collect()
    assert not result.coverage_issues()
    assert [job.source_key for job in result.jobs] == ["a"]
    assert result.scopes[0].skipped_out_of_scope == 2
    unknown = GroupReplay()
    unknown.unknown_code = True
    assert (await TclIndustries(src, unknown, now).collect()).coverage_issues()


async def test_missing_requirement_is_visible_warning(now: datetime) -> None:
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url="https://wecruit.hotjob.cn/SU645b0d18bef57c0907e9fbc8/pb/school.html",
    )
    result = await HuaXia(source, Replay(missing_body=True), now).collect()
    assert result.coverage_issues() == []
    assert len(result.jobs) == 3
    assert all(job.requirements == "" for job in result.jobs)
    assert len([warning for warning in result.warnings if warning.code == "field_missing"]) == 3


async def test_missing_location_tree_keeps_raw_place(now: datetime) -> None:
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url="https://wecruit.hotjob.cn/SU645b0d18bef57c0907e9fbc8/pb/school.html",
    )
    result = await HuaXia(source, Replay(no_places=True), now).collect()
    assert result.coverage_issues() == []
    assert all(job.location == "宁波市" for job in result.jobs)
    assert "location_tree_missing" in {warning.code for warning in result.warnings}
