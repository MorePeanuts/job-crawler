"""Deterministic contracts for the added public catalogs; no live network."""

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from test_adapters import source
from test_transport import Page

from job_crawler.adapters.anker import AnkerCampus
from job_crawler.adapters.chinatower import JacCampus, validate_page
from job_crawler.adapters.extra_catalogs import ZhinkCampus
from job_crawler.adapters.inline_catalogs import CndCampus, MideaCampus
from job_crawler.adapters.moka import Nongfu
from job_crawler.adapters.nci import parse_nci
from job_crawler.adapters.sinopharm import SinopharmCampus
from job_crawler.config import CrawlConfig
from job_crawler.storage import Store
from job_crawler.transport import BrowserSession, CrawlError


class Replay:
    output = Path(".")
    last_evidence = "public-evidence.json"

    def __init__(self, observed: dict[str, Any], response: dict[str, Any]):
        self.response = response
        self.observation = observed
        self.calls: list[dict[str, Any]] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def observed(self, needle: str) -> dict[str, Any]:
        return self.observation

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "include",
    ) -> dict[str, Any]:
        self.calls.append({"url": url, "payload": payload, "credentials": credentials})
        return copy.deepcopy(self.response)


def cnd_response(total: int = 1) -> dict[str, Any]:
    return {
        "success": True,
        "code": 200,
        "result": {
            "total": total,
            "current": 1,
            "size": 10,
            "pages": (total + 9) // 10,
            "records": [
                {
                    "id": "a",
                    "externalAliase": "采购岗",
                    "jobState": "12030004",
                    "jobDescribe": "采购执行",
                    "jobRequirement": "本科及以上",
                    "workAddrName": "厦门市",
                    "interviewCity": "北京市",
                    "education": "本科",
                    "publishTime": "2026-10-13",
                }
            ],
        },
    }


async def test_cnd_uses_work_city_not_interview_city(now: datetime) -> None:
    body = cnd_response()
    session = Replay({"url": "https://campus.chinacnd.com/list", "body": json.dumps(body)}, body)
    result = await CndCampus(source(CndCampus.host), session, now).collect()
    assert not result.coverage_issues()
    assert result.jobs[0].location == "厦门市" and result.jobs[0].published == "2026-10-13"
    assert not session.calls


async def test_cnd_repeated_page_cannot_be_complete(now: datetime) -> None:
    body = cnd_response(11)
    session = Replay({"url": "https://campus.chinacnd.com/list", "body": json.dumps(body)}, body)
    result = await CndCampus(source(CndCampus.host), session, now).collect()
    assert result.coverage_issues() and len(result.jobs) == 1
    assert "页码" in result.issues[0].message


@pytest.mark.parametrize("bad_field", ["jobState", "jobDescribe"])
async def test_cnd_fails_closed_on_status_or_body_change(now: datetime, bad_field: str) -> None:
    body = cnd_response()
    body["result"]["records"][0][bad_field] = ""
    result = await CndCampus(
        source(CndCampus.host), Replay({"url": "x", "body": json.dumps(body)}, body), now
    ).collect()
    assert result.coverage_issues() and not result.jobs


async def test_midea_enumerates_regular_projects_and_rejects_wrong_detail(now: datetime) -> None:
    class MideaReplay(Replay):
        async def observed(self, needle: str) -> dict[str, Any]:
            if needle == MideaCampus.project_endpoint:
                return {
                    "body": json.dumps(
                        {
                            "code": 0,
                            "data": [
                                {
                                    "projectRuleId": "a",
                                    "projectRuleName": "本硕",
                                    "status": 1,
                                    "employementCategory": 1,
                                },
                                {
                                    "projectRuleId": "b",
                                    "projectRuleName": "博士",
                                    "status": 1,
                                    "employementCategory": 1,
                                },
                                {"projectRuleId": "intern", "status": 1, "employementCategory": 4},
                            ],
                        }
                    )
                }
            return {"url": "https://example.test/list", "post_data": "{}"}

        async def request(
            self,
            url: str,
            *,
            payload: dict[str, Any] | None = None,
            detail: bool = False,
            credentials: str = "include",
        ) -> dict[str, Any]:
            assert payload is not None
            self.calls.append(payload)
            p = payload["projectRuleId"]
            return {
                "code": 0,
                "data": {
                    "total": 1,
                    "info": {"pageIndex": 1, "totalPage": 1},
                    "data": [
                        {
                            "positionId": "same",
                            "projectRuleId": p,
                            "employementCategory": 1,
                            "projectPositionId": "advert",
                            "projectPositionName": "工程师",
                            "projectPositionDto": {
                                "projectPositionId": "wrong" if p == "b" else "advert",
                                "jobResponsibility": "研发",
                                "jobRequirement": "本科",
                            },
                        }
                    ],
                },
            }

    replay = MideaReplay({}, {})
    result = await MideaCampus(source(MideaCampus.host), replay, now).collect()
    assert [p["projectRuleId"] for p in replay.calls] == ["a", "b"]
    assert len(result.jobs) == 1 and result.jobs[0].source_key == "a:same"
    assert result.coverage_issues()


