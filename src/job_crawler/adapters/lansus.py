"""Lansus's public, server-rendered campus job catalog."""

from typing import Any, Protocol, cast
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, query
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Page(Protocol):
    async def evaluate(self, script: str) -> Any: ...


class PageSession(Protocol):
    page: Page

    async def request_html(self, url: str, *, detail: bool = False) -> str: ...


class LansusCampus(Adapter):
    name = "lansus-campus"
    host = "www.lansus.com"
    path = "/about/careers/campus-jobs"
    scope_description = "飞骧科技官网校园招聘频道的全部分页和逐岗详情；与社会招聘目录分离"

    async def harvest(self) -> None:
        scope = Scope(name="official-campus-pages")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page_num = 1
        total_pages: int | None = None
        while True:
            if page_num > 1:
                await self.session.open(query(f"https://{self.host}{self.path}", page=page_num))
            page = await cast(PageSession, self.session).page.evaluate(
                """() => ({
                  path: location.pathname,
                  current: Number(new URLSearchParams(location.search).get('page') || '1'),
                  pages: [...document.querySelectorAll('a[aria-label^="第 "][href*="page="]')]
                    .map(a => Number(new URL(a.href).searchParams.get('page'))),
                  rows: [...document.querySelectorAll('a[href^="/about/careers/campus-jobs/campus-"]')]
                    .map(a => ({
                      id: a.getAttribute('href')?.split('/').pop() || '',
                      url: a.href,
                      title: a.querySelector('h3')?.textContent?.trim() || '',
                      fields: [...a.querySelectorAll('h3 + div > span')]
                        .map(s => s.firstChild?.textContent?.trim() || '')
                    }))
                })"""
            )
            check(page["path"] == self.path and page["current"] == page_num, "飞骧校园页码错配")
            pages = [1, page_num, *page["pages"]]
            check(all(n > 0 for n in pages), "飞骧校园页码无效")
            if total_pages is None:
                total_pages = max(pages)
            check(max(pages) == total_pages, "飞骧校园分页边界变化")
            rows = page["rows"]
            check(bool(rows) and len(rows) <= 9, "飞骧校园列表为空或超过页长")
            if page_num < total_pages:
                check(len(rows) == 9, "飞骧校园非末页不满九岗")
            fresh = self.add_page(scope, rows, seen, lambda row: str(row["id"]))
            for row in fresh:
                key = str(row["id"])
                try:
                    check(key.startswith("campus-"), "飞骧校园职位 ID 格式改变")
                    check(urlsplit(row["url"]).path == f"{self.path}/{key}", "职位链接越出校园目录")
                    check(len(row["fields"]) == 3 and bool(row["title"]), "飞骧职位卡片字段缺失")
                    cached = self.before_detail(f"job:{key}", row, scope)
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        continue
                    html = await cast(PageSession, self.session).request_html(
                        row["url"], detail=True
                    )
                    detail = self.parse_detail(html)
                    check(detail["title"] == row["title"], "飞骧详情标题与列表不一致")
                    check(bool(detail["duties"] and detail["requirements"]), "飞骧岗位正文缺失")
                    job = self.job(
                        key,
                        title=detail["title"],
                        work_type="校招",
                        source_url=row["url"],
                        apply_url=detail["apply"] or row["url"],
                        education=row["fields"][0],
                        category_raw=row["fields"][1],
                        location=row["fields"][2].replace("/", "、"),
                        duties=detail["duties"],
                        requirements=detail["requirements"],
                        field_sources={
                            "duties": "官网校园详情岗位职责",
                            "requirements": "官网校园详情岗位要求",
                            "education": "官网校园列表学历",
                            "published": "source_missing",
                            "deadline": "source_missing",
                        },
                    )
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if page_num == total_pages:
                check(not any(n > page_num for n in page["pages"]), "飞骧末页仍有后续页")
                scope.expected = scope.unique
                scope.terminal = True
                return
            page_num += 1

    @staticmethod
    def parse_detail(html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one("h1")
        check(title is not None, "飞骧职位详情无标题")
        assert title is not None
        sections: dict[str, str] = {}
        for heading in soup.select("h4"):
            label = heading.get_text(" ", strip=True)
            if label in {"岗位职责", "岗位要求"}:
                body = heading.find_next_sibling("div")
                check(body is not None, f"飞骧{label}正文容器缺失")
                assert body is not None
                sections[label] = body.get_text("\n", strip=True)
        apply = next(
            (
                str(a.get("href"))
                for a in soup.select("a[href]")
                if a.get_text(" ", strip=True) == "立即申请"
            ),
            "",
        )
        return {
            "title": title.get_text(" ", strip=True),
            "duties": sections.get("岗位职责", ""),
            "requirements": sections.get("岗位要求", ""),
            "apply": apply,
        }
