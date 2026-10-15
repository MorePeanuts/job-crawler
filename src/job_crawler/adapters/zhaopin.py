"""Verified Zhaopin campus campaigns with a shared public JSON catalog."""

import json
from typing import Any

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope

API = "https://fe.zhaopin.com/grace/api/dsc/search-job-list"
TREE_API = "https://fe.zhaopin.com/grace/api/dsc/get-sub-company-and-department-list"
FILTERS = {
    "orgIds",
    "workExperiences",
    "minSalary",
    "maxSalary",
    "educations",
    "orgScales",
    "employmentTypes",
    "orgNatures",
    "orgDepartmentIds",
    "campusParentDepartmentIds",
    "workRegionIds",
    "jobTypes",
    "priorityMajors",
    "customTags",
    "keyword",
}
ALLOWED = FILTERS | {"orgNumbers", "jobSource", "pageIndex", "pageSize"}


def split_detail(value: str) -> tuple[str, str]:
    return split_sections(value)


class Zhaopin(Adapter):
    org_number = ""
    request_org_number = ""
    job_source = 2
    required_custom_tag = ""
    observed_custom_tag = ""
    page_size = 50
    scope_description = (
        "智联招聘公开校园招聘 jobSource=2 无部门/地区/标签筛选全目录；列表包含完整岗位正文"
    )
    ready_endpoints = (API,)

    def parse_detail(self, value: str) -> tuple[str, str]:
        return split_detail(value)

    def validate_company(self, company_data: dict[str, Any]) -> None:
        pass

    def unit_name(self, company_data: dict[str, Any]) -> str:
        return text(company_data.get("campusOrgName"))

    def work_type(self, job_data: dict[str, Any]) -> str:
        return "校招"

    async def harvest(self) -> None:
        observed = await self.session.observed(API)
        check(observed["url"] == API, "智联岗位接口地址改变")
        payload = json.loads(observed["post_data"])
        check(isinstance(payload, dict) and set(payload) <= ALLOWED, "智联岗位查询出现未知参数")
        numbers = payload["orgNumbers"]
        request_org_number = self.request_org_number or self.org_number
        check(
            [str(number) for number in numbers] == [request_org_number]
            if isinstance(numbers, list)
            else str(numbers) == request_org_number,
            "智联岗位查询与租户组织号不符",
        )
        check(payload.get("jobSource") == self.job_source, "智联目录来源码与租户契约不符")
        check(
            text(payload.get("customTags"))
            == (self.observed_custom_tag or self.required_custom_tag),
            "智联目录校招标签与租户契约不符",
        )
        check(payload.get("pageIndex") == 1, "智联目录不是第一页")
        for key in FILTERS:
            payload[key] = (
                self.required_custom_tag
                if key == "customTags"
                else []
                if key == "orgDepartmentIds"
                else ""
            )
        await self.collect_catalog(payload)

    async def collect_catalog(self, payload: dict[str, Any]) -> None:
        size = self.page_size
        payload["pageSize"] = size
        scope = Scope(name=f"campus-job-source-{self.job_source}")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            result = await self.session.request(API, payload={**payload, "pageIndex": page})
            check(result.get("code") == 200, "智联岗位接口业务失败")
            data = result["data"]
            info = data["pageInfo"]
            expected = int(info["totalNum"])
            pages = int(info["totalPage"])
            check(expected >= 0, "智联岗位总数无效")
            check(int(info["pageIndex"]) == page, "智联返回了错误页码")
            check(int(info["pageSize"]) == size, "智联返回了错误分页大小")
            check(pages == (expected + size - 1) // size, "智联总页数与岗位数不符")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "智联翻页期间岗位总数变化")
            rows = self.add_page(
                scope, data["jobList"], seen, lambda row: str(row["job"]["jobNumber"])
            )
            evidence = self.session.last_evidence
            for row in rows:
                job_data: dict[str, Any] = row["job"]
                company_data: dict[str, Any] = row["company"]
                check(str(company_data["companyId"]) == self.org_number, "岗位混入其他组织")
                self.validate_company(company_data)
                check(
                    job_data.get("positionSourceType") == self.job_source,
                    "岗位来源码与租户契约不符",
                )
                if self.required_custom_tag:
                    check(
                        self.required_custom_tag in job_data.get("jobCategories", []),
                        "岗位缺少校招标签",
                    )
                key = str(job_data["jobNumber"])
                detail = text(job_data.get("detail"))
                check(bool(text(job_data.get("title"))) and bool(detail), "岗位标题或正文缺失")
                duties, requirements = self.parse_detail(detail)
                job = self.job(
                    key,
                    title=text(job_data["title"]),
                    source_url=str(job_data.get("url") or job_data.get("deliveryPath") or ""),
                    apply_url=str(job_data.get("deliveryPath") or ""),
                    unit=self.unit_name(company_data),
                    location=text(job_data.get("address") or job_data.get("cityName")),
                    education=text(job_data.get("minEducationName")),
                    category_raw=text(job_data.get("jobTypeName")),
                    duties=duties,
                    requirements=requirements,
                    work_type=self.work_type(job_data),
                    field_sources={
                        "duties": (
                            "search-job-list.data.jobList[].job.detail"
                            if duties
                            else "source_missing:无独立岗位职责"
                        ),
                        "requirements": (
                            "search-job-list.data.jobList[].job.detail:任职要求等标题"
                            if requirements
                            else "source_missing:独立任职要求"
                        ),
                        "published": "source_missing:modifiedTime 是更新时间，非发布时间",
                        "deadline": "source_missing",
                    },
                )
                job.evidence = [evidence]
                resolved = self.before_detail(f"job:{key}", row, scope, job, evidence=evidence)
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            if page >= pages:
                check(scope.unique == expected, "智联岗位唯一数与总数不符")
                scope.terminal = True
                break
            check(bool(rows), "智联分页提前为空")
            page += 1


class Unicom(Zhaopin):
    name = "zhaopin-unicom"
    host = "zglt.zhaopin.com"
    path = "/scjobs/index.html"
    org_number = "105347"


class Longfor2027(Zhaopin):
    name = "zhaopin-longfor-2027"
    host = "longfor.zhaopin.com"
    path = "/sgs/index.html#jobs"
    org_number = "105173"
    scope_description = "龙湖集团2027届仕官生、绽放、点将三个项目的无筛选联合校招目录"

    def validate_company(self, company_data: dict[str, Any]) -> None:
        check(
            text(company_data.get("slaveDisplayOrgName")) == "龙湖集团"
            and text(company_data.get("campusOrgName")) in {"仕官生", "绽放", "点将"},
            "龙湖岗位集团归属或招聘项目变化",
        )

    def unit_name(self, company_data: dict[str, Any]) -> str:
        names = [text(company_data.get("campusOrgName"))]
        for key in ("campusParentDepartment", "campusDepartment"):
            node = company_data.get(key)
            if isinstance(node, dict):
                name = text(node.get("name"))
                if name and name not in names:
                    names.append(name)
        return " / ".join(names)


class Cnooc2027(Zhaopin):
    name = "zhaopin-cnooc-2027"
    host = "cnooc.zhaopin.com"
    path = "/job/index.html"
    org_number = "105147"
    page_size = 100
    scope_description = (
        "中国海油2027集团校招 16 个招聘单位；清除页面默认首单位筛选后遍历根组织全目录"
    )

    async def harvest(self) -> None:
        observed = await self.session.observed("/get-search-aggregation")
        payload = json.loads(observed["post_data"])
        check(
            str(payload.get("orgNumber")) == self.org_number
            and payload.get("jobSource") == 2
            and payload.get("facetFields") == ["SOU_COMPANY_ID"],
            "中国海油聚合目录组织或校招来源改变",
        )
        result = json.loads(observed["body"])
        check(result.get("code") == 200, "中国海油单位聚合接口失败")
        units = result["data"]["itemMap"]["SOU_COMPANY_ID"]
        check(isinstance(units, list) and len(units) >= 16, "中国海油招聘单位树缺失")
        self._units: dict[str, str] = {}
        self._aggregate_total = 0
        for unit in units:
            company_number = str(unit["name"])
            company_name = text(unit["extend"]["campusOrgName"])
            company_info = json.loads(unit["extend"]["companyInfo"])
            check(
                company_number not in self._units
                and bool(company_name)
                and company_info.get("campusOrgName") == company_name
                and str(company_info.get("rootOrgId")) == self.org_number,
                "中国海油招聘单位身份改变",
            )
            self._units[company_number] = company_name
            self._aggregate_total += int(unit["count"])
        await super().harvest()
        check(
            self.result.scopes[0].expected == self._aggregate_total,
            "中国海油根目录总数与招聘单位聚合不一致",
        )

    def validate_company(self, company_data: dict[str, Any]) -> None:
        check(
            text(company_data.get("slaveDisplayOrgName")) == "中国海油"
            and self._units.get(str(company_data.get("companyNumber")))
            == text(company_data.get("campusOrgName")),
            "中国海油岗位招聘单位不在聚合目录内",
        )


class Fosun2027(Zhaopin):
    name = "zhaopin-fosun-2027"
    host = "fosun.zhaopin.com"
    path = "/job/index.html"
    org_number = "102124"
    observed_custom_tag = "复星财富"
    page_size = 50
    scope_description = "复星2027集团校招 10 单位 191 岗全目录；清除默认子项目标签，实习明确排除"

    async def harvest(self) -> None:
        response = await self.session.request(
            "https://fe.zhaopin.com/grace/api/dsc/get-search-aggregation",
            payload={
                "orgNumber": self.org_number,
                "jobSource": 2,
                "facetFields": ["SOU_COMPANY_ID"],
                "orgName": "",
                "sortType": 1,
                "pageIndex": 1,
                "pageSize": 21,
            },
        )
        check(response.get("code") == 200, "复星单位聚合接口失败")
        units = response["data"]["itemMap"]["SOU_COMPANY_ID"]
        check(isinstance(units, list) and len(units) == 10, "复星招聘单位数量变化")
        self._units: dict[str, str] = {}
        self._aggregate_total = 0
        for unit in units:
            number = str(unit["name"])
            name = text(unit["extend"]["campusOrgName"])
            info = json.loads(unit["extend"]["companyInfo"])
            check(
                number not in self._units
                and bool(name)
                and text(info.get("campusOrgName")) == name
                and str(info.get("rootOrgId")) == self.org_number,
                "复星招聘单位身份变化",
            )
            self._units[number] = name
            self._aggregate_total += int(unit["count"])
        aggregation_evidence = self.session.last_evidence
        await super().harvest()
        scope = self.result.scopes[0]
        scope.evidence.append(aggregation_evidence)
        check(scope.expected == self._aggregate_total, "复星单位聚合与完整岗位目录计数不符")

    def validate_company(self, company_data: dict[str, Any]) -> None:
        check(
            text(company_data.get("slaveDisplayOrgName")) == "上海复星高科技（集团）有限公司"
            and self._units.get(str(company_data.get("companyNumber")))
            == text(company_data.get("campusOrgName")),
            "复星岗位单位不在集团聚合目录",
        )

    def work_type(self, job_data: dict[str, Any]) -> str:
        tags = job_data.get("jobCategories") or []
        check(isinstance(tags, list), "复星岗位标签结构变化")
        return (
            "实习"
            if "实习" in text(job_data.get("title")) or any("实习" in text(tag) for tag in tags)
            else "校招"
        )


class TuopuCampus(Zhaopin):
    name = "zhaopin-tuopu-campus"
    host = "tuopu.zhaopin.com"
    path = "/school/index.html"
    org_number = "45914881"
    request_org_number = "CZ459148810"
    job_source = 1
    required_custom_tag = "校招"
    scope_description = "拓普集团官方校招页 jobSource=1 且 customTags=校招的无地区筛选完整目录"

    def validate_company(self, company_data: dict[str, Any]) -> None:
        check(text(company_data.get("slaveDisplayOrgName")) == "拓普集团", "拓普组织归属变化")


class Sipg(Zhaopin):
    name = "zhaopin-sipg"
    host = "sipg.zhaopin.com"
    path = "/post/index.html"
    org_number = "103473"


class Cqbank(Zhaopin):
    name = "zhaopin-cqbank"
    host = "cqcbank2027.zhaopin.com"
    path = "/post/index.html"
    org_number = "107394"


class Lbjt(Zhaopin):
    name = "zhaopin-lbjt"
    host = "lbjtxyzp.zhaopin.com"
    path = "/company/index.html"
    org_number = "107163"


class Zndl(Zhaopin):
    name = "zhaopin-zndl"
    host = "zndl2027.zhaopin.com"
    path = "/post/index.html"
    org_number = "106942"


class ShenzhenEnergy(Zhaopin):
    name = "zhaopin-szny2027"
    host = "szny2027.zhaopin.com"
    path = "/jobs/index.html"
    org_number = "107415"


class Hadian(Zhaopin):
    name = "zhaopin-hadian"
    host = "hadian.zhaopin.com"
    path = "/jobslist/index.html?id=10132887"
    org_number = "105816"


class ChinaPost2027(Zhaopin):
    name = "zhaopin-chinapost-2027"
    host = "chinapost2027.zhaopin.com"
    path = "/job/index.html?comid=1013109"
    org_number = "105582"
    page_size = 100
    ready_endpoints = (TREE_API,)
    scope_description = (
        "中国邮政2027联合校招组织树中集团总部及30个省级分公司及下辖分支；排除独立子公司"
    )
    root_names: frozenset[str] = frozenset()

    def parse_detail(self, value: str) -> tuple[str, str]:
        return "", text(value)

    def validate_company(self, company_data: dict[str, Any]) -> None:
        check(
            company_data.get("slaveDisplayOrgName") == "中国邮政集团有限公司"
            and company_data.get("campusOrgName") in self.root_names,
            "中国邮政岗位所属主体或省级根机构越界",
        )
        department = company_data.get("campusDepartment")
        check(
            isinstance(department, dict) and bool(text(department.get("name"))),
            "中国邮政岗位缺少下辖招聘机构",
        )

    def unit_name(self, company_data: dict[str, Any]) -> str:
        return text(company_data["campusDepartment"]["name"])

    async def harvest(self) -> None:
        observed = await self.session.observed(TREE_API)
        tree_evidence = self.session.last_evidence
        check(observed["url"] == TREE_API, "中国邮政组织树接口变化")
        query = json.loads(observed["post_data"])
        check(
            query == {"rootCompanyId": self.org_number, "format": "tree"},
            "中国邮政组织树根 ID 或格式变化",
        )
        tree = json.loads(observed["body"])
        check(tree.get("code") == 200, "中国邮政组织树业务失败")
        items = tree["data"]["list"]
        check(isinstance(items, list) and bool(items), "中国邮政组织树为空")
        roots = [
            row
            for row in items
            if row.get("parentId") == int(self.org_number)
            and (
                row.get("companyName") == "中国邮政集团有限公司总部"
                or str(row.get("companyName", "")).endswith("分公司")
            )
        ]
        check(
            len(roots) == 31
            and sum(row.get("companyName") == "中国邮政集团有限公司总部" for row in roots) == 1,
            "中国邮政总部及30个省级分公司根节点不完整",
        )
        root_ids = [int(row["id"]) for row in roots]
        check(len(set(root_ids)) == len(root_ids), "中国邮政组织根 ID 重复")
        self.root_names = frozenset(str(row["companyName"]) for row in roots)
        await self.collect_catalog(
            {
                "orgNumbers": self.org_number,
                "jobSource": 2,
                "pageIndex": 1,
                "pageSize": self.page_size,
                "campusParentDepartmentIds": root_ids,
            }
        )
        self.result.scopes[0].evidence.append(tree_evidence)


TENANTS = (
    Longfor2027,
    Fosun2027,
    ChinaPost2027,
    Hadian,
    Unicom,
    Sipg,
    Cqbank,
    Lbjt,
    Zndl,
    ShenzhenEnergy,
    TuopuCampus,
)
