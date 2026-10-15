"""SAIC Motor's public group college recruiting catalog."""

import json
import math
from typing import Any

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError


class SaicCampus(Adapter):
    name = "saic-group-campus"
    host = "saic-recruit.saicmotor.com"
    path = "/recruit/pc/#/collegeRecruit"
    ready_endpoints = ("/recruit/api/recruit/position/deliver/list",)
    scope_description = "上汽集团官方校招目录，35 家公开招聘公司全部覆盖；实习计划明确排除"

    async def harvest(self) -> None:
        company_observed = await self.session.observed("/position/publishPosition/companyList")
        companies_response = json.loads(company_observed["body"])
        check(companies_response.get("code") == 200, "上汽招聘公司目录业务失败")
        companies = {str(row["id"]): text(row["companyName"]) for row in companies_response["data"]}
        check(len(companies) == 35, "上汽招聘公司目录结构改变")
        observed = await self.session.observed("/position/deliver/list")
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {
                "posCity": [],
                "posType": [1, 2],
                "posTypeIds": [],
                "companyId": [],
                "size": 15,
                "page": 1,
            },
            "上汽校招目录带有筛选或入口变化",
        )
        scope = Scope(name="college-all-companies")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                observed["url"], payload={**payload, "page": page}
            )
            check(response.get("code") == 200, "上汽校招目录业务失败")
            data = response["data"]
            expected = int(data["total"])
            pages = int(data["pages"])
            check(
                expected > 0
                and pages == math.ceil(expected / 15)
                and int(data["current"]) == page
                and int(data["size"]) == 15,
                "上汽校招目录分页异常",
            )
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "上汽校招目录总数变化")
            rows = self.add_page(scope, data["records"], seen, lambda row: str(row["posId"]))
            listing_evidence = self.session.last_evidence
            for row in rows:
                job_id = str(row["posId"])
                try:
                    unit_id = str(row["posCompanyId"])
                    unit = text(row["posCompanyName"])
                    check(companies.get(unit_id) == unit, "上汽职位招聘公司不在官方公司目录")
                    check(str(row.get("state")).lower() == "true", "上汽列表出现未开放职位")
                    nature = text(row.get("posType"))
                    check(nature in {"校园招聘", "实习计划"}, "上汽职位性质异常")
                    if nature == "实习计划":
                        scope.skipped_out_of_scope += 1
                        continue
                    listing = self.job(
                        job_id,
                        title=text(row.get("posName")),
                        unit=unit,
                        location=text(row.get("posCity")),
                        source_url=self.source.url,
                    )
                    listing.evidence = [listing_evidence]
                    resolved = self.before_detail(
                        f"job:{job_id}", row, scope, listing, evidence=listing_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    detail_response = await self.session.request(
                        f"https://{self.host}/recruit/api/recruit/position/get/?id={job_id}",
                        detail=True,
                    )
                    check(detail_response.get("code") == 200, "上汽岗位详情业务失败")
                    detail: dict[str, Any] = detail_response["data"]
                    check(str(detail.get("id")) == job_id, "上汽详情与列表 ID 不一致")
                    check(
                        text(detail.get("posName")) == text(row.get("posName"))
                        and str(detail.get("posCompanyId")) == unit_id
                        and text(detail.get("posCompanyName")) == unit,
                        "上汽详情标题或招聘公司与列表不一致",
                    )
                    check(str(detail.get("posType")) == "1", "上汽详情混入实习或社招")
                    check(
                        bool(text(detail.get("posDesc"))) and bool(text(detail.get("posRequire"))),
                        "上汽详情缺少职责或任职要求",
                    )
                    job = self.job(
                        job_id,
                        title=text(detail["posName"]),
                        unit=unit,
                        location=text(row.get("posCity")),
                        category_raw=text(detail.get("posMajorTypeName")),
                        duties=text(detail["posDesc"]),
                        requirements=text(detail["posRequire"]),
                        source_url=self.source.url,
                        field_sources={
                            "unit": "publishPosition/companyList + deliver/list.records[].posCompanyId",
                            "location": "deliver/list.records[].posCity",
                            "duties": "position/get.data.posDesc",
                            "requirements": "position/get.data.posRequire",
                            "published": "source_missing; posCreatorDate 是后台创建时间",
                        },
                    )
                    job.evidence = [listing_evidence, self.session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{job_id}", row, [job])
                except Exception as exc:
                    self.error(exc, job_id)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if page == pages:
                check(scope.unique == expected, "上汽末页岗位数与总数不符")
                scope.terminal = True
                break
            check(bool(rows) and scope.unique < expected, "上汽校招分页提前为空")
            page += 1