async def test_sinopharm_shared_project_preserves_social_type_and_deadline(now: datetime) -> None:
    rows = [
        {
            "job_id": str(i),
            "job_name": "岗位",
            "recruitment_type_cn": kind,
            "nature_cn": "校招" if kind == "校园招聘" else "社招",
            "contents": "【岗位职责】\n做研发\n【任职条件】\n本科",
            "district_list": [{"area_cn": "厦门", "address": "园区"}],
            "company_name": "企业",
            "education_cn": "本科",
            "end_time": "2026-12-31",
            "start_time": "2026-08-01",
            "category_cn": "研发",
        }
        for i, kind in enumerate(["校园招聘", "社会招聘"])
    ]
    response = {"code": 200, "data": {"page": 1, "page_size": 20, "total": 2, "list": rows}}
    payload = {
        "page": 1,
        "page_size": 20,
        "source": "s_job_list",
        "project_id": [SinopharmCampus.project],
    }
    session = Replay(
        {"url": "https://gp-api.iguopin.com/list", "post_data": json.dumps(payload)}, response
    )
    result = await SinopharmCampus(source(SinopharmCampus.host), session, now).collect()
    assert not result.coverage_issues()
    assert [j.work_type for j in result.jobs] == ["校招", "社会招聘"]
    assert result.jobs[0].requirements == "本科" and not result.jobs[0].published
    assert result.jobs[0].deadline == "2026-12-31"
    assert session.calls[0]["credentials"] == "omit"


async def test_zhink_ignores_backend_creation_date_and_rejects_hidden_jobs(now: datetime) -> None:
    row = {
        "id": "a",
        "type": "1",
        "isShow": "Y",
        "delFlag": 0,
        "positionName": "开发",
        "jobDesc": "职责",
        "jobRequirement": "本科",
        "createTime": "2026-10-13",
    }
    response = {
        "success": True,
        "code": 200,
        "result": {"current": 1, "size": 1000, "pages": 1, "total": 1, "records": [row]},
    }
    observation = {
        "url": "https://www.zhink.cc/list?tenantId=1&type=1&positionName=&workingPlace=&companyName="
    }
    session = Replay(observation, response)
    result = await ZhinkCampus(source(ZhinkCampus.host), session, now).collect()
    assert not result.coverage_issues() and result.jobs[0].published == ""
    row["isShow"] = "N"
    result = await ZhinkCampus(source(ZhinkCampus.host), session, now).collect()
    assert result.coverage_issues() and not result.jobs


def hcm_page() -> dict[str, Any]:
    return {
        "total": 21,
        "size": 20,
        "current": 2,
        "model_page": 2,
        "fetching": False,
        "pages": 2,
        "selected_departments": 0,
        "rows": [{"id": 21}],
        "deadline_label": "职位申请结束时间",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        {"model_page": 1},
        {"fetching": True},
        {"rows": []},
        {"total": 22},
        {"selected_departments": 1},
        {"deadline_label": "更新时间"},
    ],
)
def test_virtual_table_requires_current_complete_unfiltered_page(mutation: dict[str, Any]) -> None:
    data = hcm_page()
    assert validate_page(data, 2, 21) == 21
    data.update(mutation)
    with pytest.raises(CrawlError):
        validate_page(data, 2, 21)


