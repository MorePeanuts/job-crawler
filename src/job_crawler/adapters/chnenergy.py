"""National Energy Group's server-rendered campus form and job details."""

import re
from typing import Protocol, cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.filtering import select
from job_crawler.models import Scope

HOST = "zhaopin.chnenergy.com.cn"
LIST_PATH = "/recTypeSerch"
DETAIL_PATH = "/annc/showgw"


class Page(Protocol):
    async def content(self) -> str: ...


class HtmlSession(Protocol):
    page: Page
    last_evidence: str

    async def request_html(
        self, url: str, *, form: dict[str, str] | None = None, detail: bool = False
    ) -> str: ...


def page_counts(document: BeautifulSoup) -> tuple[int, int, int]:
    counters = [
        item
        for item in document.select("li.page-item")
        if "条，共" in item.get_text(" ", strip=True)
    ]
    check(len(counters) == 1, "国家能源目录缺少唯一总数/页数")
    numbers = counters[0].find_all("b")
    check(len(numbers) == 2, "国家能源目录总数结构变化")
    expected, pages = (int(item.get_text(strip=True)) for item in numbers)
    active = document.select("li.page-item.active a")
    check(len(active) == 1, "国家能源目录活动页码缺失")
    page = int(active[0].get_text(strip=True))
    check(pages == (expected + 9) // 10, "国家能源总页数与十条分页不符")
    return expected, pages, page


def card_fields(card: Tag) -> dict[str, str]:
    link = card.select_one('h3 a[href^="/annc/showgw?id="]')
    unit = card.select_one(".col-md-6 h5")
    lists = card.select("ul.list-inline")
    check(
        isinstance(link, Tag) and isinstance(unit, Tag) and len(lists) >= 2,
        "国家能源岗位卡片结构改变",
    )
    assert isinstance(link, Tag) and isinstance(unit, Tag)
    url = urljoin(f"https://{HOST}", str(link.get("href", "")))
    ids = parse_qs(urlsplit(url).query).get("id", [])
    check(len(ids) == 1 and bool(ids[0]), "国家能源岗位详情 ID 缺失")
    education = lists[0].select_one("li")
    location = lists[1].select_one("li")
    check(isinstance(education, Tag) and isinstance(location, Tag), "国家能源岗位学历或地点缺失")
    assert isinstance(education, Tag) and isinstance(location, Tag)
    deadline_node = card.select_one(".applyBtn p, .backbtn p")
    deadline_match = re.search(
        r"\d{4}-\d{2}-\d{2}", deadline_node.get_text(" ", strip=True) if deadline_node else ""
    )
    return {
        "id": ids[0],
        "url": url,
        "title": link.get_text(" ", strip=True),
        "unit": unit.get_text(" ", strip=True),
        "location": location.get_text(" ", strip=True),
        "education": education.get_text(" ", strip=True),
        "deadline": deadline_match.group(0) if deadline_match else "",
    }


def detail_fields(html: str, title: str) -> tuple[str, str, str, str]:
    document = BeautifulSoup(html, "html.parser")
    heading = document.select_one("h3.text-elip")
    check(
        isinstance(heading, Tag) and heading.get_text(" ", strip=True) == title,
        "国家能源详情岗位名称与目录不符",
    )
    date_nodes = document.select("blockquote.blockquote a strong")
    check(len(date_nodes) >= 2, "国家能源详情发布日期/截止日期结构改变")
    sections: dict[str, str] = {}
    for label in document.select("h4.listTitle"):
        parent = label.parent
        following = parent.find_next_sibling() if isinstance(parent, Tag) else None
        if isinstance(following, Tag):
            sections[label.get_text(" ", strip=True)] = following.get_text("\n", strip=True)
    check(bool(sections.get("岗位职责") and sections.get("岗位要求")), "国家能源详情职责或要求缺失")
    return (
        sections["岗位职责"],
        sections["岗位要求"],
        date_nodes[0].get_text(" ", strip=True),
        date_nodes[1].get_text(" ", strip=True),
    )


class Chnenergy(Adapter):
    name = "chnenergy-campus"
    host = HOST
    path = "/recTypeSerch?kinds=1&schType=2"
    scope_description = (
        "国家能源集团校招 kinds=1/schType=2 全单位十条分页；按截止日期跳过已过期详情"
    )

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        scope = Scope(name="campus-all-units")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 0
        form = {
            "pagenum": "0",
            "kinds": "1",
            "schType": "2",
            "unitCode": "",
            "ebDownAll": "",
            "transAreaCode": "",
            "workPlaceCode": "",
            "searchtype": "job",
            "workUnit": "",
            "station": "",
            "stationkind": "",
            "ebDown": "",
        }
        while True:
            html = (
                await session.page.content()
                if page == 0
                else await session.request_html(
                    f"https://{HOST}{LIST_PATH}", form={**form, "pagenum": str(page)}
                )
            )
            document = BeautifulSoup(html, "html.parser")
            expected, pages, active = page_counts(document)
            check(active == page + 1, "国家能源服务端返回了错误页码")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "国家能源目录总数变化")
            cards = document.select('li.list-group-item:has(h3 a[href^="/annc/showgw?id="])')
            rows = self.add_page(
                scope, [card_fields(card) for card in cards], seen, lambda row: row["id"]
            )
            list_evidence = session.last_evidence
            check(len(rows) == min(10, expected - page * 10), "国家能源目录提前空白或页长改变")
            for row in rows:
                key = row["id"]
                try:
                    listing = self.job(
                        key,
                        title=row["title"],
                        unit=row["unit"],
                        location=row["location"],
                        education=row["education"],
                        deadline=row["deadline"],
                        source_url=row["url"],
                        apply_url=row["url"],
                    )
                    listing.evidence = [list_evidence]
                    if select(listing, "all", self.as_of).reason == "expired":
                        listing.detail_mode = "listing_only"
                        self.result.jobs.append(listing)
                        scope.skipped_expired += 1
                        continue
                    resolved = self.before_detail(
                        f"job:{key}", row, scope, listing, evidence=list_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    detail = await session.request_html(row["url"], detail=True)
                    duties, requirements, published, deadline = detail_fields(detail, row["title"])
                    check(
                        not row["deadline"]
                        or row["deadline"].replace("-", "")
                        in deadline.replace("年", "").replace("月", "").replace("日", ""),
                        "国家能源详情截止日期与目录不符",
                    )
                    job = listing.model_copy(deep=True)
                    job.duties = duties
                    job.requirements = requirements
                    job.published = published
                    job.deadline = deadline
                    job.evidence = [list_evidence, session.last_evidence]
                    job.field_sources = {
                        "duties": "annc/showgw:岗位职责",
                        "requirements": "annc/showgw:岗位要求",
                        "published": "annc/showgw:发布时间",
                        "deadline": "annc/showgw:截止时间",
                    }
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if page + 1 >= pages:
                check(scope.unique == expected, "国家能源目录唯一岗位数与总数不符")
                scope.terminal = True
                break
            page += 1
