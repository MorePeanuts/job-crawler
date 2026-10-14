"""Sinopharm's official Guopin project catalog with full inline job descriptions."""

import json
from typing import cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.moka import sections
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class SinopharmCampus(Adapter):
    name = "sinopharm-campus"
    host = "sinopharm2027.iguopin.com"
    path = "/job"
    endpoint = "/api/jobs/v1/project-job"
    ready_endpoints = (f"https://gp-api.iguopin.com{endpoint}",)
    project = "216321915759888083"
    scope_description = "国药2027官方校园项目全目录，涵盖目录全部招聘单位；完整内嵌正文"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {"page": 1, "page_size": 20, "source": "s_job_list", "project_id": [self.project]},
            "国药项目或筛选条件改变",
        )
        scope = Scope(name="sinopharm-2027-project")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await cast(BrowserSession, self.session).request(
                observed["url"], payload={**payload, "page": page}, credentials="omit"
            )
            check(response.get("code") == 200, "国药列表业务失败")
            data = response["data"]
            count = int(data["total"])
            check(data["page"] == page and data["page_size"] == 20, "国药页码不符")
            if scope.expected is None:
                scope.expected = count
            check(scope.expected == count, "国药列表总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda r: str(r["job_id"]))
            check(len(rows) == min(20, max(0, count - (page - 1) * 20)), "国药目录页不完整")
            for row in rows:
                check(bool(row["contents"]), "国药职位正文缺失")
                duties, requirements = sections(
                    text(row["contents"]).replace("任职条件", "任职要求")
                )
                locations = row.get("district_list") or []
                self.result.jobs.append(
                    self.job(
                        str(row["job_id"]),
                        title=text(row["job_name"]),
                        unit=text(row["company_name"]),
                        source_url=f"https://{self.host}{self.path}",
                        work_type="实习"
                        if "实习" in row["job_name"]
                        else "校招"
                        if row["recruitment_type_cn"] == "校园招聘" and row["nature_cn"] == "校招"
                        else row["recruitment_type_cn"],
                        education=text(row["education_cn"]),
                        location="、".join(text(p["area_cn"]) for p in locations),
                        address="、".join(
                            text(p.get("address")) for p in locations if p.get("address")
                        ),
                        duties=duties,
                        requirements=requirements,
                        deadline=text(row["end_time"]),
                        category_raw=text(row["category_cn"]),
                        field_sources={
                            "duties": "project-job.contents",
                            "requirements": "project-job.contents:明确章节",
                            "education": "education_cn",
                            "deadline": "end_time（投递截止）",
                            "published": "source_missing；start_time为招聘起始，不冒充发布日期",
                        },
                    )
                )
                scope.details += 1
            if scope.unique >= count:
                scope.terminal = True
                break
            page += 1
