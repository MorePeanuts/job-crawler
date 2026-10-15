"""SDIC Power's public Guopin group campus catalog."""

import json
from typing import Any, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.moka import sections
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class SdicPowerCampus(Adapter):
    name = "sdicpower-campus"
    host = "sdicpower.iguopin.com"
    path = "/job-campus"
    ready_endpoints = ("https://gp-api.iguopin.com/api/jobs/v1/list",)
    scope_description = "国投电力国聘官网校招及成员企业公开目录；机构树与列表总数闭合"

    async def harvest(self) -> None:
        info = json.loads((await self.session.observed("/api/activity/exclusive/v1/info"))["body"])
        check(info.get("code") == 200, "国投电力项目身份接口失败")
        company = info["data"]["company"]
        company_id = str(company["id"])
        check(
            info["data"]["key"] == "sdicpower" and company["name"] == "国投电力控股股份有限公司",
            "国投电力门户主体不符",
        )
        tree = json.loads(
            (await self.session.observed("/api/company/organization/v1/tree"))["body"]
        )
        check(tree.get("code") == 200, "国投电力机构树失败")
        root = tree["data"]["organization_tree"]
        check(str(root["company_id"]) == company_id, "国投电力机构树根不符")

        def units(node: dict[str, Any]) -> dict[str, str]:
            result = {str(node["company_id"]): text(node["name"])}
            for child in node.get("children", []):
                result.update(units(child))
            return result

        unit_names = units(root)
        observed = await self.session.observed("/api/jobs/v1/list")
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {
                "page": 1,
                "page_size": 20,
                "source": "s_job_list",
                "nature": ["115xW5oQ", "11bTac9", "114Fay7E"],
                "company_id_with_sub": company_id,
                "sort_scene": 2,
            },
            "国投电力公开目录含未知筛选或主体改变",
        )
        scope = Scope(name="sdicpower-group-campus")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        session = cast(BrowserSession, self.session)
        while True:
            response = await session.request(
                observed["url"], payload={**payload, "page": page}, credentials="omit"
            )
            check(response.get("code") == 200, "国投电力列表业务失败")
            data = response["data"]
            expected = int(data["total"])
            check(expected == int(root["all_job_count"]), "国投电力成员树与目录总数不符")
            check(data["page"] == page and data["page_size"] == 20, "国投电力页码不符")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "国投电力翻页期间总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["job_id"]))
            check(len(rows) <= 20, "国投电力分页大小异常")
            evidence = session.last_evidence
            for row in rows:
                unit_id = str(row["company_id"])
                check(
                    unit_id in unit_names and text(row["company_name"]) == unit_names[unit_id],
                    "国投电力岗位招聘单位不在机构树内",
                )
                check(
                    row.get("recruitment_type_cn") == "校园招聘"
                    and row.get("nature_cn") == "校招"
                    and row.get("status") == 1,
                    "国投电力目录混入非正式校招或关闭岗位",
                )
                check(
                    bool(text(row.get("job_name"))) and bool(row.get("contents")),
                    "国投电力岗位正文缺失",
                )
                duties, requirements = sections(text(row["contents"]))
                locations = row.get("district_list") or []
                key = str(row["job_id"])
                job = self.job(
                    key,
                    title=text(row["job_name"]),
                    source_url=f"https://{self.host}{self.path}",
                    work_type="校招",
                    unit=" / ".join(
                        part
                        for part in (unit_names[unit_id], text(row.get("department_cn")))
                        if part
                    ),
                    category_raw=text(row.get("category_cn")),
                    education=text(row.get("education_cn")),
                    location="、".join(text(part.get("area_cn")) for part in locations),
                    address="、".join(
                        text(part.get("address")) for part in locations if part.get("address")
                    ),
                    duties=duties,
                    requirements=requirements,
                    deadline=text(row.get("end_time")),
                    field_sources={
                        "unit": "jobs/v1/list.company_name/department_cn + organization/v1/tree",
                        "duties": "jobs/v1/list.contents:职责章节",
                        "requirements": "jobs/v1/list.contents:任职章节",
                        "deadline": "jobs/v1/list.end_time",
                        "published": "source_missing；start_time为招聘起始，非岗位发布时间",
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
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "国投电力分页提前为空")
            page += 1
