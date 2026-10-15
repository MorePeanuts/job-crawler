"""SPIC's official 2027 Guopin project, including known units outside its display tree."""

import json
from typing import Any, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.moka import sections
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

PROJECT = "212108939976772673"
OUTSIDE_TREE = {
    "青铜峡铝业发电有限责任公司",
    "国电投宁夏能源铝业青鑫炭素有限公司",
    "青铜峡铝业股份有限公司宁东铝业分公司",
}


class Spic2027(Adapter):
    name = "iguopin-spic-2027"
    host = "spic2027.iguopin.com"
    path = "/job"
    ready_endpoints = ("https://gp-api.iguopin.com/api/jobs/v1/project-job",)
    scope_description = "国家电投集团 2027 国聘官方项目全目录，机构树内和已核验树外单位全部纳入"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        info = json.loads((await self.session.observed("/api/activity/exclusive/v1/info"))["body"])
        check(info.get("code") == 200, "国家电投专站身份接口失败")
        campaign = info["data"]
        root_id = str(campaign["company_id"])
        check(
            campaign.get("key") == "spic2027"
            and campaign["company"]["name"] == "国家电力投资集团有限公司"
            and str(campaign["company"]["id"]) == root_id,
            "国家电投专站主体改变",
        )
        config = json.loads(campaign["content"])
        nav = config["params"]["nav"]
        check(
            any(
                item.get("route") == "/job"
                and item.get("title") == "校园招聘"
                and str(item.get("props", {}).get("projectId")) == PROJECT
                for item in nav
            )
            and any(
                item.get("route") == "/job1"
                and item.get("title") == "培优计划"
                and str(item.get("props", {}).get("projectId")) == PROJECT
                for item in nav
            ),
            "国家电投校招项目或导航改变",
        )
        tree_observed = await self.session.observed("/api/company/index/v1/project-company")
        tree_payload = json.loads(tree_observed["post_data"])
        check(
            tree_payload == {"project_ids": [PROJECT], "show_all_company": 0},
            "国家电投机构树项目筛选改变",
        )
        tree = json.loads(tree_observed["body"])
        check(tree.get("code") == 200, "国家电投机构树业务失败")
        root = tree["data"]["list"]
        check(
            str(root["company_id"]) == root_id and text(root["name"]) == "国家电力投资集团有限公司",
            "国家电投机构树根改变",
        )
        names: dict[str, tuple[str, str, str]] = {}

        def add_units(node: dict[str, Any]) -> None:
            unit_id = str(node["company_id"])
            unit_name = text(node["name"])
            check(unit_id not in names and bool(unit_name), "国家电投机构树单位缺失或重复")
            names[unit_id] = (
                unit_name,
                text(node.get("show_name")),
                text(node.get("short_name")),
            )
            children = node.get("children") or []
            check(isinstance(children, list), "国家电投机构树子节点变化")
            for child in children:
                check(isinstance(child, dict), "国家电投机构树子节点变化")
                add_units(child)

        add_units(root)
        observed = await self.session.observed("/api/jobs/v1/project-job")
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {"page": 1, "page_size": 20, "source": "s_job_list", "project_id": [PROJECT]},
            "国家电投校招目录含未知筛选或项目改变",
        )
        scope = Scope(name="spic-2027-project-all")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        inside = 0
        outside = 0
        page = 1
        while True:
            response = await session.request(
                observed["url"], payload={**payload, "page": page}, credentials="omit"
            )
            check(response.get("code") == 200, "国家电投校招列表业务失败")
            data = response["data"]
            expected = int(data["total"])
            check(
                expected >= 0 and data["page"] == page and data["page_size"] == 20,
                "国家电投校招分页元数据异常",
            )
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "国家电投校招翻页期间总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda item: str(item["job_id"]))
            check(len(rows) <= 20, "国家电投校招单页超出上限")
            evidence = session.last_evidence
            for row in rows:
                unit_id = str(row["company_id"])
                unit_name = text(row.get("company_name"))
                info_name = text((row.get("company_info") or {}).get("name"))
                check(bool(unit_name) and bool(info_name), "国家电投岗位单位身份缺失")
                if unit_id in names:
                    check(
                        info_name == names[unit_id][0] and unit_name in names[unit_id],
                        "国家电投岗位机构树单位不一致",
                    )
                    inside += 1
                else:
                    check(
                        unit_name == info_name and unit_name in OUTSIDE_TREE,
                        "国家电投项目出现未核验的树外单位",
                    )
                    outside += 1
                check(
                    row.get("recruitment_type_cn") == "校园招聘"
                    and row.get("nature_cn") == "校招"
                    and row.get("status") == 1,
                    "国家电投项目混入非公开校招岗位",
                )
                body = text(row.get("contents"))
                check(bool(text(row.get("job_name"))) and bool(body), "国家电投岗位标题或正文缺失")
                duties, requirements = sections(body)
                places = row.get("district_list") or []
                check(isinstance(places, list), "国家电投岗位地点结构变化")
                key = str(row["job_id"])
                job = self.job(
                    key,
                    title=text(row["job_name"]),
                    source_url=f"https://{self.host}{self.path}",
                    work_type="校招",
                    unit=" / ".join(
                        part for part in (info_name, text(row.get("department_cn"))) if part
                    ),
                    category_raw=text(row.get("category_cn")),
                    education=text(row.get("education_cn")),
                    location="、".join(text(part.get("area_cn")) for part in places),
                    duties=duties,
                    requirements=requirements,
                    deadline=text(row.get("end_time")),
                    field_sources={
                        "unit": "project-job.company_name/company_info.name/department_cn",
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
                check(
                    inside == int(root["all_job_count"]) and inside + outside == expected,
                    "国家电投机构树与全项目岗位数量不平衡",
                )
                scope.terminal = True
                break
            check(bool(rows), "国家电投项目分页提前为空")
            page += 1
