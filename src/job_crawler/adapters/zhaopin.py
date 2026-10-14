"""Verified Zhaopin campus campaigns with a shared public JSON catalog."""

import json
from typing import Any

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope

API = "https://fe.zhaopin.com/grace/api/dsc/search-job-list"
FILTERS = {
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
}
ALLOWED = FILTERS | {"orgNumbers", "jobSource", "pageIndex", "pageSize"}


def split_detail(value: str) -> tuple[str, str]:
    return split_sections(value)


class Zhaopin(Adapter):
    org_number = ""
    scope_description = (
        "智联招聘公开校园招聘 jobSource=2 无部门/地区/标签筛选全目录；列表包含完整岗位正文"
    )
    ready_endpoints = (API,)

    async def harvest(self) -> None:
        observed = await self.session.observed(API)
        check(observed["url"] == API, "智联岗位接口地址改变")
        payload = json.loads(observed["post_data"])
        check(isinstance(payload, dict) and set(payload) <= ALLOWED, "智联岗位查询出现未知参数")
        numbers = payload["orgNumbers"]
        check(
            [str(number) for number in numbers] == [self.org_number]
            if isinstance(numbers, list)
            else str(numbers) == self.org_number,
            "智联岗位查询与租户组织号不符",
        )
        check(payload.get("jobSource") == 2, "智联目录不是校招 jobSource=2")
        check(payload.get("pageIndex") == 1, "智联目录不是第一页")
        for key in FILTERS:
            payload[key] = [] if key == "orgDepartmentIds" else ""
        size = 50
        payload["pageSize"] = size
        scope = Scope(name="campus-job-source-2")
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
                check(job_data.get("positionSourceType") == 2, "岗位混入非校招来源")
                key = str(job_data["jobNumber"])
                detail = text(job_data.get("detail"))
                check(bool(text(job_data.get("title"))) and bool(detail), "岗位标题或正文缺失")
                duties, requirements = split_detail(detail)
                job = self.job(
                    key,
                    title=text(job_data["title"]),
                    source_url=str(job_data.get("url") or job_data.get("deliveryPath") or ""),
                    apply_url=str(job_data.get("deliveryPath") or ""),
                    unit=text(company_data.get("campusOrgName")),
                    location=text(job_data.get("address") or job_data.get("cityName")),
                    education=text(job_data.get("minEducationName")),
                    category_raw=text(job_data.get("jobTypeName")),
                    duties=duties,
                    requirements=requirements,
                    field_sources={
                        "duties": "search-job-list.data.jobList[].job.detail",
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


TENANTS = (Hadian, Unicom, Sipg, Cqbank, Lbjt, Zndl, ShenzhenEnergy)
