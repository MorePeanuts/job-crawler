"""Lenovo public graduate positions with source-owned enum dictionaries."""

from typing import Any

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


def dictionaries(payload: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    check(payload.get("code") == 0, "联想字典接口失败")
    groups = {str(item.get("dictCode")): item for item in payload["result"]}
    result: list[dict[str, str]] = []
    for name in ("city_portal", "education"):
        check(name in groups, f"联想字典缺少 {name}")
        values = {
            str(item["dictValue"]): text(item["dictName"]) for item in groups[name]["children"]
        }
        check(bool(values), f"联想字典 {name} 为空")
        result.append(values)
    return result[0], result[1]


class Lenovo(Adapter):
    name = "lenovo-campus"
    host = "talent.lenovo.com.cn"
    path = "/position"
    ready_endpoints = ("/gateway/jobBase/list?pageNum=1",)
    scope_description = "联想应届生招聘 projectType=1 公开无筛选目录；列表有完整职责和任职要求"

    async def harvest(self) -> None:
        observed = await self.session.observed("/gateway/jobBase/list?pageNum=1")
        check(observed["url"].endswith("/gateway/jobBase/list?pageNum=1"), "联想目录不是第一页")
        cities, educations = dictionaries(
            await self.session.request(f"https://{self.host}/gateway/sysDict/all")
        )
        dict_evidence = self.session.last_evidence
        scope = Scope(name="graduate-project-type-1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            data = await self.session.request(query(observed["url"], pageNum=page))
            check(data.get("code") == 0, "联想岗位列表业务失败")
            result = data["result"]
            expected = int(result["total"])
            check(expected >= 0, "联想岗位总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "联想翻页期间总数变化")
            rows = self.add_page(scope, result["rows"], seen, lambda row: str(row["id"]))
            list_evidence = self.session.last_evidence
            for row in rows:
                project_type = row.get("projectType")
                check(project_type in {1, 2, 3}, "联想出现未知招聘项目类型")
                codes = [
                    part.strip()
                    for part in str(row.get("workPlace") or "").split(",")
                    if part.strip()
                ]
                check(all(code in cities for code in codes), "联想岗位地点代码不在公开字典中")
                education_code = str(row.get("educationRequired") or "")
                check(
                    not education_code or education_code in educations, "联想学历代码不在公开字典中"
                )
                duties = text(row.get("jobDuties"))
                requirements = text(row.get("jobRequirement"))
                check(bool(text(row.get("jobName"))) and bool(duties), "联想岗位标题或职责为空")
                key = str(row["id"])
                job = self.job(
                    key,
                    title=text(row["jobName"]),
                    source_url=f"https://{self.host}/position/detail?id={key}",
                    work_type="校招"
                    if project_type == 1
                    else "实习"
                    if project_type == 2
                    else "其他",
                    visible=row.get("publishFlag") == 1 and row.get("activateFlag") == 1,
                    unit=text(row.get("firstDeptId")),
                    category_raw=text(row.get("typeName")),
                    location="、".join(cities[code] for code in codes),
                    education=educations.get(education_code, ""),
                    duties=duties,
                    requirements=requirements,
                    field_sources={
                        "location": "jobBase.list[].workPlace + sysDict.city_portal",
                        "education": "jobBase.list[].educationRequired + sysDict.education",
                        "duties": "jobBase.list[].jobDuties",
                        "requirements": "jobBase.list[].jobRequirement",
                        "published": "source_missing",
                        "deadline": "source_missing",
                        "work_type": "jobBase.list[].projectType:1=应届生，2=实习，3=人才项目",
                    },
                )
                job.evidence = [list_evidence, dict_evidence]
                resolved = self.before_detail(f"job:{key}", row, scope, job, evidence=list_evidence)
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "联想岗位分页提前为空")
            page += 1