def test_jac_public_flag_is_not_job_status_and_dates_not_invented(now: datetime) -> None:
    adapter = JacCampus(source(JacCampus.host), Replay({}, {}), now)
    row = {
        "id": 1,
        "name": "工程师",
        "job_class": "校园招聘",
        "job_property": "全职",
        "is_open": False,
        "status": 1,
        "job_desc": "任职要求：\n本科\n岗位描述：\n开发",
        "background": 2,
        "department_name": "技术部",
        "address_multi": ["合肥市"],
        "work_city": "合肥市",
        "work_address": "园区",
        "release_date": "2026-10-09",
        "auto_offline_date": "2027-01-01",
    }
    job = adapter.parse_job(
        row, {"education_labels": {"2": "本科及以上"}, "url": "https://example.test"}
    )
    assert not job.closed and job.duties == "开发" and job.requirements == "本科"
    assert job.deadline == "" and job.published == "2026-10-09"
    row["status"] = 2
    assert adapter.parse_job(row, {"education_labels": {"2": "本科及以上"}, "url": "x"}).closed


def test_nongfu_requires_detail_company_and_excludes_other_group_companies(now: datetime) -> None:
    adapter = Nongfu(source(Nongfu.host), Replay({}, {}), now)
    adapter.departments = {"1867931": "农夫山泉股份有限公司"}
    row = {
        "id": "a",
        "title": "工程师",
        "status": "open",
        "jobDescription": "岗位职责\n研发\n任职要求\n本科",
        "deptId": 123,
    }
    assert adapter._job(row, row, "evidence").work_type == "校招"
    detail = {**row, "department": {"id": 1867931, "name": "农夫山泉股份有限公司"}}
    assert adapter._job(detail, row, "evidence", is_detail=True).unit == "农夫山泉股份有限公司"
    detail["department"] = {"id": 1874073, "name": "养生堂有限公司"}
    assert adapter._job(detail, row, "evidence", is_detail=True).work_type == "非农夫山泉主体"
    with pytest.raises(CrawlError):
        adapter._job(row, row, "evidence", is_detail=True)


def test_nci_title_attribute_preserves_full_location_and_page_evidence() -> None:
    html = '<p>共1条记录 当前第1/1页</p><li><h1 class="zwlblit"><span>开发</span><span title="完整企业">企业...</span><span title="北京、上海">北京...</span><span>1</span><span>2026-10-10</span></h1><a class="ljyp" jobadid="1"></a><div class="zwms"><b class="zwmsl">职位描述：</b><p class="zwmsr">研发</p></div><div class="zwms"><b class="zwmsl">任职要求：</b><p class="zwmsr">本科</p></div></li>'
    total, page, pages, rows = parse_nci(html)
    assert (total, page, pages) == (1, 1, 1) and rows[0]["location"] == "北京、上海"
    with pytest.raises(CrawlError):
        parse_nci(html.replace("共1条", "共2条"))


def test_anker_full_address_and_unpublished_dates(now: datetime) -> None:
    row = {
        "id": "1",
        "title": "研发",
        "job_department": {"name": {"zh_cn": "技术部"}},
        "job_recruitment_type": {"name": {"zh_cn": "正式"}},
        "job_active_status": 1,
        "description": "开发",
        "requirement": "本科",
        "create_time": "1791000000000",
        "address_list": [
            {
                "state": {"name": {"zh_cn": "广东"}},
                "city": {"name": {"zh_cn": "深圳"}},
                "district": {"name": {"zh_cn": "宝安"}},
                "name": {"zh_cn": "研发楼"},
            }
        ],
    }
    job = AnkerCampus(source(AnkerCampus.host), Replay({}, {}), now).from_detail(
        row, "https://example.test/1"
    )
    assert job.address == "广东深圳宝安研发楼" and job.location == "广东深圳宝安"
    assert job.published == "" and job.deadline == "" and job.work_type == "校招"


