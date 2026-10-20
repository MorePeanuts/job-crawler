"""Conch New Materials' two named 2027 graduate demand rows."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "海螺（安徽）节能环保新材料股份有限公司"
HEADERS = ("招聘岗位", "专业类别", "招聘人数")


def compact(value: str) -> str:
    return "".join(text(value).split())


def demand(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".news_detail_title")
    body = soup.select_one(".v_news_content")
    check(
        title is not None
        and "安徽海螺集团有限责任公司2027届校园招聘简章" in compact(title.get_text())
        and body is not None,
        "海螺高校公告标题或正文变化",
    )
    assert body is not None
    page = compact(body.get_text(" ", strip=True))
    check(
        "控股经营海螺水泥、海螺新材" in page and EMPLOYER in page and "（一）招聘岗位" in page,
        "海螺新材主体关系或需求段落变化",
    )
    date_nodes = soup.select(".news_detail")
    check(len(date_nodes) == 1, "海螺高校公告日期容器变化")
    dates = re.findall(r"日期：\s*(\d{4}-\d{2}-\d{2})", date_nodes[0].get_text(" ", strip=True))
    check(len(dates) == 1, "海螺高校公告发布时间缺失或重复")
    tables = body.select("table")
    check(len(tables) == 1, "海螺岗位需求表数量变化")
    rows = tables[0].select("tr")
    check(len(rows) == 3, "海螺岗位需求表新增或缺失行")
    cells = [
        tuple(text(cell.get_text(" ", strip=True)) for cell in row.select("th,td")) for row in rows
    ]
    check(cells[0] == HEADERS, "海螺岗位需求表列含义变化")
    check(
        len(cells[1]) == len(cells[2]) == 3
        and tuple(row[0] for row in cells[1:]) == ("财务类", "语言类")
        and all(row[1] and row[2] == "若干" for row in cells[1:]),
        "海螺岗位、专业或名额变化",
    )
    return dates[0], [{"title": row[0], "majors": row[1], "headcount": row[2]} for row in cells[1:]]


class ConchNewMaterialsAhnu2027(Adapter):
    name = "conch-new-materials-ahnu-2027"
    host = "career.ahnu.edu.cn"
    path = "/info/1008/36382.htm"
    scope_description = "海螺集团控股海螺新材在安徽师大 2027 届公告中的两条岗位需求"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "海螺高校公告未就绪")
        published, rows = demand(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="conch-ahnu-2027-36382", expected=len(rows))
        self.result.scopes.append(scope)
        for item in self.add_page(scope, rows, set(), lambda row: row["title"]):
            job = self.job(
                item["title"],
                title=item["title"],
                source_url=self.source.url,
                unit=EMPLOYER,
                work_type="校招",
                requirements=item["majors"],
                published=published,
                field_sources={
                    "unit": "公告正文：集团控股海螺新材；岗位需求主体为海螺新材",
                    "title": "唯一招聘需求表岗位列",
                    "requirements": "需求表专业类别列",
                    "published": "高校公告日期",
                    "headcount": "需求表人数为若干，不拆成岗位",
                    "location": "source_missing:公司联系地址不是逐岗工作地点",
                    "education": "source_missing:公告未列逐岗学历",
                    "duties": "source_missing:公告未列逐岗职责",
                    "deadline": "source_missing:公告未列申请截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
