"""Risun Dingzhou's four 2027 graduate demand categories on HEBUT."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "河北旭阳能源有限公司"
HEADERS = ("职位类别", "专业要求", "学历要求", "招聘人数")
TITLES = ("化工、生工类", "机电及自动化类", "环境、材料类", "博士专家")


def compact(value: str) -> str:
    return "".join(text(value).split())


def demand(html: str) -> tuple[str, list[dict[str, str]], str]:
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(".zpxq")
    check(panel is not None, "旭阳高校公告缺失")
    assert panel is not None
    title = panel.select_one(".title")
    account = panel.select_one('.info a[href="/company/index/id/9247.html"]')
    published = panel.select_one(".info .fb")
    bodies = panel.select(".content")
    check(
        title is not None
        and "旭阳集团定州园区2027年应届生" in compact(title.get_text())
        and account is not None
        and compact(account.get_text()) == f"【{EMPLOYER}】"
        and published is not None
        and len(bodies) == 2,
        "旭阳高校公告届别、账号或版面变化",
    )
    assert published is not None
    date = re.search(r"发布时间：\s*(\d{4}-\d{2}-\d{2})", published.get_text(" ", strip=True))
    check(date is not None, "旭阳高校公告发布时间缺失")
    assert date is not None
    page = compact(bodies[1].get_text(" ", strip=True))
    check(
        "旭阳集团定州园区2027届校园招聘简章" in page
        and "拥有中国旭阳集团（01907.HK）" in page
        and "旭阳集团定州园区2027届校园招聘需求表" in page,
        "旭阳公告集团、届别或需求表边界变化",
    )
    locations = re.findall(r"【工作地点】([^【]+)", page)
    check(
        len(locations) == 1 and "河北省定州市胜利路旭阳集团定州园区" in locations[0],
        "旭阳定州园区工作地点缺失或变化",
    )
    tables = bodies[1].select("table")
    check(len(tables) == 2, "旭阳需求表或薪酬表数量变化")
    rows = tables[0].select("tr")
    check(len(rows) == 5, "旭阳需求表新增或缺失岗位行")
    cells = [
        tuple(text(cell.get_text(" ", strip=True)) for cell in row.select("th,td")) for row in rows
    ]
    check(cells[0] == HEADERS, "旭阳需求表列含义变化")
    check(
        all(len(row) == 4 for row in cells[1:])
        and tuple(row[0] for row in cells[1:]) == TITLES
        and all(row[1] and row[2] and row[3].isdigit() for row in cells[1:]),
        "旭阳需求表岗位、专业、学历或名额变化",
    )
    return (
        date[1],
        [
            {"title": row[0], "majors": row[1], "education": row[2], "headcount": row[3]}
            for row in cells[1:]
        ],
        "河北省定州市胜利路旭阳集团定州园区",
    )


class RisunDingzhouHebut2027(Adapter):
    name = "risun-dingzhou-hebut-2027"
    host = "career.hebut.edu.cn"
    path = "/correcruit/content/id/81673.html"
    scope_description = "中国旭阳集团旗下河北旭阳能源定州园区 2027 届四类岗位需求"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "旭阳高校公告未就绪")
        published, rows, location = demand(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="risun-dingzhou-hebut-2027-81673", expected=len(rows))
        self.result.scopes.append(scope)
        for item in self.add_page(scope, rows, set(), lambda row: row["title"]):
            job = self.job(
                item["title"],
                title=item["title"],
                source_url=self.source.url,
                unit=EMPLOYER,
                work_type="校招",
                location=location,
                education=item["education"],
                requirements=item["majors"],
                published=published,
                field_sources={
                    "unit": "高校账号为河北旭阳能源；集团公告列中国旭阳集团",
                    "title": "2027 届校园招聘需求表职位类别列",
                    "location": "公告【工作地点】明确为定州园区",
                    "education": "需求表学历要求列，保留原文",
                    "requirements": "需求表专业要求列",
                    "published": "高校招聘元信息发布时间",
                    "headcount": "需求表招聘人数，仅作证据不拆岗；页头总人数另为 50",
                    "duties": "source_missing:公告未列逐岗职责",
                    "deadline": "source_missing:公告未列申请截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
