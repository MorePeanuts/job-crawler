"""United Aircraft's server-rendered official campus catalog."""

import re
from typing import Any, Protocol, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope


class Page(Protocol):
    async def content(self) -> str: ...


class PageSession(Protocol):
    page: Page


class UatairCampus(Adapter):
    name = "uatair-campus"
    host = "www.uatair.com"
    path = "/about/school.html"
    scope_description = "联合飞机官网独立校园招聘页全部服务端岗位卡片；不含社会招聘"

    async def harvest(self) -> None:
        html = await cast(PageSession, self.session).page.content()
        rows = self.parse_catalog(html)
        scope = Scope(name="official-campus-page")
        self.result.scopes.append(scope)
        scope.expected = len(rows)
        seen: set[str] = set()
        fresh = self.add_page(scope, rows, seen, lambda row: str(row["id"]))
        for row in fresh:
            key = str(row["id"])
            try:
                if "实习" in str(row["title"]) or "在校生" in str(row["title"]):
                    scope.skipped_out_of_scope += 1
                    continue
                job = self.job(
                    key,
                    title=str(row["title"]),
                    source_url=f"https://{self.host}{self.path}",
                    apply_url=f"https://{self.host}{self.path}",
                    work_type="校招",
                    location=str(row["location"]),
                    published=str(row["published"]),
                    duties=str(row["duties"]),
                    requirements=str(row["requirements"]),
                    field_sources={
                        "duties": "官网校园卡片正文",
                        "requirements": "官网校园卡片正文",
                        "location": "官网校园卡片地点",
                        "published": "官网校园卡片发布时间",
                        "deadline": "source_missing",
                    },
                )
                resolved = self.before_detail(f"job:{key}", row, scope, job)
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True

    @staticmethod
    def parse_catalog(html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        active = soup.select_one('a[href="/about/school.html"].active')
        check(active is not None, "联合飞机当前页不是校园招聘")
        container = soup.select_one("#gwList")
        check(container is not None, "联合飞机校园目录容器缺失")
        assert container is not None
        check(not soup.select("#gwList .pagination, #gwList .load-more"), "校园目录出现分页")
        cards = container.select(":scope > .col-12")
        check(bool(cards), "联合飞机校园目录为空")
        options = [
            option.get_text(" ", strip=True)
            for option in soup.select("#zwid option[value]")
            if option.get("value")
        ]
        rows: list[dict[str, Any]] = []
        for card in cards:
            head = card.select_one("[data-id]")
            title = card.select_one(".title-show")
            summary = card.select_one(".v1-size16-font.v1-sec-font")
            body = card.select_one(".v1-jd-con")
            check(all((head, title, summary, body)), "联合飞机岗位卡片字段缺失")
            assert (
                head is not None and title is not None and summary is not None and body is not None
            )
            key = str(head.get("data-id", ""))
            check(key.isdecimal(), "联合飞机岗位 ID 无效")
            title_text = title.get_text(" ", strip=True)
            summary_text = summary.get_text("", strip=True)
            match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[^|]*\|职位数：\d+\|(.+)", summary_text)
            check(match is not None, "联合飞机岗位发布时间或地点格式变化")
            assert match is not None
            body_text = body.get_text("\n", strip=True)
            check(bool(body_text), "联合飞机岗位正文为空")
            duties, requirements = split_sections(body_text)
            rows.append(
                {
                    "id": key,
                    "title": title_text,
                    "published": match.group(1),
                    "location": match.group(2).strip(),
                    "duties": duties,
                    "requirements": requirements,
                }
            )
        check(
            len(options) == len(rows)
            and len(set(options)) == len(options)
            and all(
                any(str(row["title"]).startswith(option) for row in rows) for option in options
            ),
            "校园筛选项与目录不一致",
        )
        check(len({row["id"] for row in rows}) == len(rows), "联合飞机校园岗位 ID 重复")
        return rows
