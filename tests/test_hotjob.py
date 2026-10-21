"""Offline replay of Hotjob's observed campus list/detail contract."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from job_crawler.adapters.hotjob import (
    GF,
    BbmgCampus,
    CrrcGroup,
    DbnCampus,
    EveEnergy,
    FarEastListedCampus,
    GoermicroCampus2027,
    Goertek,
    GwmListed,
    HaiTian,
    HengyiGroup,
    Hotjob,
    Huatai,
    HuaXia,
    Huayou,
    JinTian,
    LiuGong,
    Luxshare,
    MinmetalsGroup,
    Minth,
    SinomachGroup,
    Skyworth,
    Tbea,
    TclIndustries,
    UnisocCampus2027,
    Wanhua2027,
    Zoomlion2027,
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


class SinomachReplay(Replay):
    def __init__(
        self,
        *,
        wrong_detail: bool = False,
        wrong_tree: bool = False,
        wrong_listing: bool = False,
        wrong_count: bool = False,
        internship: bool = False,
    ):
        super().__init__()
        self.wrong_detail = wrong_detail
        self.wrong_tree = wrong_tree
        self.wrong_listing = wrong_listing
        self.wrong_count = wrong_count
        self.internship = internship

    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        if "listSearchTerm" in needle:
            terms = json.loads(response["body"])
            terms["data"]["orgList"] = (
                []
                if self.wrong_tree
                else [
                    {
                        "code": "0/2688",
                        "nameCh": "国机集团总部",
                        "positionsNum": 3 if self.wrong_count else 2,
                        "childNodes": [{"code": "0/2688/1317", "childNodes": []}],
                    },
                    {
                        "code": "0/1289",
                        "nameCh": "中国机械设备工程股份有限公司",
                        "positionsNum": 1,
                        "childNodes": [{"code": "0/1289/2693", "childNodes": []}],
                    },
                ]
            )
            response["body"] = json.dumps(terms, ensure_ascii=False)
        elif "listPositionDetail" not in needle:
            response["post_data"] = (
                "recruitType=1&currentPage=1&pageSize=2&coordinateLat=&coordinateLng="
            )
        return response

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = super()._listing(post_id)
        row.update(
            {
                "company": "中国机械设备工程股份有限公司" if post_id == "b" else "国机集团总部",
                "orgCode": "0/1289/2693" if post_id == "b" else "0/2688/1317",
                "projectName": "2027届青蓝计划",
            }
        )
        if self.wrong_listing and post_id == "c":
            row["orgCode"] = "0/9999/2693"
        if self.internship and post_id == "c":
            row["projectName"] = "实习见习岗位"
            row["workTypeStr"] = "全职"
        return row

    def _detail(self, post_id: str) -> dict[str, Any]:
        detail = super()._detail(post_id)
        detail["data"].update(self._listing(post_id))
        if self.wrong_detail and post_id == "c":
            detail["data"]["orgCode"] = "0/1289/2693"
        return detail


@pytest.mark.parametrize(
    "wrong_detail,wrong_tree,wrong_listing,wrong_count",
    [
        (False, False, False, False),
        (True, False, False, False),
        (False, True, False, False),
        (False, False, True, False),
        (False, False, False, True),
    ],
)
async def test_sinomach_group_directory_and_identity(
    wrong_detail: bool,
    wrong_tree: bool,
    wrong_listing: bool,
    wrong_count: bool,
    now: datetime,
) -> None:
    replay = SinomachReplay(
        wrong_detail=wrong_detail,
        wrong_tree=wrong_tree,
        wrong_listing=wrong_listing,
        wrong_count=wrong_count,
    )
    source = Source(
        source_id="COM0085",
        company_id="COM0085",
        company="中国机械工业集团有限公司",
        url=("https://zhaopin.sinomach.com.cn/SU64b60d25bef57c7e363ff1a3/mc/position/campus"),
    )
    result = await SinomachGroup(source, replay, now).collect()
    if wrong_tree:
        assert result.coverage_issues()
        assert result.jobs == []
    elif wrong_detail or wrong_listing:
        assert result.coverage_issues()
        assert [job.source_key for job in result.jobs] == ["a", "b"]
    elif wrong_count:
        assert result.coverage_issues()
        assert [job.source_key for job in result.jobs] == ["a", "b", "c"]
    else:
        assert result.coverage_issues() == []
        assert [job.source_key for job in result.jobs] == ["a", "b", "c"]
        assert result.scopes[0].skipped_out_of_scope == 0
        assert result.scopes[0].details == 3
        assert [job.unit for job in result.jobs] == [
            "国机集团总部 / 某业务单位",
            "中国机械设备工程股份有限公司 / 某业务单位",
            "国机集团总部 / 某业务单位",
        ]
        assert all(job.published == "2026-10-10 09:00:00" for job in result.jobs)


async def test_sinomach_internship_project_is_not_regular_campus(now: datetime) -> None:
    source = Source(
        source_id="COM0085",
        company_id="COM0085",
        company="中国机械工业集团有限公司",
        url="https://zhaopin.sinomach.com.cn/SU64b60d25bef57c7e363ff1a3/mc/position/campus",
    )
    result = await SinomachGroup(source, SinomachReplay(internship=True), now).collect()
    assert result.coverage_issues() == []
    assert [job.work_type for job in result.jobs] == ["校招", "校招", "实习"]


class MinmetalsReplay(SinomachReplay):
    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        if "listSearchTerm" in needle:
            terms = json.loads(response["body"])
            terms["data"]["orgList"] = [
                {
                    "code": "0/1",
                    "nameCh": "集团总部",
                    "positionsNum": 2,
                    "childNodes": [],
                },
                {
                    "code": "0/496",
                    "nameCh": "中国冶金科工股份有限公司",
                    "positionsNum": 1,
                    "childNodes": [{"code": "0/496/612", "childNodes": []}],
                },
            ]
            response["body"] = json.dumps(terms, ensure_ascii=False)
        elif "listPositionDetail" not in needle:
            response["post_data"] = "isFrompb=true&recruitType=1&pageSize=2&currentPage=1"
        return response

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = Replay._listing(self, post_id)
        row.update(
            {
                "company": "中国冶金科工股份有限公司" if post_id == "b" else "中国五矿集团总部",
                "orgCode": "0/496/612" if post_id == "b" else "0/1/491/190",
                "projectName": "2027届校园招聘",
            }
        )
        return row

    def _detail(self, post_id: str) -> dict[str, Any]:
        detail = Replay._detail(self, post_id)
        detail["data"].update(self._listing(post_id))
        return detail


async def test_minmetals_group_directory_and_member_units(now: datetime) -> None:
    source = Source(
        source_id="COM0028",
        company_id="COM0028",
        company="中国五矿集团有限公司",
        url=f"https://wecruit.hotjob.cn/{MinmetalsGroup.suite}/pb/school.html",
    )
    result = await MinmetalsGroup(source, MinmetalsReplay(), now).collect()
    assert result.coverage_issues() == []
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert [job.unit for job in result.jobs] == [
        "中国五矿集团总部 / 某业务单位",
        "中国冶金科工股份有限公司 / 某业务单位",
        "中国五矿集团总部 / 某业务单位",
    ]


class HengyiReplay(SinomachReplay):
    def __init__(
        self, *, wrong_project: bool = False, wrong_tree: bool = False, daily: bool = False
    ):
        super().__init__()
        self.wrong_project = wrong_project
        self.wrong_tree = wrong_tree
        self.daily = daily

    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        if "listSearchTerm" in needle:
            terms = json.loads(response["body"])
            terms["data"]["orgList"] = [
                {
                    "code": "0/3",
                    "nameCh": "错误集团" if self.wrong_tree else "浙江恒逸集团有限公司",
                    "positionsNum": 2,
                    "childNodes": [],
                },
                {
                    "code": "0/4",
                    "nameCh": "恒逸石化股份有限公司",
                    "positionsNum": 1,
                    "childNodes": [{"code": "0/4/17", "childNodes": []}],
                },
            ]
            response["body"] = json.dumps(terms, ensure_ascii=False)
        return response

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = Replay._listing(self, post_id)
        row.update(
            {
                "company": "浙江恒逸物流有限公司" if post_id == "b" else "浙江恒逸集团有限公司",
                "orgCode": "0/4/17" if post_id == "b" else "0/3",
                "projectName": "未知项目"
                if self.wrong_project and post_id == "c"
                else "日常招聘"
                if self.daily and post_id == "c"
                else "2027届校园招聘",
                "projectId": 0 if self.daily and post_id == "c" else 100901,
            }
        )
        return row

    def _detail(self, post_id: str) -> dict[str, Any]:
        detail = Replay._detail(self, post_id)
        detail["data"].update(self._listing(post_id))
        return detail


@pytest.mark.parametrize(
    "wrong_project,wrong_tree,daily",
    [(False, False, False), (True, False, False), (False, True, False), (False, False, True)],
)
async def test_hengyi_group_contract(
    wrong_project: bool, wrong_tree: bool, daily: bool, now: datetime
) -> None:
    source = Source(
        source_id="COM0050",
        company_id="COM0050",
        company="浙江恒逸集团有限公司",
        url=f"https://wecruit.hotjob.cn/{HengyiGroup.suite}/mc/position/campus",
    )
    result = await HengyiGroup(
        source,
        HengyiReplay(wrong_project=wrong_project, wrong_tree=wrong_tree, daily=daily),
        now,
    ).collect()
    if wrong_project or wrong_tree:
        assert result.coverage_issues()
    else:
        assert result.coverage_issues() == []
        assert result.scopes[0].expected == result.scopes[0].unique == 3
        assert result.scopes[0].skipped_out_of_scope == int(daily)
        assert [job.unit for job in result.jobs] == (
            ["浙江恒逸集团有限公司 / 某业务单位", "浙江恒逸物流有限公司 / 某业务单位"]
            + ([] if daily else ["浙江恒逸集团有限公司 / 某业务单位"])
        )


class CrrcReplay(MinmetalsReplay):
    def _url(self, endpoint: str) -> str:
        return super()._url(endpoint).replace("wecruit.hotjob.cn", "crrc.hotjob.cn")

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = super()._listing(post_id)
        row["company"] = "中车齐齐哈尔车辆有限公司" if post_id == "b" else "中车集团总部"
        return row


async def test_crrc_group_directory_and_detail_identity(now: datetime) -> None:
    source = Source(
        source_id="COM0095",
        company_id="COM0095",
        company="中国中车集团有限公司",
        url=f"https://crrc.hotjob.cn/{CrrcGroup.suite}/pb/school.html",
    )
    result = await CrrcGroup(source, CrrcReplay(), now).collect()
    assert result.coverage_issues() == []
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert [job.unit for job in result.jobs] == [
        "中车集团总部 / 某业务单位",
        "中车齐齐哈尔车辆有限公司 / 某业务单位",
        "中车集团总部 / 某业务单位",
    ]


class GwmListedReplay(MinmetalsReplay):
    def _url(self, endpoint: str) -> str:
        return super()._url(endpoint).replace("wecruit.hotjob.cn", "zhaopin.gwm.cn")

    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        if "listSearchTerm" in needle:
            terms = json.loads(response["body"])
            terms["data"]["orgList"][0]["code"] = "0/14"
            terms["data"]["orgList"][0]["nameCh"] = "长城汽车股份有限公司"
            response["body"] = json.dumps(terms, ensure_ascii=False)
        return response

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = super()._listing(post_id)
        row["company"] = "曼德电子电器有限公司" if post_id == "b" else "长城汽车股份有限公司"
        row["orgCode"] = "0/496/612" if post_id == "b" else "0/14/22"
        return row


async def test_gwm_listed_entity_filters_other_group_units(now: datetime) -> None:
    source = Source(
        source_id="COM0130",
        company_id="COM0130",
        company="长城汽车股份有限公司",
        url=f"https://zhaopin.gwm.cn/{GwmListed.suite}/pb/school.html",
    )
    result = await GwmListed(source, GwmListedReplay(), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert result.scopes[0].skipped_out_of_scope == 1
    assert [job.source_key for job in result.jobs] == ["a", "c"]


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


class ZoomlionReplay(Replay):
    def __init__(self, *, wrong_detail: bool = False):
        super().__init__()
        self.wrong_detail = wrong_detail

    async def observed(self, needle: str) -> dict[str, Any]:
        if "listPosition" in needle and "Detail" not in needle:
            return {
                "url": self._url("listPosition"),
                "post_data": "recruitType=1&currentPage=1&pageSize=10&coordinateLat=&coordinateLng=",
            }
        if "listPositionDetail" in needle:
            return {"url": self._url("listPositionDetail"), "body": json.dumps(self._detail("1"))}
        return await super().observed(needle)

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = super()._listing(post_id)
        number = int(post_id)
        row.update(
            {
                "postName": f"{'机器人研发工程师' if 6 <= number <= 14 else '技术研发岗'}{number}",
                "company": "中联重科股份有限公司",
                "orgCode": "0/100001",
                "projectName": "中联重科2027届校招",
                "projectId": 128002,
            }
        )
        return row

    def _detail(self, post_id: str) -> dict[str, Any]:
        row = self._listing(post_id)
        row.update(
            {
                "orgName": "子公司"
                if self.wrong_detail and post_id == "1"
                else "中联重科股份有限公司",
                "education": "本科及以上",
                "workContent": "负责技术研发",
                "serviceCondition": "2027届本科毕业生",
            }
        )
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
        assert form["coordinateLat"] == form["coordinateLng"] == ""
        page = int(form["currentPage"])
        ids = range(1, 11) if page == 1 else range(11, 17)
        return {
            "state": "200",
            "data": {
                "pageForm": {
                    "dataCount": 16,
                    "totalPage": 2,
                    "pageSize": 10,
                    "currentPage": page,
                    "pageData": [self._listing(str(i)) for i in ids],
                }
            },
        }


async def test_zoomlion_mobile_scope_and_details(now: datetime) -> None:
    replay = ZoomlionReplay()
    source = Source(
        source_id="COM0304",
        company_id="COM0304",
        company="中联重科股份有限公司",
        url=f"https://wecruit.hotjob.cn/{Zoomlion2027.suite}/mc/position/campus",
    )
    result = await Zoomlion2027(source, replay, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].unique == 16
    assert result.scopes[0].details == 7
    assert result.scopes[0].skipped_out_of_scope == 9
    assert len(result.jobs) == 7
    assert all("/mc/detail?" in job.source_url for job in result.jobs)


async def test_zoomlion_rejects_detail_legal_entity_conflict(now: datetime) -> None:
    replay = ZoomlionReplay(wrong_detail=True)
    source = Source(
        source_id="COM0304",
        company_id="COM0304",
        company="中联重科股份有限公司",
        url=f"https://wecruit.hotjob.cn/{Zoomlion2027.suite}/mc/position/campus",
    )
    result = await Zoomlion2027(source, replay, now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 6
    assert any(issue.job_key == "1" for issue in result.issues)


class WanhuaReplay(Replay):
    def __init__(self, *, wrong_detail: bool = False):
        super().__init__()
        self.wrong_detail = wrong_detail

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = super()._listing(post_id)
        row.update(
            {
                "postName": f"研发工程师-{post_id}",
                "company": "万华化学集团股份有限公司",
                "orgCode": "0",
                "projectName": "本硕博招聘",
                "projectId": 100001,
            }
        )
        return row

    def _detail(self, post_id: str) -> dict[str, Any]:
        row = self._listing(post_id)
        row.update(
            {
                "orgName": "另一法人"
                if self.wrong_detail and post_id == "a"
                else "万华化学集团股份有限公司",
                "education": "本科及以上",
                "workContent": "负责化工研发",
                "serviceCondition": "2027届本科毕业生",
            }
        )
        return {"state": "200", "data": row}


async def test_wanhua_2027_pagination_and_legal_identity(now: datetime) -> None:
    source = Source(
        source_id="COM0139",
        company_id="COM0139",
        company="万华化学集团股份有限公司",
        url=f"https://wecruit.hotjob.cn/{Wanhua2027.suite}/pb/school.html",
    )
    result = await Wanhua2027(source, WanhuaReplay(), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert len(result.jobs) == 3
    assert all(job.unit == "万华化学集团股份有限公司" for job in result.jobs)

    wrong = await Wanhua2027(source, WanhuaReplay(wrong_detail=True), now).collect()
    assert wrong.coverage_issues()
    assert len(wrong.jobs) == 2
    assert any(issue.job_key == "a" for issue in wrong.issues)


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


@pytest.mark.parametrize("tenant", [HuaXia, BbmgCampus])
async def test_hotjob_accepts_a_counted_empty_campus_catalog(
    now: datetime, tenant: type[Hotjob]
) -> None:
    source = Source(
        source_id="SITE",
        company_id="SITE",
        company="企业",
        url=f"https://{tenant.host}{tenant.path}",
    )
    result = await tenant(source, Replay(empty=True), now).collect()

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


async def test_luxshare_only_collects_explicit_listed_company_branch(now: datetime) -> None:
    class OrganizationReplay(Replay):
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
                                    {
                                        "code": "0/36",
                                        "nameCh": "立讯精密工业股份",
                                        "positionsNum": 1,
                                    },
                                    {"code": "0/45", "nameCh": "华南园区", "positionsNum": 1},
                                    {"code": "0/44", "nameCh": "华东园区", "positionsNum": 1},
                                    {"code": "0/210201", "nameCh": "京西国际", "positionsNum": 0},
                                ]
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
            return await super().observed(needle)

        def _listing(self, post_id: str) -> dict[str, Any]:
            row = super()._listing(post_id)
            code, company = {
                "a": ("0/36", "立讯精密工业股份"),
                "b": ("0/45", "华南园区"),
                "c": ("0/44", "华东园区"),
            }[post_id]
            row["orgCode"] = "0/999" if self.unknown_code and post_id == "c" else code
            row["company"] = company
            return row

    source = Source(
        source_id="COM0079",
        company_id="COM0079",
        company="立讯精密工业股份有限公司",
        url=f"https://wecruit.hotjob.cn/{Luxshare.suite}/pb/school.html",
    )
    result = await Luxshare(source, OrganizationReplay(), now).collect()
    assert result.coverage_issues() == []
    assert [job.source_key for job in result.jobs] == ["a"]
    assert result.scopes[0].skipped_out_of_scope == 2
    unknown = OrganizationReplay()
    unknown.unknown_code = True
    assert (await Luxshare(source, unknown, now).collect()).coverage_issues()


async def test_eve_energy_only_collects_verified_headquarters_code(now: datetime) -> None:
    class CompanyReplay(Replay):
        bad_detail = False
        unknown_code = False

        def _listing(self, post_id: str) -> dict[str, Any]:
            row = super()._listing(post_id)
            row["orgCode"] = {
                "a": "0/108547",
                "b": "0",
                "c": "0/108528/106673",
            }[post_id]
            if self.unknown_code and post_id == "c":
                row["orgCode"] = "0/999"
            row["company"] = "亿纬锂能"
            row["workPlaceStr"] = "惠州市" if post_id == "a" else "荆门市"
            return row

        def _detail(self, post_id: str) -> dict[str, Any]:
            result = super()._detail(post_id)
            result["data"]["orgName"] = "其他公司" if self.bad_detail else "亿纬锂能"
            return result

    source = Source(
        source_id="COM0278",
        company_id="COM0278",
        company="惠州亿纬锂能股份有限公司",
        url=f"https://wecruit.hotjob.cn/{EveEnergy.suite}/pb/school.html",
    )
    result = await EveEnergy(source, CompanyReplay(), now).collect()
    assert result.coverage_issues() == []
    assert [job.source_key for job in result.jobs] == ["a"]
    assert result.scopes[0].skipped_out_of_scope == 2
    bad_detail = CompanyReplay()
    bad_detail.bad_detail = True
    assert (await EveEnergy(source, bad_detail, now).collect()).coverage_issues()
    unknown = CompanyReplay()
    unknown.unknown_code = True
    assert (await EveEnergy(source, unknown, now).collect()).coverage_issues()


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


class DbnReplay(Replay):
    def __init__(self, conflict: str = "") -> None:
        super().__init__()
        self.conflict = conflict

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = super()._listing(post_id)
        row.update(
            company="河南区" if post_id == "c" else "钦州大北农饲料科技有限公司",
            orgCode="0/209663/278705" if post_id == "c" else "0/198908/198909/218072",
        )
        if post_id == "b":
            row.update(
                publishFirstDate="2025-12-22 11:48:23",
                publishDate="2026-10-10 11:29:54",
                endDate="2026-04-09 23:59:59",
            )
        if post_id == "c":
            row.pop("publishFirstDate")
        return row

    def _detail(self, post_id: str) -> dict[str, Any]:
        detail = super()._detail(post_id)
        detail["data"]["orgName"] = (
            "财务综合室" if post_id == "a" else self._listing(post_id)["company"]
        )
        if post_id == "c" and self.conflict:
            detail["data"][self.conflict] = "不同记录"
        return detail


@pytest.mark.parametrize("conflict", ["", "postName", "orgCode", "company"])
async def test_dbn_first_publication_expiry_and_detail_identity(
    conflict: str, now: datetime
) -> None:
    source = Source(
        source_id="COM0459",
        company_id="COM0459",
        company="北京大北农科技集团股份有限公司",
        url=f"https://wecruit.hotjob.cn/{DbnCampus.suite}/pb/school.html",
    )
    replay = DbnReplay(conflict)
    result = await DbnCampus(source, replay, now).collect()
    scope = result.scopes[0]
    assert scope.expected == scope.listed == scope.unique == 3
    assert scope.terminal and scope.skipped_expired == 1
    expired = next(job for job in result.jobs if job.source_key == "b")
    assert expired.published == "2025-12-22 11:48:23"
    assert expired.deadline == "2026-04-09 23:59:59"
    assert expired.detail_mode == "listing_only"
    assert all(form.get("postId") != "b" for _, form in replay.calls)
    assert result.jobs[0].unit == "钦州大北农饲料科技有限公司 / 财务综合室"
    if conflict:
        assert result.coverage_issues()
        assert scope.details == 1
        assert [job.source_key for job in result.jobs] == ["a", "b"]
        assert "与列表不一致" in result.issues[0].message
    else:
        assert not result.coverage_issues()
        assert scope.details == 2
        unknown_date = result.jobs[-1]
        assert unknown_date.source_key == "c" and unknown_date.published == ""
        assert unknown_date.unit == "河南区"
        assert "不使用publishDate" in unknown_date.field_sources["published"]


class FarEastReplay(Replay):
    def __init__(self, fault: str = "") -> None:
        super().__init__()
        self.fault = fault

    async def observed(self, needle: str) -> dict[str, Any]:
        result = await super().observed(needle)
        if "listSearchTerm" in needle:
            terms = json.loads(result["body"])
            child = {
                "code": "0/9/39/85",
                "nameCh": "安徽电缆股份有限公司",
                "positionsNum": 2 if self.fault == "child_count" else 1,
                "childNodes": [],
            }
            own = {
                "code": "0/9/39",
                "nameCh": "错误名称" if self.fault == "own_name" else "远东智慧能源股份有限公司",
                "positionsNum": 3 if self.fault == "own_count" else 2,
                "childNodes": [child, child] if self.fault == "duplicate" else [child],
            }
            terms["data"]["orgList"] = [
                {
                    "code": "0/9",
                    "nameCh": "远东控股集团有限公司",
                    "positionsNum": 3,
                    "childNodes": [own],
                }
            ]
            result["body"] = json.dumps(terms, ensure_ascii=False)
        return result

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = super()._listing(post_id)
        company, code = {
            "a": ("安徽电缆股份有限公司", "0/9/39/85/1550"),
            "b": ("远东控股集团有限公司", "0/9/32"),
            "c": ("远东智慧能源股份有限公司", "0/9/39/1719"),
        }[post_id]
        row.update(company=company, orgCode=code, postName="2027届技术营销校招生")
        if post_id == "c":
            row.pop("publishFirstDate")
            if self.fault == "unknown_branch":
                row["orgCode"] = "0/99/39"
            if self.fault == "wrong_company":
                row["company"] = "远东控股集团有限公司"
        return row

    def _detail(self, post_id: str) -> dict[str, Any]:
        result = super()._detail(post_id)
        result["data"]["orgName"] = "西北片区" if post_id == "a" else "研究院"
        if post_id == "c" and self.fault in {"postName", "company", "orgCode", "postId"}:
            result["data"][self.fault] = "其他岗位"
        return result


def fareast_source() -> Source:
    return Source(
        source_id="COM0470",
        company_id="COM0470",
        company="远东智慧能源股份有限公司",
        url=f"https://wecruit.hotjob.cn/{FarEastListedCampus.suite}/pb/school.html",
    )


async def test_fareast_accounts_for_every_tree_level_and_keeps_same_title(now: datetime) -> None:
    replay = FarEastReplay()
    result = await FarEastListedCampus(fareast_source(), replay, now).collect()
    assert not result.coverage_issues()
    scope = result.scopes[0]
    assert scope.expected == scope.unique == scope.listed == 3
    assert scope.terminal
    assert [form["currentPage"] for _, form in replay.calls if "currentPage" in form] == ["1", "2"]
    assert scope.details == 2 and scope.skipped_out_of_scope == 1
    assert [job.source_key for job in result.jobs] == ["a", "c"]
    assert result.jobs[0].title == result.jobs[1].title
    assert result.jobs[0].unit == "安徽电缆股份有限公司 / 西北片区"
    assert result.jobs[1].unit == "远东智慧能源股份有限公司 / 研究院"
    assert result.jobs[1].published == ""
    assert all(form.get("postId") != "b" for _, form in replay.calls)


@pytest.mark.parametrize(
    "fault",
    [
        "child_count",
        "own_count",
        "own_name",
        "duplicate",
        "unknown_branch",
        "wrong_company",
        "postName",
        "company",
        "orgCode",
        "postId",
    ],
)
async def test_fareast_rejects_scope_and_identity_drift(fault: str, now: datetime) -> None:
    result = await FarEastListedCampus(fareast_source(), FarEastReplay(fault), now).collect()
    assert result.coverage_issues()
    if fault in {"postName", "company", "orgCode", "postId"}:
        assert [job.source_key for job in result.jobs] == ["a"]
        assert result.scopes[0].details == 1


def test_fareast_public_field_fixture(now: datetime) -> None:
    data = json.loads(Path("tests/fixtures/hotjob/COM0470.json").read_text())
    adapter = FarEastListedCampus(fareast_source(), FarEastReplay(), now)
    job = adapter._job(data["detail"], data["listing"], "detail", {}, "tree")
    assert job.source_key == "6ad07ebcf0cfabf2b4f31084"
    assert job.unit == "安徽电缆股份有限公司 / 西北片区"
    assert job.location == "滁州市-天长市" and job.education == "本科"
    assert "【能力要求】" in job.duties and job.requirements == ""
    assert job.published == "2026-10-15 15:20:15"
    assert job.deadline == "2027-01-15 23:59:59"


class UnisocReplay(Replay):
    def __init__(self, *, wrong_company: bool = False, wrong_project: bool = False) -> None:
        super().__init__()
        self.wrong_company = wrong_company
        self.wrong_project = wrong_project

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = super()._listing(post_id)
        row["company"] = "其他企业" if self.wrong_company and post_id == "b" else "紫光展锐"
        row["projectName"] = "实习" if self.wrong_project and post_id == "b" else "2027届秋招"
        return row


@pytest.mark.parametrize("fault", ["", "wrong_company", "wrong_project"])
async def test_unisoc_campus_scope_and_identity(fault: str, now: datetime) -> None:
    source = Source(
        source_id="COM0524",
        company_id="COM0524",
        company="紫光展锐",
        url=f"https://wecruit.hotjob.cn/{UnisocCampus2027.suite}/pb/index.html",
    )
    replay = UnisocReplay(
        wrong_company=fault == "wrong_company", wrong_project=fault == "wrong_project"
    )
    result = await UnisocCampus2027(source, replay, now).collect()
    assert replay.opens[0].endswith("/pb/school.html")
    if fault:
        assert result.coverage_issues()
    else:
        assert not result.coverage_issues()
        assert result.scopes[0].expected == 3 and result.scopes[0].terminal
        assert len(result.jobs) == 3
        assert result.jobs[0].published == "2026-10-10 09:00:00"


class GoermicroReplay(Replay):
    def __init__(self, *, wrong_company: bool = False) -> None:
        super().__init__()
        self.wrong_company = wrong_company

    def _listing(self, post_id: str) -> dict[str, Any]:
        row = super()._listing(post_id)
        row["company"] = "其他企业" if self.wrong_company and post_id == "c" else "歌尔微电子"
        row["postTypeName"] = "校园精英招聘" if post_id == "c" else "校园招聘"
        row["postName"] = f"{'2026届' if post_id == 'b' else '2027届'}精英计划-{post_id}"
        row["projectName"] = "日常招聘"
        return row


@pytest.mark.parametrize("wrong_company", [False, True])
async def test_goermicro_2027_scope(now: datetime, wrong_company: bool) -> None:
    source = Source(
        source_id="COM0556",
        company_id="COM0556",
        company="歌尔微电子",
        url=f"https://wecruit.hotjob.cn/{GoermicroCampus2027.suite}/pb/school.html",
    )
    result = await GoermicroCampus2027(
        source, GoermicroReplay(wrong_company=wrong_company), now
    ).collect()
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert result.scopes[0].skipped_out_of_scope == 1
    if wrong_company:
        assert result.coverage_issues()
    else:
        assert not result.coverage_issues()
        assert [job.title for job in result.jobs] == ["2027届精英计划-a", "2027届精英计划-c"]
        assert result.jobs[0].published == "2026-10-10 09:00:00"
