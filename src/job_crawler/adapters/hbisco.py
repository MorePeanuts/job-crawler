"""HBIS group's public campus catalog across its member companies."""

import json
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class HbiscoCampus(Adapter):
    name = "hbisco-group-campus"
    host = "biz.hbisco.com"
    path = "/gf/hrpc/recruit/campus"
    api = "/stage-api/apply/recruitment/position"
    ready_endpoints = (f"{api}/filterOptions?", f"{api}/list?")
    scope_description = "河钢集团官网校园招聘 A 类无筛选全目录；保留成员单位原名"

    async def harvest(self) -> None:
        observed_list = await self.session.observed(f"{self.api}/list?")
        params = parse_qs(urlsplit(observed_list["url"]).query)
        check(
            params
            == {
                "hbisMediaOutlet": ["A"],
                "hbisRequirementType": ["A"],
                "pageNum": ["1"],
                "pageSize": ["10"],
            },
            "河钢校园目录首屏带有未知筛选",
        )
        observed_filters = await self.session.observed(f"{self.api}/filterOptions?")
        check(
            parse_qs(urlsplit(observed_filters["url"]).query)
            == {"hbisMediaOutlet": ["A"], "hbisRequirementType": ["A"]},
            "河钢校招筛选字典来源不符",
        )
        filters = json.loads(observed_filters["body"])
        check(
            filters.get("success") is True and filters.get("code") == "00000",
            "河钢校招单位字典业务失败",
        )
        company = filters["data"]["company"]
        check(isinstance(company, list) and len(company) >= 2, "河钢校招单位字典为空或结构变化")
        units = {text(row["name"]) for row in company}
        check(len(units) == len(company) and "河钢集团" in units, "河钢校招单位字典重复或缺少集团")
        scope = Scope(name="hbis-campus-all-units")
        scope.evidence.append(self.session.last_evidence)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                query(observed_list["url"], pageNum=page, pageSize=10)
            )
            check(
                response.get("success") is True and response.get("code") == "00000",
                "河钢校招目录业务失败",
            )
            data = response["data"]
            expected = int(data["totalCount"])
            check(
                expected > 0 and int(data["pageNo"]) == page and int(data["pageSize"]) == 10,
                "河钢校招目录总数或页码无效",
            )
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "河钢校招目录总数变化")
            rows = data["rows"]
            check(isinstance(rows, list), "河钢校招目录不是数组")
            check(len(rows) == min(10, max(0, expected - (page - 1) * 10)), "河钢校招分页缺行")
            check(bool(data["lastPage"]) == (page * 10 >= expected), "河钢校招末页标志与总数不一致")
            fresh = self.add_page(scope, rows, seen, lambda row: str(row["id"]))
            list_evidence = self.session.last_evidence
            for row in fresh:
                key = str(row["id"])
                try:
                    unit = text(row.get("hbisDemandOrgBelongcompanyName"))
                    check(unit in units, "河钢校招岗位单位不在官网单位字典")
                    check(bool(text(row.get("hbisPositiont"))), "河钢校招岗位标题缺失")
                    detail = await self.session.request(
                        f"https://{self.host}{self.api}/detail?id={key}", detail=True
                    )
                    check(
                        detail.get("success") is True and detail.get("code") == "00000",
                        "河钢校招岗位详情业务失败",
                    )
                    item = detail["data"]
                    check(
                        str(item["id"]) == key
                        and text(item.get("hbisPositiont")) == text(row["hbisPositiont"])
                        and text(item.get("hbisDemandOrgBelongcompanyName")) == unit,
                        "河钢校招岗位详情身份或单位不符",
                    )
                    check(
                        item.get("hbisRequirementType") == "A"
                        and "A" in text(item.get("hbisMediaOutlet")),
                        "河钢校招详情招聘渠道或类别改变",
                    )
                    duties = text(item.get("hbisJobDuties"))
                    requirements = text(item.get("hbisJobReqs"))
                    specialty = text(item.get("hbisProReqs"))
                    if specialty and specialty not in requirements:
                        requirements = (
                            requirements + "\n" if requirements else ""
                        ) + f"专业要求：{specialty}"
                    check(bool(duties) and bool(requirements), "河钢校招岗位职责或要求缺失")
                    job = self.job(
                        key,
                        title=text(item["hbisPositiont"]),
                        source_url=f"https://{self.host}{self.path}/detail/{key}",
                        apply_url=f"https://{self.host}{self.path}/detail/{key}",
                        unit=unit,
                        location=text(item.get("hbisWorkLocation")),
                        education=text(item.get("hbisEduBackgroundName")),
                        category_raw=text(item.get("hbisPositionCotegorysName")),
                        duties=duties,
                        requirements=requirements,
                        deadline=text(item.get("hbisDueDate")),
                        field_sources={
                            "published": "source_missing:createtime/生效日非发布时间",
                            "deadline": "position/detail.data.hbisDueDate",
                            "unit": "position/detail.data.hbisDemandOrgBelongcompanyName",
                            "duties": "position/detail.data.hbisJobDuties",
                            "requirements": "position/detail.data.hbisJobReqs/hbisProReqs",
                        },
                    )
                    job.evidence = [list_evidence, self.session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, key)
            if scope.unique >= expected:
                scope.terminal = True
                break
            page += 1
