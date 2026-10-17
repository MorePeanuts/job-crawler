"""Listed Shenergy company boundary derived from the portal's public unit tree."""

from typing import Any

from job_crawler.adapters.base import text
from job_crawler.adapters.platforms import check
from job_crawler.adapters.zhiye import Zhiye


def unit_names(data: dict[str, Any]) -> tuple[set[str], set[str]]:
    check(data.get("Code") == 200, "申能单位树业务失败")
    root = data["Data"]["Type"]
    check(root["TypeCode"] == 1 and root["Text"] == "招聘单位", "申能单位树类型改变")
    all_names: set[str] = set()
    included: set[str] = set()
    targets = 0

    def visit(node: dict[str, Any], inside: bool = False) -> None:
        nonlocal targets
        name = text(node["Text"])
        check(bool(name) and name not in all_names, "申能单位树名称缺失或重复，无法唯一关联")
        all_names.add(name)
        if name == "申能股份有限公司":
            check(node["Value"] == 6, "申能股份单位树标识改变")
            targets += 1
            inside = True
        if inside:
            included.add(name)
        children = node["Items"]
        check(isinstance(children, list), "申能单位树分支结构改变")
        for child in children:
            visit(child, inside)

    for node in root["Items"]:
        visit(node)
    check(targets == 1, "申能股份单位节点缺失或不唯一")
    return all_names, included


class ShenergyListedCampus(Zhiye):
    name = "zhiye-shenergy-listed-campus"
    host = "shenergy.zhiye.com"
    path = "/custom/campus"
    detail_path = "/custom/campusxq"
    listing_complete = True
    regular_only = True
    category_field = "ClassificationTwo"
    scope_description = "申能集团公开校招全目录中，官方单位树申能股份有限公司及其全部下属单位"

    async def harvest(self) -> None:
        observed = await self.session.observed("/api/OpenCustomization/GetJobAdCustomTypeList")
        data = await self.session.request(observed["url"], payload={"TypeCode": 1})
        tree_evidence = self.session.last_evidence
        self.all_units, self.included_units = unit_names(data)
        await super().harvest()
        for scope in self.result.scopes:
            if tree_evidence not in scope.evidence:
                scope.evidence.append(tree_evidence)
        for job in self.result.jobs:
            if tree_evidence not in job.evidence:
                job.evidence.append(tree_evidence)
            job.field_sources["unit"] = "Org 与官方 TypeCode=1 单位树申能股份节点及后代关联"

    def in_scope(self, row: dict[str, Any]) -> bool:
        unit = text(row.get("Org"))
        check(unit in self.all_units, "申能岗位单位不在官方单位树中")
        check(text(row.get("ClassificationOne")) == unit, "申能岗位单位与分类归属不一致")
        return unit in self.included_units
