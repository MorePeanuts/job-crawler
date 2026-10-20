"""恒力重工在高校 2027 届招聘公告公开的三个职位。"""

import re
from typing import cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "恒力重工集团有限公司"
ROOT = "https://job.neuq.edu.cn"
TITLE = "恒力重工集团2027届校园招聘"
DETAIL = re.compile(r"/job/view/id/(\d+)/from_type/4/from_id/861683")
PUBLISHED = re.compile(r"发布时间：\s*(\d{4}-\d{2}-\d{2})")


def roster(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    check(TITLE in page_text and EMPLOYER in page_text, "恒力重工高校招聘公告主体或届别改变")
    check(
        re.search(r"恒力重工产业园\s*2027届校园\s*招聘简章", page_text) is not None,
        "恒力重工 2027 简章缺失",
    )
    date_match = PUBLISHED.search(page_text)
    check(date_match is not None, "恒力重工公告发布时间缺失")
    assert date_match is not None
    tables = [table for table in soup.select("table") if table.select(".apply_job[data-id]")]
    check(len(tables) == 1, "恒力重工高校职位表缺失或重复")
    check(not soup.select(".pagination, .pages"), "恒力重工职位表出现分页")
    rows = tables[0].select("tr")
    check(len(rows) == 4, "恒力重工高校职位表三岗范围改变")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows[1:], start=1):
        cells = row.find_all("td", recursive=False)
        check(len(cells) == 4 and text(cells[0].get_text()) == f"{index:02d}", "恒力职位行结构改变")
        anchor = cells[1].select_one("a.text-primary[href]")
        apply = cells[3].select_one(".apply_job[data-id]")
        check(anchor is not None and apply is not None, "恒力职位详情或申请 ID 缺失")
        assert anchor is not None and apply is not None
        url = urljoin(ROOT, str(anchor["href"]))
        matched = DETAIL.fullmatch(urlsplit(url).path)
        check(
            matched is not None and matched.group(1) == text(apply["data-id"]),
            "恒力职位链接与申请 ID 不一致",
        )
        assert matched is not None
        key = matched.group(1)
        check(key not in seen, "恒力职位申请 ID 重复")
        seen.add(key)
        title = text(anchor.get_text(" ", strip=True))
        facts = [text(li.get_text(" ", strip=True)) for li in cells[1].select("li")]
        check(bool(title) and len(facts) >= 3 and facts[2] == "全职", "恒力职位标题或性质改变")
        majors = text(cells[2].get_text(" ", strip=True))
        check(bool(majors), "恒力职位专业要求缺失")
        result.append({"id": key, "title": title, "url": url, "majors": majors})
    return date_match.group(1), result


def verify_detail(html: str, listed: dict[str, str], published: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("span.title[title]")
    employer = soup.select_one('a[href="/company/view/id/956041"]')
    page_text = soup.get_text(" ", strip=True)
    check(
        title is not None
        and text(title.get_text()) == listed["title"]
        and employer is not None
        and text(employer.get_text()) == EMPLOYER,
        "恒力职位详情标题或企业账号不一致",
    )
    check(
        re.search(r"2027届校园\s*招聘简章", page_text) is not None, "恒力职位详情不再是 2027 届简章"
    )
    check(f"{published}发布" in page_text, "恒力职位列表与详情发布时间不一致")


class HengliShipbuilding2027(Adapter):
    name = "hengli-shipbuilding-2027"
    host = "job.neuq.edu.cn"
    path = "/campus/view/id/861683"
    scope_description = "恒力集团所设恒力重工集团在东北大学秦皇岛分校2027届校园公告的三个职位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "恒力重工高校公告未就绪")
        published, rows = roster(await session.page.content())
        list_evidence = self.session.last_evidence
        scope = Scope(name="hengli-shipbuilding-2027-neuq", expected=len(rows))
        self.result.scopes.append(scope)
        listed = self.add_page(scope, rows, set(), lambda row: row["id"])
        for row in listed:
            try:
                await self.session.open(row["url"])
                check(session.page is not None, "恒力重工职位详情未就绪")
                verify_detail(await session.page.content(), row, published)
                job = self.job(
                    row["id"],
                    title=row["title"],
                    work_type="校招",
                    source_url=row["url"],
                    unit=EMPLOYER,
                    location="辽宁省大连市长兴岛经济区",
                    requirements=row["majors"],
                    published=published,
                    field_sources={
                        "unit": "职位详情 /company/view/id/956041；恒力重工官网说明集团关系",
                        "title": "高校公告职位表逐岗详情及投递 ID",
                        "location": "2027 届校园招聘简章 工作地点",
                        "requirements": "高校职位表 需求专业",
                        "duties": "source_missing:公告未提供逐岗职责",
                        "published": "高校公告及职位详情发布时间",
                        "deadline": "source_missing:高校过期时间不是招聘截止日期",
                    },
                )
                job.evidence = [list_evidence, self.session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, row["id"])
        scope.terminal = True
