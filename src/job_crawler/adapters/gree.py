"""Gree Electric's public graduate job directory."""

from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError


class GreeCampus(Adapter):
    name = "gree-campus"
    host = "zhaopin.greeyun.com"
    path = "/home"
    ready_endpoints = ("/api/apply/jobs?",)
    scope_description = "格力电器官网 property=1 校招无筛选全目录，逐岗校验详情"

    async def harvest(self) -> None:
        observed = await self.session.observed("/api/apply/jobs?")
        params = parse_qs(urlsplit(observed["url"]).query, keep_blank_values=True)
        check(
            params == {"category": [""], "pageNum": ["1"], "pageSize": ["8"], "property": ["1"]},
            "格力校招目录入口或筛选发生变化",
        )
        base = observed["url"].split("?", 1)[0]
        scope = Scope(name="campus-property-1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            url = (
                base
                + "?"
                + urlencode({"category": "", "pageNum": page, "pageSize": 8, "property": 1})
            )
            response = await self.session.request(url)
            check(response.get("code") == 200, "格力校招列表业务失败")
            body = response["data"]
            expected = int(body["total"])
            check(expected > 0, "格力校招目录为空或计数无效")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "格力校招翻页期间总数变化")
            rows = self.add_page(scope, body["list"], seen, lambda row: str(row["Code"]))
            check(len(rows) <= 8, "格力校招页面超过观察到的每页容量")
            list_evidence = self.session.last_evidence
            for row in rows:
                key = str(row["Code"])
                try:
                    check(
                        row.get("property") == 1
                        and row.get("Status") == 1
                        and text(row.get("Experience")) == "应届毕业生",
                        "格力校招列表混入其他招聘类型或关闭岗位",
                    )
                    check(bool(text(row.get("Position"))), "格力校招岗位名称为空")
                    detail_url = f"https://{self.host}/job?" + urlencode(
                        {"JobCode": key, "recruitType": 1}
                    )
                    listing = self.job(
                        key,
                        title=text(row["Position"]),
                        source_url=detail_url,
                        apply_url=detail_url,
                        unit=self.source.company,
                        location=text(row.get("Location")),
                        education=text(row.get("Education")),
                        category_raw=text(row.get("Category")),
                        duties=text(row.get("Description")),
                        requirements=text(row.get("Qualifications")),
                        published=text(row.get("PubTime")),
                        field_sources={
                            "unit": "格力电器官方独立招聘域名 + 名录主体",
                            "location": "jobs.data.list[].Location；不使用面试城市",
                            "published": "jobs.data.list[].PubTime",
                            "deadline": "source_missing",
                        },
                    )
                    resolved = self.before_detail(
                        f"job:{key}", row, scope, listing, evidence=list_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    detail_response = await self.session.request(
                        f"https://{self.host}/api/apply/job/details?jobCode={key}",
                        detail=True,
                    )
                    check(detail_response.get("code") == 200, "格力校招详情业务失败")
                    detail: dict[str, Any] = detail_response["data"]
                    check(
                        str(detail.get("Code")) == key
                        and str(detail.get("ID")) == str(row.get("ID"))
                        and text(detail.get("Position")) == listing.title,
                        "格力校招详情与列表不匹配",
                    )
                    check(detail.get("Status") == 1, "格力校招详情已关闭")
                    listing.location = text(detail.get("Location"))
                    listing.education = text(detail.get("Education"))
                    listing.duties = text(detail.get("Description"))
                    listing.requirements = text(detail.get("Qualifications"))
                    listing.published = text(detail.get("PubTime"))
                    listing.evidence = [list_evidence, self.session.last_evidence]
                    self.result.jobs.append(listing)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [listing])
                except Exception as exc:
                    self.error(exc, key)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if scope.unique == expected:
                check(len(rows) <= 8, "格力校招末页容量异常")
                scope.terminal = True
                break
            check(len(rows) == 8 and scope.unique < expected, "格力校招目录提前结束")
            page += 1
