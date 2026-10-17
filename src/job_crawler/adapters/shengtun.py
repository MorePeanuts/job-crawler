"""Shengtun Mining's verified branch of the group's campus campaign."""

from collections import Counter
from typing import Any

from job_crawler.adapters.base import text
from job_crawler.adapters.platforms import check
from job_crawler.adapters.zhaopin import Zhaopin

BRANCHES = {
    "KA0538004527D90000102000": ("盛屯矿业", 10133771),
    "KA0538004527D90000103000": ("盛新锂能", 10133774),
    "KA0538004527D90000104000": ("盛屯集团直属", 10133776),
}


class ShengtunMiningCampus(Zhaopin):
    name = "zhaopin-shengtun-mining-campus"
    host = "shengtun2027.zhaopin.com"
    path = "/index.html"
    org_number = "105807"
    scope_description = (
        "盛屯集团2027校招根目录全量核对，仅纳入盛屯矿业及下属单位；排除盛新锂能、集团直属"
    )

    async def harvest(self) -> None:
        observed = await self.session.observed("/get-search-aggregation")
        check(
            observed["url"] == "https://fe.zhaopin.com/grace/api/dsc/get-search-aggregation",
            "盛屯聚合接口变化",
        )
        response = await self.session.request(
            observed["url"],
            payload={
                "orgNumber": self.org_number,
                "jobSource": 2,
                "facetFields": ["SOU_XY_ORG_ID"],
                "orgDepartmentIds": "",
                "sortType": 1,
            },
        )
        check(response.get("code") == 200, "盛屯单位聚合业务失败")
        counts: Counter[str] = Counter()
        for unit in response["data"]["itemMap"]["SOU_XY_ORG_ID"]:
            number = str(unit["extend"]["number"])
            check(number in BRANCHES and number not in counts, "盛屯目录出现未知或重复板块")
            check(
                (text(unit["name"]), int(unit["code"])) == BRANCHES[number]
                and str(unit["extend"]["parentId"]) == self.org_number,
                "盛屯板块身份与父集团不符",
            )
            count = int(unit["count"])
            check(count >= 0, "盛屯板块岗位数无效")
            counts[number] = count
        check(set(counts) == set(BRANCHES), "盛屯目录缺少已验证的招聘板块")
        evidence = self.session.last_evidence
        self.distribution: Counter[str] = Counter()
        await super().harvest()
        scope = self.result.scopes[0]
        scope.evidence.append(evidence)
        for job in self.result.jobs:
            job.evidence.append(evidence)
            job.field_sources["unit"] = (
                "SOU_XY_ORG_ID 聚合 + company.campusDepartment，所属板块为盛屯矿业"
            )
        check(
            scope.expected == sum(counts.values()) and self.distribution == counts,
            "盛屯板块岗位数与完整目录不闭合",
        )

    def validate_company(self, company_data: dict[str, Any]) -> None:
        number = str(company_data["companyNumber"])
        check(number in BRANCHES, "盛屯岗位所属单位不在已验证板块")
        name, identity = BRANCHES[number]
        check(
            text(company_data["campusOrgName"]) == name
            and text(company_data["slaveDisplayOrgName"]) == "深圳盛屯集团有限公司",
            "盛屯岗位集团或板块名称错配",
        )
        department = company_data["campusDepartment"]
        check(
            int(department["parentId"]) == identity and bool(text(department["name"])),
            "盛屯岗位下属单位归属不符",
        )
        self.distribution[number] += 1

    def in_scope(self, company_data: dict[str, Any]) -> bool:
        return company_data["companyNumber"] == "KA0538004527D90000102000"

    def unit_name(self, company_data: dict[str, Any]) -> str:
        return text(company_data["campusDepartment"]["name"])