async def test_public_cross_origin_credential_mode_separates_cache(
    tmp_path: Path, now: datetime
) -> None:
    store = Store(tmp_path / "state.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0), resume=True
    )
    page = Page()
    session.page = page
    try:
        await session.request("https://example.test/job", detail=True)
        await session.request("https://example.test/job", detail=True, credentials="omit")
        await session.request("https://example.test/job", detail=True, credentials="omit")
        assert page.calls == 2 and '"credentials": "omit"' in page.scripts[1]
        with pytest.raises(ValueError):
            await session.request("https://example.test/job", credentials="invalid")
    finally:
        store.close()


async def test_html_with_legitimate_preface_resources(tmp_path: Path, now: datetime) -> None:
    class PrefacePage(Page):
        async def evaluate(self, script: str) -> dict[str, Any]:
            return {
                "status": 200,
                "url": "https://example.test/jobs",
                "body": '\n<link href="a.css">' * 300 + "<html><body>岗位</body></html>",
            }

    store = Store(tmp_path / "state.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession("A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0))
    session.page = PrefacePage()
    try:
        assert "岗位" in await session.request_html("https://example.test/jobs")
    finally:
        store.close()


async def test_sunwoda_two_categories_and_cross_category_duplicate(now: datetime) -> None:
    from job_crawler.adapters.sunwoda import SunwodaCampus

    class SunReplay(Replay):
        category = "2"
        duplicate = False

        async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
            self.category = "1547436687" if "/1547436687/" in url else "2"

        async def observed(self, needle: str) -> dict[str, Any]:
            return {
                "url": "https://example.test/list",
                "post_data": json.dumps({"Category": [self.category]}),
            }

        async def request(
            self,
            url: str,
            *,
            payload: dict[str, Any] | None = None,
            detail: bool = False,
            credentials: str = "include",
        ) -> dict[str, Any]:
            assert payload is not None
            c = payload["Category"][0]
            return {
                "Code": 200,
                "Count": 1,
                "Data": [
                    {
                        "Id": "same" if self.duplicate else c,
                        "CategoryId": c,
                        "Category": "应届博士招聘" if c != "2" else "校园招聘",
                        "JobAdName": "研发",
                        "Duty": "开发",
                        "Require": "要求",
                        "EndTime": "0001-01-01",
                    }
                ],
            }

    replay = SunReplay({}, {})
    result = await SunwodaCampus(source(SunwodaCampus.host), replay, now).collect()
    assert not result.coverage_issues() and len(result.scopes) == 2
    assert result.jobs[1].education == "博士" and result.jobs[0].education == ""
    assert all(j.deadline == "" for j in result.jobs)
    replay.duplicate = True
    result = await SunwodaCampus(source(SunwodaCampus.host), replay, now).collect()
    assert result.coverage_issues() and len(result.jobs) == 1


async def test_kuaishou_nested_dictionary_and_false_last_page(now: datetime) -> None:
    from job_crawler.adapters.inline_catalogs import KuaishouCampus

    class KuaishouReplay(Replay):
        terminal = True

        async def observed(self, needle: str) -> dict[str, Any]:
            if "dictionary" in needle:
                return {
                    "body": json.dumps(
                        {
                            "code": 0,
                            "result": {
                                "recruitSubProject": [
                                    {"code": KuaishouCampus.project, "name": "2027应届生"}
                                ],
                                "positionCategory": [
                                    {
                                        "code": "root",
                                        "name": "研发",
                                        "children": [{"code": "child", "name": "软件"}],
                                    }
                                ],
                            },
                        }
                    )
                }
            return {
                "url": "https://example.test/list",
                "post_data": json.dumps({"recruitSubProjectCodes": [KuaishouCampus.project]}),
            }

        async def request(
            self,
            url: str,
            *,
            payload: dict[str, Any] | None = None,
            detail: bool = False,
            credentials: str = "include",
        ) -> dict[str, Any]:
            return {
                "code": 0,
                "result": {
                    "pageNum": 1,
                    "pages": 1,
                    "total": 1,
                    "isLastPage": self.terminal,
                    "list": [
                        {
                            "code": "a",
                            "name": "研发",
                            "recruitSubProjectCode": KuaishouCampus.project,
                            "recruitProjectCode": "schoolr",
                            "positionStatusCode": "Release",
                            "ifShowRecruitWebsite": True,
                            "description": "职责",
                            "positionDemand": "要求",
                            "positionNatureCode": "fulltime",
                            "positionCategoryCode": "child",
                            "releaseTime": "2026-10-13",
                            "updateTime": "2026-10-14",
                        }
                    ],
                },
            }

    replay = KuaishouReplay({}, {})
    result = await KuaishouCampus(source(KuaishouCampus.host), replay, now).collect()
    assert not result.coverage_issues() and result.jobs[0].category_raw == "软件"
    assert result.jobs[0].published == "2026-10-13"
    replay.terminal = False
    result = await KuaishouCampus(source(KuaishouCampus.host), replay, now).collect()
    assert result.coverage_issues()


