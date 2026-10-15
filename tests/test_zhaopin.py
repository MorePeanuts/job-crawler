import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhaopin import (
    ChinaPost2027,
    Fosun2027,
    Longfor2027,
    Unicom,
    split_detail,
)
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, *, repeated: bool = False, changed_count: bool = False):
        self.repeated = repeated
        self.changed_count = changed_count
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://zglt.zhaopin.com/scjobs/index.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle.endswith("/search-job-list")
        return {
            "url": needle,
            "post_data": json.dumps(
                {
                    "orgNumbers": ["105347"],
                    "jobSource": 2,
                    "pageIndex": 1,
                    "pageSize": 11,
                    "orgDepartmentIds": [123],
                    "workRegionIds": "",
                    "jobTypes": "",
                    "priorityMajors": "",
                    "customTags": "",
                    "campusParentDepartmentIds": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and payload["orgDepartmentIds"] == []
        assert payload["jobSource"] == 2 and payload["orgNumbers"] == ["105347"]
        page = int(payload["pageIndex"])
        self.pages.append(page)
        start = 0 if self.repeated else (page - 1) * 50
        rows = [
            {
                "company": {"companyId": 105347, "campusOrgName": "北京市分公司"},
                "job": {
                    "jobNumber": f"CC{i}",
                    "positionSourceType": 2,
                    "title": f"工程师{i}",
                    "detail": "岗位职责：开发软件\n任职要求：本科及以上",
                    "url": f"https://xiaoyuan.zhaopin.com/job/CC{i}",
                    "deliveryPath": f"https://campus1.zhaopin.com/Resume/CheckIntoApp?pid=CC{i}",
                    "address": "北京",
                    "minEducationName": "本科",
                    "jobTypeName": "软件工程师",
                    "modifiedTime": 1790000000000,
                },
            }
            for i in range(start, min(start + 50, 51))
        ]
        return {
            "code": 200,
            "data": {
                "jobList": rows,
                "pageInfo": {
                    "pageIndex": page,
                    "pageSize": 50,
                    "totalNum": 52 if self.changed_count and page == 2 else 51,
                    "totalPage": 2,
                },
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0069",
        company_id="COM0069",
        company="中国联合网络通信股份有限公司",
        url="https://zglt.zhaopin.com/scjobs/index.html",
    )


async def test_zhaopin_full_unfiltered_catalog(now: datetime) -> None:
    replay = Replay()
    result = await Unicom(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert len(result.jobs) == 51
    assert result.scopes[0].expected == result.scopes[0].details == 51
    assert result.jobs[0].requirements == "本科及以上"
    assert result.jobs[0].published == ""
    assert "modifiedTime" in result.jobs[0].field_sources["published"]


async def test_zhaopin_repeated_page_is_incomplete(now: datetime) -> None:
    result = await Unicom(source(), Replay(repeated=True), now).collect()
    assert result.coverage_issues()
    assert any(issue.code == "duplicate_page" for issue in result.issues)


async def test_zhaopin_total_change_is_incomplete(now: datetime) -> None:
    result = await Unicom(source(), Replay(changed_count=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 50


def test_zhaopin_detail_without_requirements() -> None:
    assert split_detail("负责开发软件") == ("负责开发软件", "")


class FosunReplay:
    last_evidence = "fosun-evidence.json"

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://fosun.zhaopin.com/job/index.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        if "get-search-aggregation" in needle:
            units = [
                {
                    "name": f"N{n}",
                    "count": 3 if n == 0 else 0,
                    "extend": {
                        "campusOrgName": f"单位{n}",
                        "companyInfo": json.dumps(
                            {"campusOrgName": f"单位{n}", "rootOrgId": 102124}
                        ),
                    },
                }
                for n in range(10)
            ]
            return {
                "post_data": json.dumps(
                    {"orgNumber": "102124", "jobSource": 2, "facetFields": ["SOU_COMPANY_ID"]}
                ),
                "body": json.dumps({"code": 200, "data": {"itemMap": {"SOU_COMPANY_ID": units}}}),
            }
        return {
            "url": needle,
            "post_data": json.dumps(
                {
                    "orgNumbers": ["102124"],
                    "jobSource": 2,
                    "pageIndex": 1,
                    "customTags": "复星财富",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        if "get-search-aggregation" in url:
            observed = await self.observed(url)
            assert payload is not None and payload["facetFields"] == ["SOU_COMPANY_ID"]
            return json.loads(observed["body"])
        assert payload is not None and payload["customTags"] == ""
        assert payload["pageIndex"] == 1
        rows = [
            {
                "company": {
                    "companyId": 102124,
                    "companyNumber": "N0",
                    "campusOrgName": "单位0",
                    "slaveDisplayOrgName": "上海复星高科技（集团）有限公司",
                },
                "job": {
                    "jobNumber": f"F{n}",
                    "positionSourceType": 2,
                    "title": "投资实习生" if n == 2 else f"管培生{n}",
                    "jobCategories": ["实习生招聘"] if n == 2 else ["星冉生"],
                    "detail": "岗位职责：业务分析\n任职要求：本科",
                },
            }
            for n in range(3)
        ]
        return {
            "code": 200,
            "data": {
                "jobList": rows,
                "pageInfo": {"pageIndex": 1, "pageSize": 50, "totalNum": 3, "totalPage": 1},
            },
        }


async def test_fosun_removes_default_tag_and_marks_internships(now: datetime) -> None:
    source = Source(
        source_id="COM0148",
        company_id="COM0148",
        company="复星国际有限公司",
        url="https://fosun.zhaopin.com/job/index.html",
    )
    result = await Fosun2027(source, FosunReplay(), now).collect()
    assert result.coverage_issues() == []
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert [job.work_type for job in result.jobs] == ["校招", "校招", "实习"]
    assert [job.unit for job in result.jobs] == ["单位0"] * 3


class LongforReplay:
    last_evidence = "longfor-list.json"

    def __init__(self, *, foreign: bool = False):
        self.foreign = foreign
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://longfor.zhaopin.com/sgs/index.html#jobs"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": needle,
            "post_data": json.dumps(
                {
                    "orgNumbers": "105173",
                    "jobSource": 2,
                    "pageIndex": 1,
                    "pageSize": 21,
                    "orgDepartmentIds": [10126970],
                    "campusParentDepartmentIds": 10126975,
                    "workRegionIds": "530",
                    "jobTypes": "",
                    "priorityMajors": "",
                    "customTags": "",
                    "keyword": "仕官生",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        assert payload["orgNumbers"] == "105173" and payload["jobSource"] == 2
        assert payload["orgDepartmentIds"] == []
        assert payload["campusParentDepartmentIds"] == payload["workRegionIds"] == ""
        assert payload["keyword"] == ""
        page = int(payload["pageIndex"])
        self.pages.append(page)
        start = (page - 1) * 50
        rows = []
        projects = ("仕官生", "绽放", "点将")
        for i in range(start, min(start + 50, 51)):
            rows.append(
                {
                    "company": {
                        "companyId": 105173,
                        "slaveDisplayOrgName": "其他集团"
                        if self.foreign and i == 50
                        else "龙湖集团",
                        "campusOrgName": projects[i % 3],
                        "campusParentDepartment": {"name": "地产开发"},
                        "campusDepartment": {"name": "北京"},
                    },
                    "job": {
                        "jobNumber": f"LONGFOR{i}",
                        "positionSourceType": 2,
                        "title": f"岗位{i}",
                        "detail": "岗位职责：负责项目管理\n任职要求：本科及以上",
                        "url": f"https://xiaoyuan.zhaopin.com/job/LONGFOR{i}",
                        "address": "北京",
                    },
                }
            )
        return {
            "code": 200,
            "data": {
                "jobList": rows,
                "pageInfo": {
                    "pageIndex": page,
                    "pageSize": 50,
                    "totalNum": 51,
                    "totalPage": 2,
                },
            },
        }


async def test_longfor_clears_local_filters_and_keeps_three_projects(now: datetime) -> None:
    source = Source(
        source_id="COM0206",
        company_id="COM0206",
        company="龙湖集团控股有限公司",
        url="https://longfor.zhaopin.com/sgs/index.html#jobs",
    )
    replay = LongforReplay()
    result = await Longfor2027(source, replay, now).collect()
    assert result.coverage_issues() == []
    assert replay.pages == [1, 2] and len(result.jobs) == 51
    assert {job.unit for job in result.jobs} == {
        "仕官生 / 地产开发 / 北京",
        "绽放 / 地产开发 / 北京",
        "点将 / 地产开发 / 北京",
    }
    foreign = await Longfor2027(source, LongforReplay(foreign=True), now).collect()
    assert foreign.coverage_issues()


class PostReplay:
    last_evidence = "post-tree.json"

    def __init__(self, *, foreign: bool = False, repeated: bool = False):
        self.foreign = foreign
        self.repeated = repeated
        self.pages: list[int] = []
        self.roots = [
            {"id": 100 + i, "parentId": 105582, "companyName": f"第{i}省分公司"} for i in range(30)
        ] + [
            {"id": 200, "parentId": 105582, "companyName": "中国邮政集团有限公司总部"},
            {"id": 201, "parentId": 105582, "companyName": "中邮人寿保险股份有限公司"},
        ]

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://chinapost2027.zhaopin.com/job/index.html?comid=1013109"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle.endswith("/get-sub-company-and-department-list")
        return {
            "url": needle,
            "post_data": json.dumps({"rootCompanyId": "105582", "format": "tree"}),
            "body": json.dumps({"code": 200, "data": {"list": self.roots}}),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        assert len(payload["campusParentDepartmentIds"]) == 31
        assert 201 not in payload["campusParentDepartmentIds"]
        page = int(payload["pageIndex"])
        self.pages.append(page)
        start = 0 if self.repeated else (page - 1) * 100
        rows = []
        for i in range(start, min(start + 100, 101)):
            rows.append(
                {
                    "company": {
                        "companyId": 105582,
                        "slaveDisplayOrgName": "其他法人"
                        if self.foreign and i == 100
                        else "中国邮政集团有限公司",
                        "campusOrgName": "第0省分公司",
                        "campusDepartment": {"name": "市分公司本部"},
                    },
                    "job": {
                        "jobNumber": f"POST{i}",
                        "positionSourceType": 2,
                        "title": f"岗位{i}",
                        "detail": "招聘专业要求：计算机专业",
                        "url": f"https://xiaoyuan.zhaopin.com/job/POST{i}",
                        "address": "北京",
                        "minEducationName": "硕士",
                    },
                }
            )
        return {
            "code": 200,
            "data": {
                "jobList": rows,
                "pageInfo": {
                    "pageIndex": page,
                    "pageSize": 100,
                    "totalNum": 101,
                    "totalPage": 2,
                },
            },
        }


def post_source() -> Source:
    return Source(
        source_id="COM0034",
        company_id="COM0034",
        company="中国邮政集团有限公司",
        url="https://chinapost2027.zhaopin.com/job/index.html?comid=1013109",
    )


async def test_chinapost_all_parent_branches_and_ends_at_count(now: datetime) -> None:
    replay = PostReplay()
    result = await ChinaPost2027(post_source(), replay, now).collect()
    assert result.coverage_issues() == []
    assert replay.pages == [1, 2]
    assert len(result.jobs) == 101
    assert result.jobs[0].unit == "市分公司本部"
    assert result.jobs[0].requirements == "招聘专业要求：计算机专业"
    assert result.jobs[0].duties == result.jobs[0].published == ""


async def test_chinapost_rejects_foreign_or_repeated_rows(now: datetime) -> None:
    for replay in (PostReplay(foreign=True), PostReplay(repeated=True)):
        result = await ChinaPost2027(post_source(), replay, now).collect()
        assert result.coverage_issues()
