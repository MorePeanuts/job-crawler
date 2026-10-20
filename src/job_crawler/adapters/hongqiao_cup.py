"""China Hongqiao's four 2027 graduate roles on CUP's career site."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "中国宏桥集团有限公司"
HEADERS = ("岗位", "学历", "专业")
TITLES = (
    "产业研究院研发工程师",
    "青年储备干部（职能管理方向）",
    "青年储备干部（生产制造方向）",
    "数智化工程师",
)


def compact(value: str) -> str:
    return "".join(text(value).split())


def demand(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".aTitle")
    info = soup.select_one(".aInfo #pub_date")
    body = soup.select_one(".aContent")
    check(
        title is not None
        and compact(title.get_text()) == f"{EMPLOYER}2027届校园招聘"
        and info is not None
        and body is not None,
        "宏桥高校公告标题、日期或正文变化",
    )
    assert info is not None and body is not None
    date = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日\d{2}:\d{2}", compact(info.get_text()))
    check(date is not None, "宏桥高校发布时间格式变化")
    assert date is not None
    page = compact(body.get_text(" ", strip=True))
    check(
        f"{EMPLOYER}是一家" in page and "股票代码：1378.HK" in page and "一、招聘岗位：" in page,
        "宏桥公告主体、上市关系或招聘范围变化",
    )
    tables = body.select("table")
    check(len(tables) == 1, "宏桥招聘岗位表数量变化")
    rows = tables[0].select("tr")
    check(len(rows) == 5, "宏桥招聘岗位表新增或缺失行")
    cells = [
        tuple(text(cell.get_text(" ", strip=True)) for cell in row.select("th,td")) for row in rows
    ]
    check(cells[0] == HEADERS, "宏桥招聘岗位表列含义变化")
    check(
        all(len(row) == 3 and row[1] and row[2] for row in cells[1:])
        and tuple(row[0] for row in cells[1:]) == TITLES,
        "宏桥岗位名称、学历或专业变化",
    )
    published = f"{date[1]}-{int(date[2]):02d}-{int(date[3]):02d}"
    return published, [
        {"title": row[0], "education": row[1], "majors": row[2]} for row in cells[1:]
    ]


class HongqiaoCup2027(Adapter):
    name = "hongqiao-cup-2027"
    host = "career.cup.edu.cn"
    path = "/news/view/aid/95971/tag/xwzp"
    scope_description = "中国宏桥集团高校 2027 届公告的四行明确岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "宏桥高校公告未就绪")
        published, rows = demand(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="hongqiao-cup-2027-95971", expected=len(rows))
        self.result.scopes.append(scope)
        for item in self.add_page(scope, rows, set(), lambda row: row["title"]):
            job = self.job(
                item["title"],
                title=item["title"],
                source_url=self.source.url,
                unit=EMPLOYER,
                work_type="校招",
                education=item["education"],
                requirements=item["majors"],
                published=published,
                field_sources={
                    "unit": "高校公告标题及正文标明中国宏桥集团上市主体",
                    "title": "唯一招聘岗位表岗位列",
                    "education": "招聘岗位表学历列",
                    "requirements": "招聘岗位表专业列",
                    "published": "高校公告发布时间",
                    "location": "source_missing:公司地址不是逐岗工作地点",
                    "duties": "source_missing:公告未列逐岗职责",
                    "deadline": "source_missing:公告未列申请截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
