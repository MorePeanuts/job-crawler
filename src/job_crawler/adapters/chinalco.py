"""Chinalco's public 2027 Guopin project and complete member-company catalog."""

import json
from typing import Any, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.moka import sections
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

PROJECT = "212368257720519917"
SECOND_PROJECT = "195434479274167937"


class Chinalco2027(Adapter):
    name = "iguopin-chinalco-2027"
    host = "chinalco2027.iguopin.com"
    path = "/job"
    ready_endpoints = ("https://gp-api.iguopin.com/api/jobs/v1/project-job",)
    scope_description = "中铝集团国聘 2027 校招项目全目录，集团机构树逐岗核对实际招聘单位"

    async def harvest(self) -> None:
        info = json.loads((await self.session.observed("/api/activity/exclusive/v1/info"))["body"])
        check(info.get("code") == 200, "中铝专站身份接口失败")
        campaign = info["data"]
        company_id = str(campaign["company_id"])
        check(
            campaign.get("key") == "chinalco2027"
            and campaign["company"]["name"] == "中国铝业集团有限公司"
            and str(campaign["company"]["id"]) == company_id,
            "中铝专站主体改变",
        )
        config = json.loads(campaign["content"])
        nav = config["params"]["nav"]
        check(
            any(
                row.get("route") == "/job"
                and row.get("title") == "校园招聘"
                and str(row.get("props", {}).get("projectId")) == PROJECT
                for row in nav
            ),
            "中铝校园招聘项目改变",
        )
        check(
            any(
                row.get("route") == "/job2"
                and str(row.get("props", {}).get("projectId")) == SECOND_PROJECT
                for row in nav
            ),
            "中铝第二批项目导航改变",
        )
        tree_observed = await self.session.observed("/api/company/index/v1/project-company")
        tree_payload = json.loads(tree_observed["post_data"])
        check(
            tree_payload == {"project_ids": [PROJECT], "show_all_company": 0},
            "中铝机构树项目筛选改变",
        )
        tree = json.loads(tree_observed["body"])
        check(tree.get("code") == 200, "中铝机构树业务失败")
        root = tree["data"]["list"]
        check(
            str(root["company_id"]) == company_id and text(root["name"]) == "中国铝业集团有限公司",
            "中铝机构树根改变",
        )

        names: dict[str, str] = {}

        def add_units(node: dict[str, Any]) -> None:
            unit_id = str(node["company_id"])
            unit_name = text(node["name"])
            check(unit_id not in names and bool(unit_name), "中铝机构树单位缺失或重复")
            names[unit_id] = unit_name
            children = node.get("children") or []
            check(isinstance(children, list), "中铝机构树子节点变化")
            for child in children:
                check(isinstance(child, dict), "中铝机构树子节点变化")
                add_units(child)

        add_units(root)
        observed = await self.session.observed("/api/jobs/v1/project-job")
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {
                "page": 1,
                "page_size": 20,
                "source": "s_job_list",
                "company_id_with_sub": company_id,
                "project_id": [PROJECT],
            },
            "中铝校招目录含未知筛选或项目改变",
        )
        scope = Scope(name="chinalco-2027-group-campus")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        session = cast(BrowserSession, self.session)
        while True:
            response = await session.request(
                observed["url"], payload={**payload, "page": page}, credentials="omit"
            )
            check(response.get("code") == 200, "中铝校招列表业务失败")
            data = response["data"]
            expected = int(data["total"])
            check(expected == int(root["all_job_count"]), "中铝机构树和目录总数不一致")
            check(data["page"] == page and data["page_size"] == 20, "中铝校招页码不符")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "中铝翻页期间总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["job_id"]))
            check(len(rows) <= 20, "中铝校招分页超限")
            evidence = session.last_evidence
            for row in rows:
                unit_id = str(row["company_id"])
                check(
                    unit_id in names and text(row["company_name"]) == names[unit_id],
                    "中铝岗位招聘单位不在机构树内",
                )
                check(
                    row.get("recruitment_type_cn") == "校园招聘"
                    and row.get("nature_cn") == "校招"
                    and row.get("status") == 1,
                    "中铝目录混入非正式校招或关闭岗位",
                )
                body = text(row.get("contents"))
                check(bool(text(row.get("job_name"))) and bool(body), "中铝岗位标题或正文缺失")
                duties, requirements = sections(body)
                places = row.get("district_list") or []
                check(isinstance(places, list), "中铝岗位地点结构变化")
                key = str(row["job_id"])
                job = self.job(
                    key,
                    title=text(row["job_name"]),
                    source_url=f"https://{self.host}{self.path}",
                    work_type="校招",
                    unit=" / ".join(
                        part for part in (names[unit_id], text(row.get("department_cn"))) if part
                    ),
                    category_raw=text(row.get("category_cn")),
                    education=text(row.get("education_cn")),
                    location="、".join(text(part.get("area_cn")) for part in places),
                    duties=duties,
                    requirements=requirements,
                    deadline=text(row.get("end_time")),
                    field_sources={
                        "unit": "project-company tree + project-job.company_name/department_cn",
                        "duties": "project-job.contents:职责章节",
                        "requirements": "project-job.contents:任职要求章节",
                        "deadline": "project-job.end_time",
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
            check(bool(rows), "中铝校招分页提前为空")
            page += 1
