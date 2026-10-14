"""Yingte jobs within the shared Zhejiang International Trade campus portal."""

import json
import math
from typing import Any
from urllib.parse import urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError

LIST_PATH = "/server/recruitpositionapply/listPage"
ORG_PATH = "/server/recruitpositionapply/org/list/all"
DETAIL_PATH = "/server/recruitpositionapply/getInfo/"
ROOT_NAME = "浙江英特集团股份有限公司"


def member_ids(nodes: list[dict[str, Any]]) -> set[str]:
    index = {str(node["id"]): node for node in nodes}
    check(len(index) == len(nodes), "英特组织树出现重复 ID")
    roots = [key for key, value in index.items() if value.get("name") == ROOT_NAME]
    check(len(roots) == 1, "英特组织树缺少唯一公司根")
    root = roots[0]
    members: set[str] = set()
    for key in index:
        seen: set[str] = set()
        current = key
        while current in index:
            check(current not in seen, "英特组织树存在循环")
            seen.add(current)
            if current == root:
                members.add(key)
                break
            current = str(index[current].get("parentId") or "")
    return members


class YingteCampus(Adapter):
    name = "yingte-campus"
    host = "recruit.zibchina.com"
    path = "/campus.html"
    ready_endpoints = (LIST_PATH, ORG_PATH)
    scope_description = (
        "浙江省国际贸易集团共享校园目录中，组织树隶属于浙江英特集团股份有限公司的岗位"
    )

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/position_detail.html?positionId={job_id}&channel=1"

    async def harvest(self) -> None:
        observed = await self.session.observed(LIST_PATH)
        check(urlsplit(observed["url"]).hostname == self.host, "英特目录接口域名改变")
        payload = json.loads(observed["post_data"])
        check(payload["conds"]["channel"] == 1, "英特目录不是校园渠道")
        check(
            not any(
                payload["conds"].get(key)
                for key in (
                    "name",
                    "orgIds",
                    "cityCodes",
                    "positionTypes",
                    "educations",
                    "salarys",
                    "experiences",
                )
            ),
            "英特校园目录存在局部筛选",
        )
        org_response = await self.session.observed(ORG_PATH)
        groups = json.loads(org_response["body"])
        check(isinstance(groups, list), "英特组织树不是数组")
        members = member_ids(groups)
        all_orgs = {str(node["id"]) for node in groups}
        scope = Scope(name="yingte-descendants-campus")
        self.result.scopes.append(scope)
        listings: list[tuple[dict[str, Any], str]] = []
        seen_all: set[str] = set()
        seen_members: set[str] = set()
        page = 1
        size = 50
        catalog_total: int | None = None
        pages: int | None = None
        try:
            while True:
                result = await self.session.request(
                    observed["url"],
                    payload={**payload, "pageNo": page, "pageSize": size},
                )
                check(isinstance(result.get("records"), list), "英特岗位列表不是数组")
                total = int(result["total"])
                returned_pages = int(result["pages"])
                check(
                    total >= 0 and returned_pages == math.ceil(total / size),
                    "英特目录总数与页数不一致",
                )
                check(
                    int(result["current"]) == page and int(result["size"]) == size,
                    "英特返回错误页码",
                )
                if catalog_total is None:
                    catalog_total, pages = total, returned_pages
                check(total == catalog_total and returned_pages == pages, "英特目录总数发生变化")
                rows = result["records"]
                check(len(rows) <= size, "英特单页超出容量")
                check(bool(rows) or page > 1 or total == 0, "英特目录首页意外为空")
                evidence = self.session.last_evidence
                for row in rows:
                    identity = str(row["id"])
                    check(identity not in seen_all, "英特岗位 ID 重复或分页循环")
                    seen_all.add(identity)
                    org = str(row["orgId"])
                    check(org in all_orgs, "英特目录岗位所属组织不在组织树中")
                    if org in members:
                        self.add_page(scope, [row], seen_members, lambda item: str(item["id"]))
                        listings.append((row, evidence))
                if page >= returned_pages:
                    check(len(seen_all) == total, "英特末页目录总数不符")
                    scope.expected = scope.unique
                    scope.terminal = True
                    break
                check(bool(rows), "英特分页提前为空")
                page += 1
        except Exception as exc:
            self.error(exc, f"page:{page}")

        for row, list_evidence in listings:
            job_id = str(row["id"])
            try:
                listing = self.job(
                    job_id,
                    title=text(row["name"]),
                    source_url=self.detail_page(job_id),
                    unit=text(row["orgName"]),
                    deadline=text(row.get("endTime")),
                )
                listing.evidence = [list_evidence] if list_evidence else []
                reused = self.before_detail(
                    f"job:{job_id}", row, scope, listing, evidence=list_evidence
                )
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                detail = await self.session.request(
                    f"https://{self.host}{DETAIL_PATH}{job_id}", detail=True
                )
                check(str(detail["id"]) == job_id, "英特详情岗位 ID 与列表不一致")
                check(str(detail["orgId"]) == str(row["orgId"]), "英特详情所属组织变化")
                check("1" in str(detail["channel"]).split(","), "英特详情不是校园渠道")
                check(text(detail["name"]) == text(row["name"]), "英特详情岗位名称变化")
                check("duty" in detail and "demand" in detail, "英特详情缺岗位正文")
                job = self.job(
                    job_id,
                    title=text(detail["name"]),
                    source_url=self.detail_page(job_id),
                    unit=text(detail.get("orgName")),
                    location="".join(text(detail.get(key)) for key in ("province", "city", "area")),
                    address=text(detail.get("address")),
                    education=text(detail.get("education")),
                    duties=text(detail["duty"]),
                    requirements=text(detail["demand"]),
                    deadline=text(detail.get("endTime")),
                    closed=text(detail.get("status")) != "进行中",
                    field_sources={
                        "duties": "getInfo.duty",
                        "requirements": "getInfo.demand",
                        "deadline": "getInfo.endTime",
                        "published": "源站未给发布日期，startTime 仅为开放时间",
                    },
                )
                job.evidence = [e for e in (list_evidence, self.session.last_evidence) if e]
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
