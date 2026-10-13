"""Greentown's older server-rendered Beisen campus catalog."""

import re
from typing import Protocol, cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

HOST = "gtgroup.zhiye.com"


class Page(Protocol):
    async def content(self) -> str: ...


class HtmlSession(Protocol):
    page: Page
    last_evidence: str

    async def request_html(
        self, url: str, *, form: dict[str, str] | None = None, detail: bool = False
    ) -> str: ...


def catalog(document: BeautifulSoup) -> tuple[int, int, int, list[dict[str, str]]]:
    text = document.get_text(" ", strip=True)
    total = re.search(r"共\s*(\d+)\s*条记录", text)
    current = re.search(r"当前第\s*(\d+)\s*/\s*(\d+)\s*页", text)
    check(total is not None and current is not None, "绿城目录缺少总数或页码")
    assert total is not None and current is not None
    expected, page, pages = int(total[1]), int(current[1]), int(current[2])
    rows: list[dict[str, str]] = []
    for anchor in document.select('tr td a[href^="/zpdetail/"]'):
        parent = anchor.find_parent("tr")
        check(isinstance(parent, Tag), "绿城岗位表格结构改变")
        assert isinstance(parent, Tag)
        cells = parent.find_all("td", recursive=False)
        check(len(cells) >= 5, "绿城岗位表格列数改变")
        url = urljoin(f"https://{HOST}", str(anchor.get("href", "")))
        key = urlsplit(url).path.rsplit("/", 1)[-1]
        check(key.isdigit(), "绿城详情 ID 无效")
        rows.append(
            {
                "id": key,
                "url": url,
                "title": anchor.get_text(" ", strip=True),
                "category": cells[1].get_text(" ", strip=True),
                "batch": cells[2].get_text(" ", strip=True),
                "location": cells[3].get_text(" ", strip=True),
                "published": cells[4].get_text(" ", strip=True),
            }
        )
    return expected, page, pages, rows


def details(html: str, title: str) -> tuple[str, str, str, str, str]:
    document = BeautifulSoup(html, "html.parser")
    heading = document.select_one(".boxSupertitle span")
    check(
        isinstance(heading, Tag) and title in heading.get_text(" ", strip=True),
        "绿城详情标题不一致",
    )
    values: dict[str, str] = {}
    for label in document.select("li.ntitle"):
        neighbor = label.find_next_sibling("li")
        if isinstance(neighbor, Tag):
            values[label.get_text(" ", strip=True).rstrip("：:")] = neighbor.get_text(
                " ", strip=True
            )
    check(values.get("招聘类别") == "校园招聘", "绿城详情不是校园招聘")
    sections: dict[str, str] = {}
    for label in document.select(".xiangqingtext p.title"):
        neighbor = label.find_next_sibling("p")
        if isinstance(neighbor, Tag):
            sections[label.get_text(" ", strip=True).rstrip("：:")] = neighbor.get_text(
                "\n", strip=True
            )
    check(bool(sections.get("工作职责") and sections.get("任职资格")), "绿城详情职责或资格缺失")
    return (
        sections["工作职责"],
        sections["任职资格"],
        values.get("工作地点", ""),
        values.get("发布时间", ""),
        values.get("截止时间", ""),
    )


class GreentownCampus(Adapter):
    name = "greentown-2027-html"
    host = HOST
    path = "/campus/"
    scope_description = "绿城中国旧版北森校园目录 PageIndex 全页及 /zpdetail 详情"

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        scope = Scope(name="greentown-campus")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            html = (
                await session.page.content()
                if page == 1
                else await session.request_html(f"https://{HOST}/campus/?PageIndex={page}")
            )
            expected, active, pages, parsed = catalog(BeautifulSoup(html, "html.parser"))
            check(active == page, "绿城服务端返回了错误页码")
            check(pages == (expected + 14) // 15, "绿城总页数与十五条分页不符")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "绿城目录总数变化")
            rows = self.add_page(scope, parsed, seen, lambda row: row["id"])
            list_evidence = session.last_evidence
            check(len(rows) == min(15, expected - (page - 1) * 15), "绿城目录提前空白")
            for row in rows:
                key = row["id"]
                try:
                    detail = await session.request_html(row["url"], detail=True)
                    duties, requirements, location, published, deadline = details(
                        detail, row["title"]
                    )
                    check(
                        not published or published == row["published"], "绿城详情发布时间与目录不符"
                    )
                    job = self.job(
                        key,
                        title=row["title"],
                        batch=row["batch"],
                        category_raw=row["category"],
                        location=location or row["location"],
                        duties=duties,
                        requirements=requirements,
                        published=published or row["published"],
                        deadline=deadline,
                        source_url=row["url"],
                        apply_url=row["url"],
                        field_sources={
                            "duties": "zpdetail:工作职责",
                            "requirements": "zpdetail:任职资格",
                            "published": "zpdetail:发布时间/目录发布日期",
                            "deadline": "zpdetail:截止时间",
                        },
                    )
                    job.evidence = [list_evidence, session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if page >= pages:
                check(scope.unique == expected, "绿城目录唯一岗位数与总数不符")
                scope.terminal = True
                break
            page += 1
