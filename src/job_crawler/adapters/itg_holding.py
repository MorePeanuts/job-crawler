"""ITG Holding's server-rendered, paginated public campus catalog."""

import re
from typing import Any, cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError


def field(label: str, values: list[str]) -> str:
    return next(
        (value.split("：", 1)[1].strip() for value in values if value.startswith(f"{label}：")),
        "",
    )


class ItgHoldingCampus(Adapter):
    name = "itg-holding-campus"
    host = "itgholding.zhiye.com"
    path = "/gmkgxzall"
    scope_description = "厦门国贸控股集团官网旧版北森校园招聘无筛选全目录、全部页码与逐岗详情"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        scope = Scope(name="campus-html-all-pages")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        total_pages: int | None = None
        while True:
            url = f"https://{self.host}{self.path}/?PageIndex={page}"
            html = await session.request_html(url)
            listing_evidence = session.last_evidence
            soup = BeautifulSoup(html, "html.parser")
            check(
                bool(soup.select_one("#xyzp")) and bool(soup.select_one(".zwlb")),
                "国贸控股校园目录结构变化",
            )
            current = soup.select_one(".page a.now")
            check(current is not None and text(current) == str(page), "国贸控股分页当前页错配")
            page_numbers = {
                int(text(link)) for link in soup.select(".page a") if text(link).isdigit()
            }
            check(bool(page_numbers) and min(page_numbers) == 1, "国贸控股分页导航缺失")
            discovered_pages = max(page_numbers)
            if total_pages is None:
                total_pages = discovered_pages
            check(total_pages == discovered_pages and page <= total_pages, "国贸控股分页数量变化")
            cards: list[dict[str, Any]] = []
            for link in soup.select('.zwlb li a[href*="gmkgallxq?jobId="]'):
                href = str(link.get("href") or "")
                job_ids = parse_qs(urlsplit(href).query).get("jobId", [])
                check(len(job_ids) == 1 and job_ids[0].isdigit(), "国贸控股目录岗位 ID 缺失")
                heading = link.select_one("h2")
                if heading is None or not heading.contents:
                    raise CrawlError("source_changed", "国贸控股目录标题缺失")
                title = text(heading.contents[0]).strip()
                check(bool(re.search(r"\(J\d+\)$", title)), "国贸控股目录岗位编号缺失")
                cards.append(
                    {
                        "id": job_ids[0],
                        "title": title,
                        "unit": field("招聘单位", [text(x) for x in link.select(".icon9a")]),
                        "published": field("发布时间", [text(x) for x in link.select(".icon9d")]),
                        "url": urljoin(url, href),
                    }
                )
            rows = self.add_page(scope, cards, seen, lambda item: str(item["id"]))
            check(bool(rows) and len(rows) <= 10, "国贸控股目录为空或超过单页上限")
            next_link = soup.select_one(".page a.next:last-child")
            if page < total_pages:
                check(
                    len(rows) == 10
                    and next_link is not None
                    and f"PageIndex={page + 1}" in str(next_link.get("href")),
                    "国贸控股非末页不完整",
                )
            else:
                check(
                    next_link is not None and next_link.has_attr("disabled"),
                    "国贸控股末页未关闭下一页",
                )
            for row in rows:
                key = str(row["id"])
                try:
                    draft = self.job(
                        key,
                        title=re.sub(r"\(J\d+\)$", "", str(row["title"])),
                        source_url=str(row["url"]),
                        work_type="校招",
                        unit=str(row["unit"]),
                        published=str(row["published"]),
                    )
                    resolved = self.before_detail(
                        f"job:{key}", row, scope, draft, evidence=listing_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    detail_html = await session.request_html(str(row["url"]), detail=True)
                    detail_evidence = session.last_evidence
                    detail = BeautifulSoup(detail_html, "html.parser")
                    detail_title = text(detail.select_one(".zwxq h2"))
                    check(detail_title == row["title"], "国贸控股详情岗位标题/编号错配")
                    values = [text(x) for x in detail.select(".zwxqt li")]
                    unit = field("招聘单位", values)
                    published = field("发布时间", values)
                    check(
                        unit == row["unit"] and published == row["published"],
                        "国贸控股详情单位或发布日期错配",
                    )
                    sections: dict[str, str] = {}
                    for heading in detail.select(".zwxqm h3"):
                        sibling = heading.find_next_sibling("div")
                        if sibling is not None:
                            sections[text(heading)] = text(sibling)
                    check(
                        bool(sections.get("工作职责")) and bool(sections.get("任职资格")),
                        "国贸控股详情职责或资格缺失",
                    )
                    job = self.job(
                        key,
                        title=draft.title,
                        source_url=str(row["url"]),
                        work_type="校招",
                        unit=unit,
                        location=field("工作地址", values),
                        duties=sections["工作职责"],
                        requirements=sections["任职资格"],
                        published=published,
                        deadline=field("结束时间", values),
                        field_sources={
                            "unit": "gmkgallxq .zwxqt 招聘单位",
                            "location": "gmkgallxq .zwxqt 工作地址",
                            "duties": "gmkgallxq .zwxqm 工作职责",
                            "requirements": "gmkgallxq .zwxqm 任职资格",
                            "published": "gmkgallxq .zwxqt 发布时间",
                            "deadline": "gmkgallxq .zwxqt 结束时间",
                        },
                    )
                    job.evidence = [listing_evidence, detail_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if page == total_pages:
                scope.expected = scope.unique
                scope.terminal = True
                break
            page += 1
