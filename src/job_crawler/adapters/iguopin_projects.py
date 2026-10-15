"""Validated Guopin 2027 project tenants with complete group trees and job catalogs."""

import json
from typing import Any, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.moka import sections
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class GuopinProjectCampus(Adapter):
    path = "/job"
    ready_endpoints = ("https://gp-api.iguopin.com/api/jobs/v1/project-job",)
    campaign_key = ""
    campaign_company = ""
    campaign_company_id = ""
    project_id = ""
    nav_title = ""
    nature_codes: tuple[str, ...] = ()

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        info = json.loads((await self.session.observed("/api/activity/exclusive/v1/info"))["body"])
        check(info.get("code") == 200, f"{self.name} 专站身份接口失败")
        campaign = info["data"]
        check(
            campaign.get("key") == self.campaign_key
            and str(campaign.get("company_id")) == self.campaign_company_id
            and str(campaign["company"]["id"]) == self.campaign_company_id
            and text(campaign["company"]["name"]) == self.campaign_company,
            f"{self.name} 专站主体改变",
        )
        nav = json.loads(campaign["content"])["params"]["nav"]
        check(
            any(
                item.get("route") == "/job"
                and item.get("title") == self.nav_title
                and str(item.get("props", {}).get("projectId")) == self.project_id
                for item in nav
            ),
            f"{self.name} 校招导航项目改变",
        )
        tree_observed = await self.session.observed("/api/company/index/v1/project-company")
        tree_payload: dict[str, object] = {
            "project_ids": [self.project_id],
            "show_all_company": 0,
        }
        if self.nature_codes:
            tree_payload["job_nature"] = list(self.nature_codes)
        check(
            json.loads(tree_observed["post_data"]) == tree_payload,
            f"{self.name} 机构树筛选改变",
        )
        tree = json.loads(tree_observed["body"])
        check(tree.get("code") == 200, f"{self.name} 机构树业务失败")
        root = tree["data"]["list"]
        check(
            str(root["company_id"]) == self.campaign_company_id
            and text(root["name"]) == self.campaign_company,
            f"{self.name} 机构树根改变",
        )
        names: dict[str, str] = {}

        def add_units(node: dict[str, Any]) -> None:
            unit_id = str(node["company_id"])
            unit_name = text(node["name"])
            check(unit_id not in names and bool(unit_name), f"{self.name} 机构树单位重复或缺失")
            names[unit_id] = unit_name
            children = node.get("children") or []
            check(isinstance(children, list), f"{self.name} 机构树子节点变化")
            for child in children:
                check(isinstance(child, dict), f"{self.name} 机构树子节点变化")
                add_units(child)

        add_units(root)
        observed = await self.session.observed("/api/jobs/v1/project-job")
        payload: dict[str, object] = {
            "page": 1,
            "page_size": 20,
            "source": "s_job_list",
            "project_id": [self.project_id],
        }
        if self.nature_codes:
            payload["nature"] = list(self.nature_codes)
            payload["company_id_with_sub"] = self.campaign_company_id
        check(json.loads(observed["post_data"]) == payload, f"{self.name} 目录含未知筛选")
        scope = Scope(name=f"{self.campaign_key}-2027-project-all")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await session.request(
                observed["url"], payload={**payload, "page": page}, credentials="omit"
            )
            check(response.get("code") == 200, f"{self.name} 列表业务失败")
            data = response["data"]
            expected = int(data["total"])
            check(
                expected == int(root["all_job_count"])
                and data["page"] == page
                and data["page_size"] == 20,
                f"{self.name} 分页或机构树计数不一致",
            )
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, f"{self.name} 翻页总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda item: str(item["job_id"]))
            check(len(rows) <= 20, f"{self.name} 单页超出上限")
            evidence = session.last_evidence
            for row in rows:
                unit_id = str(row["company_id"])
                unit_name = text(row.get("company_name"))
                check(
                    unit_id in names
                    and unit_name == names[unit_id]
                    and unit_name == text((row.get("company_info") or {}).get("name")),
                    f"{self.name} 岗位单位身份不一致",
                )
                check(
                    row.get("recruitment_type_cn") == "校园招聘"
                    and row.get("nature_cn") == "校招"
                    and row.get("status") == 1,
                    f"{self.name} 混入非公开正式校招",
                )
                body = text(row.get("contents"))
                check(bool(text(row.get("job_name"))) and bool(body), f"{self.name} 标题或正文缺失")
                duties, requirements = sections(body)
                places = row.get("district_list") or []
                check(isinstance(places, list), f"{self.name} 地点结构变化")
                key = str(row["job_id"])
                job = self.job(
                    key,
                    title=text(row["job_name"]),
                    source_url=f"https://{self.host}{self.path}",
                    work_type="校招",
                    unit=" / ".join(
                        part for part in (unit_name, text(row.get("department_cn"))) if part
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
                        "published": "source_missing；start_time 为招聘起始，非岗位发布时间",
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
            check(bool(rows), f"{self.name} 分页提前为空")
            page += 1


class Ceec2027(GuopinProjectCampus):
    name = "iguopin-ceec-2027"
    host = "ceec.iguopin.com"
    campaign_key = "ceec"
    campaign_company = "中国能源建设股份有限公司"
    campaign_company_id = "10698197366712845"
    project_id = "215123984184772101"
    nav_title = "校招职位"
    scope_description = "中国能建集团国聘 2027 校招门户，股份公司及下属全部招聘单位"


class Cosco2027(GuopinProjectCampus):
    name = "iguopin-cosco-2027"
    host = "coscoshipping.iguopin.com"
    campaign_key = "coscoshipping"
    campaign_company = "中国远洋海运集团有限公司"
    campaign_company_id = "10685294861878308"
    project_id = "216313247962236623"
    nav_title = "校园招聘"
    nature_codes = ("115xW5oQ", "11bTac9", "114Fay7E")
    scope_description = "中远海运集团国聘 2027 校招项目，全集团公开机构树与岗位目录"
