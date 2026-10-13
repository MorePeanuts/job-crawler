"""SMIC's server-rendered campus pages and job details."""

from typing import Protocol, cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

HOST = "smics.zhiye.com"
ROOT = f"https://{HOST}"


class Page(Protocol):
    async def content(self) -> str: ...


class HtmlSession(Protocol):
    page: Page
    last_evidence: str

    async def request_html(
        self, url: str, *, form: dict[str, str] | None = None, detail: bool = False
    ) -> str: ...


def catalog(html: str) -> tuple[int, int, bool, list[dict[str, str]]]:
    document = BeautifulSoup(html, "html.parser")
    pager = document.select_one("div.page.pt50")
    check(isinstance(pager, Tag), "中芯国际目录缺少分页")
    assert isinstance(pager, Tag)
    current = pager.select_one("a.now")
    next_button = next(
        (a for a in pager.select("a.next") if a.get_text(strip=True) == "下一页"), None
    )
    check(isinstance(current, Tag) and isinstance(next_button, Tag), "中芯国际分页结构改变")
    assert isinstance(current, Tag) and isinstance(next_button, Tag)
    check(current.get_text(strip=True).isdigit(), "中芯国际当前页码无效")
    page = int(current.get_text(strip=True))
    numbers = [
        int(a.get_text(strip=True)) for a in pager.select("a") if a.get_text(strip=True).isdigit()
    ]
    check(bool(numbers), "中芯国际缺少总页数")
    pages = max(numbers)
    terminal = "disabled" in next_button.attrs and not next_button.get("href")
    check((page == pages) == terminal, "中芯国际页码与末页状态不符")
    rows: list[dict[str, str]] = []
    for anchor in document.select('a[href^="/campusxq?"]'):
        spans = anchor.select("span")
        check(len(spans) >= 4, "中芯国际目录列数改变")
        url = urljoin(ROOT, str(anchor.get("href", "")))
        ids = parse_qs(urlsplit(url).query).get("jobId", [])
        check(len(ids) == 1 and ids[0].isdigit(), "中芯国际详情 ID 无效")
        rows.append(
            {
                "id": ids[0],
                "url": url,
                "category": spans[0].get_text(" ", strip=True),
                "education": spans[2].get_text(" ", strip=True),
                "location": spans[3].get_text(" ", strip=True),
            }
        )
    check(bool(rows) and len(rows) <= 10, "中芯国际目录页为空或超过十条")
    if not terminal:
        check(len(rows) == 10, "中芯国际非末页不足十条")
    return page, pages, terminal, rows


def detail(html: str) -> dict[str, str]:
    document = BeautifulSoup(html, "html.parser")
    box = document.select_one(".xqbox")
    check(isinstance(box, Tag), "中芯国际详情结构改变")
    assert isinstance(box, Tag)
    heading = box.select_one(".xqtitle h2")
    check(isinstance(heading, Tag), "中芯国际详情缺少标题")
    assert isinstance(heading, Tag)
    values: dict[str, str] = {}
    for item in box.select(".xqt li"):
        label = item.select_one("span")
        value = item.select_one("b")
        if isinstance(label, Tag) and isinstance(value, Tag):
            values[label.get_text(" ", strip=True).rstrip("：:")] = value.get_text(" ", strip=True)
    sections: dict[str, str] = {}
    for section in box.select("h3"):
        following = section.find_next_sibling("div", class_="xqm")
        if isinstance(following, Tag):
            sections[section.get_text(" ", strip=True)] = following.get_text("\n", strip=True)
    check(bool(sections.get("职位描述") and sections.get("职位要求")), "中芯国际详情缺少描述或要求")
    return {
        "title": heading.get_text(" ", strip=True),
        "category": values.get("职位类别", ""),
        "education": values.get("职位学历", ""),
        "location": values.get("工作地点", ""),
        "updated": values.get("更新时间", ""),
        "duties": sections["职位描述"],
        "requirements": sections["职位要求"],
    }


class SmicCampus(Adapter):
    name = "smic-campus-html"
    host = HOST
    path = "/campus/jobs"
    scope_description = "中芯国际校园目录 10 条分页及 /campusxq 岗位详情"

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        scope = Scope(name="smic-campus")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        pages: int | None = None
        page = 1
        while True:
            html = (
                await session.page.content()
                if page == 1
                else await session.request_html(f"{ROOT}/campus/?PageIndex={page}")
            )
            current, page_count, terminal, parsed = catalog(html)
            check(current == page, "中芯国际返回了错误目录页")
            if pages is None:
                pages = page_count
            check(pages == page_count, "中芯国际分页总数变化")
            rows = self.add_page(scope, parsed, seen, lambda row: row["id"])
            list_evidence = session.last_evidence
            for row in rows:
                key = row["id"]
                try:
                    html_detail = await session.request_html(row["url"], detail=True)
                    values = detail(html_detail)
                    check(values["category"] == row["category"], "中芯国际详情职位类别不符")
                    check(values["education"] == row["education"], "中芯国际详情学历不符")
                    job = self.job(
                        key,
                        title=values["title"],
                        category_raw=values["category"],
                        education=values["education"],
                        location=values["location"] or row["location"],
                        duties=values["duties"],
                        requirements=values["requirements"],
                        source_url=row["url"],
                        apply_url=row["url"],
                        field_sources={
                            "duties": "campusxq:职位描述",
                            "requirements": "campusxq:职位要求",
                            "education": "campusxq:职位学历",
                            "published": f"源站只提供更新时间 {values['updated']}，首次发布时间未知",
                        },
                    )
                    job.evidence = [list_evidence, session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if terminal:
                check(page == pages, "中芯国际提前出现末页标记")
                check(scope.unique == (pages - 1) * 10 + len(rows), "中芯国际页数与岗位数不符")
                scope.terminal = True
                break
            page += 1
            check(page <= pages, "中芯国际超出首页声明页数")
