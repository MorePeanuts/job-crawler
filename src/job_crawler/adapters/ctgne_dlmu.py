"""三峡能源辽宁分公司在大连海事大学 2027 届公告中的职位。"""

import re
from typing import cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ROOT = "https://myjob.dlmu.edu.cn"
EMPLOYER = "中国三峡新能源（集团）股份有限公司辽宁分公司"
NOTICE_ID = "869349"
DETAIL = re.compile(r"/job/view/id/(\d+)/from_type/4/from_id/869349")


def roster(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.get_text(" ", strip=True)
    check(
        "中国三峡新能源（集团）股份有限公司2027年秋季校园招聘公告" in body,
        "三峡能源 2027 届公告缺失",
    )
    employer = soup.select_one('a[href="/company/view/id/940413"]')
    check(
        employer is not None and text(employer.get_text()) == EMPLOYER, "三峡能源高校账号主体改变"
    )
    check(not soup.select(".pagination, .pages, .page"), "三峡能源高校职位列表出现分页")
    tables = [table for table in soup.select("table") if table.select("a.apply_job[data-id]")]
    check(len(tables) == 1, "三峡能源高校职位表缺失或重复")
    rows = tables[0].select("tr")
    check(len(rows) >= 2, "三峡能源高校职位表未证明公开岗位")
    check("序号" in rows[0].get_text() and "职位信息" in rows[0].get_text(), "三峡能源表头改变")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows[1:], start=1):
        cells = row.find_all("td", recursive=False)
        check(
            len(cells) == 4 and text(cells[0].get_text()) == f"{index:02d}",
            "三峡能源岗位行结构改变",
        )
        link = cells[1].select_one('a[href*="/job/view/id/"]')
        apply = cells[3].select_one("a.apply_job[data-id]")
        check(link is not None and apply is not None, "三峡能源详情链接或申请 ID 缺失")
        assert link is not None and apply is not None
        url = urljoin(ROOT, str(link["href"]))
        matched = DETAIL.fullmatch(urlsplit(url).path)
        check(
            matched is not None and matched.group(1) == text(apply["data-id"]),
            "三峡能源岗位链接与申请 ID 不一致",
        )
        assert matched is not None
        key = matched.group(1)
        check(key not in seen, "三峡能源岗位申请 ID 重复")
        seen.add(key)
        facts = [text(li.get_text(" ", strip=True)) for li in cells[1].select("li")]
        check(len(facts) >= 4 and facts[2] == "全职", "三峡能源高校岗位性质或字段改变")
        title = text(link.get_text(" ", strip=True))
        majors = text(cells[2].get_text(" ", strip=True))
        check(bool(title) and bool(majors), "三峡能源岗位标题或专业缺失")
        result.append(
            {
                "id": key,
                "title": title,
                "url": url,
                "location": facts[1],
                "education": facts[3],
                "majors": majors,
            }
        )
    return result


def verify_detail(html: str, row: dict[str, str]) -> None:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("span.title[title]")
    employer = soup.select_one('a[href="/company/view/id/940413"]')
    body = soup.get_text(" ", strip=True)
    check(title is not None and text(title.get_text()) == row["title"], "三峡能源详情标题不匹配")
    check(employer is not None and text(employer.get_text()) == EMPLOYER, "三峡能源详情主体不匹配")
    check(
        row["location"] in body and "全职" in body and row["education"] in body,
        "三峡能源详情地点、性质或学历改变",
    )


class CtgneLiaoningDlmu2027(Adapter):
    name = "ctgne-liaoning-dlmu-2027"
    host = "myjob.dlmu.edu.cn"
    path = "/campus/view/id/869349"
    scope_description = "三峡能源辽宁分公司在大连海事大学 2027 届公告的完整职位列表"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "三峡能源高校公告未就绪")
        rows = roster(await session.page.content())
        list_evidence = self.session.last_evidence
        scope = Scope(name=f"ctgne-dlmu-{NOTICE_ID}", expected=len(rows))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["id"]):
            try:
                await self.session.open(row["url"])
                check(session.page is not None, "三峡能源岗位详情未就绪")
                verify_detail(await session.page.content(), row)
                job = self.job(
                    row["id"],
                    title=row["title"],
                    work_type="校招",
                    source_url=row["url"],
                    unit=EMPLOYER,
                    location=row["location"],
                    education=row["education"],
                    requirements=row["majors"],
                    field_sources={
                        "unit": "高校公告及详情分公司账号",
                        "title": "高校公告职位表及详情申请 ID",
                        "location": "高校公告职位表及详情",
                        "education": "高校公告职位表及详情",
                        "requirements": "高校公告职位表需求专业",
                        "duties": "source_missing:详情未提供岗位职责",
                        "published": "source_missing:公告发布时间不是岗位发布时间",
                        "deadline": "source_missing:公告过期时间不是岗位截止日期",
                    },
                )
                job.evidence = [list_evidence, self.session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, row["id"])
        scope.terminal = True
