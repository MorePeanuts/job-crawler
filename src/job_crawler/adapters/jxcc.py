"""Jiangxi Copper Group's public campus CMS catalog."""

import json
import math
from urllib.parse import urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

LIST_PATH = "/cebest-cms/cus/search"


class JxccCampus(Adapter):
    name = "jxcc-campus"
    host = "www.jxcc.com"
    path = "/join/xyJoinList.html"
    ready_endpoints = (LIST_PATH,)
    scope_description = "江西铜业集团官网校园招聘 M000510 全目录；所属单位保留源字段"

    async def harvest(self) -> None:
        observed = await self.session.observed(LIST_PATH)
        check(urlsplit(observed["url"]).hostname == self.host, "江铜校园接口域名变化")
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {
                "limit": 10,
                "menuCode": "M000510",
                "page": 1,
                "searchCondition": "",
                "setting": 0,
                "sign": "",
                "sort": "",
            },
            "江铜校园列表出现未知筛选",
        )
        scope = Scope(name="campus-menu-M000510")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        pages: int | None = None
        size = 10
        while True:
            result = await self.session.request(observed["url"], payload={**payload, "page": page})
            total = int(result["totalElements"])
            returned_pages = int(result["totalPages"])
            check(
                total >= 0 and returned_pages == math.ceil(total / size), "江铜目录页数与总数不一致"
            )
            check(
                int(result["number"]) == page - 1 and int(result["size"]) == size,
                "江铜返回错误页码",
            )
            rows = result["content"]
            check(isinstance(rows, list), "江铜校园职位不是数组")
            check(
                len(rows) == int(result["numberOfElements"]) and len(rows) <= size,
                "江铜单页数量不符",
            )
            if scope.expected is None:
                scope.expected, pages = total, returned_pages
            check(total == scope.expected and returned_pages == pages, "江铜分页期间目录总数变化")
            fresh = self.add_page(scope, rows, seen, lambda row: str(row["id"]))
            evidence = self.session.last_evidence
            for row in fresh:
                check(row.get("menuCode") == "M000510", "江铜目录混入其他菜单")
                check(
                    bool(row.get("openDataId")) and bool(row.get("title")), "江铜岗位身份字段缺失"
                )
                detail_url = row.get("single10")
                check(
                    isinstance(detail_url, str)
                    and bool(detail_url)
                    and urlsplit(detail_url).scheme == "https"
                    and urlsplit(detail_url).hostname in {"jthr.jxcc.com", "www.jxcc.com"},
                    "江铜岗位详情链接不是官方域名",
                )
                check("content1" in row and "content2" in row, "江铜岗位正文结构变化")
                key = str(row["id"])
                job = self.job(
                    key,
                    title=text(row["title"]),
                    source_url=detail_url,
                    apply_url=detail_url,
                    work_type=("实习" if "实习" in text(row["title"]) else "校招"),
                    unit=text(row.get("single2")),
                    category_raw=text(row.get("single3")),
                    education=text(row.get("single5")),
                    location=text(row.get("single8")),
                    duties=text(row["content1"]),
                    requirements=text(row["content2"]),
                    published=text(row.get("postTime")),
                    deadline=text(row.get("endDate")),
                    field_sources={
                        "unit": "cus/search.content[].single2",
                        "duties": "cus/search.content[].content1",
                        "requirements": "cus/search.content[].content2",
                        "published": "cus/search.content[].postTime",
                        "deadline": "cus/search.content[].endDate",
                    },
                )
                job.evidence = [evidence] if evidence else []
                reused = self.before_detail(f"job:{key}", row, scope, job, evidence=evidence)
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            if page >= returned_pages:
                check(bool(result["last"]) and scope.unique == total, "江铜目录末页或唯一总数不符")
                scope.terminal = True
                break
            check(bool(fresh) and not result["last"], "江铜目录提前结束")
            page += 1