async def test_kingfa_requires_matching_html_advertisement_id(
    now: datetime, tmp_path: Path
) -> None:
    from job_crawler.adapters.extra_catalogs import KingfaCampus

    data = {
        "error": 0,
        "category_id": 459,
        "more_data": 0,
        "data": '<a href="/portal/article/job_details/job_id/10/cid/459/idtype/2/frist/20.html">岗位</a>',
        "job_list": [
            {
                "Id": 20,
                "JobId": 10,
                "Category": 2,
                "CategoryDescription": "校园招聘",
                "Status": 1,
                "IsDeleted": False,
                "Duty": "开发",
                "Requirements": "本科",
                "JobTitle": "工程师",
                "KindDescription": "全职",
            }
        ],
    }
    session = Replay(
        {
            "url": "https://example.test/list",
            "post_data": "category_id=459&jobad_category=2&page_num=1&page_size=20&list_tpl=list_job",
            "body": json.dumps(data),
        },
        data,
    )
    session.output = tmp_path
    result = await KingfaCampus(source(KingfaCampus.host), session, now).collect()
    assert not result.coverage_issues() and result.jobs[0].source_key == "20"
    assert "/job_id/10/" in result.jobs[0].source_url
    data["job_list"][0]["JobId"] = 11
    session.observation["body"] = json.dumps(data)
    result = await KingfaCampus(source(KingfaCampus.host), session, now).collect()
    assert result.coverage_issues() and not result.jobs


def test_haier_uses_job_own_company_intro_not_hidden_other_units() -> None:
    from job_crawler.adapters.haier import parse_detail

    html = '<div class="inner_details_box"><div class="title_div"><div class="title">研发</div></div><div class="demand_title">岗位描述</div><div class="demand_box">开发</div><div class="demand_title">岗位要求</div><div class="demand_box">本科</div><div class="demand_title">招聘部门</div><div id="department_box"><div class="department_text_item">海尔智家股份有限公司</div><div class="department_text_item primary_content">其他集团成员</div></div></div>'
    assert parse_detail(html, "研发") == ("开发", "本科", False)
    assert parse_detail(html.replace("其他集团成员", "海尔智家股份有限公司"), "研发")[2]
    with pytest.raises(CrawlError):
        parse_detail(html, "不同职位")
    with pytest.raises(CrawlError):
        parse_detail(html.replace("primary_content", "unknown"), "研发")


async def test_gbk_html_mode_has_distinct_cache_and_decoder(tmp_path: Path, now: datetime) -> None:
    class HTMLPage(Page):
        async def evaluate(self, script: str) -> dict[str, Any]:
            self.calls += 1
            self.scripts.append(script)
            return {"status": 200, "url": "https://example.test/job", "body": "<html>本科</html>"}

    store = Store(tmp_path / "state.sqlite")
    store.begin("run", "hash", now, False, 6)
    session = BrowserSession(
        "A", "run", tmp_path / "evidence", store, CrawlConfig(delay=0), resume=True
    )
    page = HTMLPage()
    session.page = page
    try:
        await session.request_html("https://example.test/job", detail=True)
        await session.request_html("https://example.test/job", detail=True, encoding="gb18030")
        await session.request_html("https://example.test/job", detail=True, encoding="gb18030")
        assert page.calls == 2 and 'TextDecoder("gb18030")' in page.scripts[1]
    finally:
        store.close()
