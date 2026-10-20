"""Hualing Cable's single 2027 graduate demand row on HUST."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "湖南华菱线缆股份有限公司"
HEADERS = ("需求岗位", "需求人数", "需求学历", "需求专业", "其他要求")


def compact(value: str) -> str:
    return "".join(text(value).split())


def demand(html: str) -> tuple[str, dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    page = compact(soup.get_text(" ", strip=True))
    check(
        f"{EMPLOYER}2027届校园招聘简章" in page
        and "为世界五百强湖南钢铁集团子公司" in page
        and "招聘对象：2027届本科、硕士、博士应届毕业生" in page,
        "华菱线缆公告主体、集团关系或届别变化",
    )
    dates = re.findall(r"发布时间：(\d{4}-\d{2}-\d{2})", page)
    check(len(dates) == 1, "华菱线缆高校发布时间缺失或重复")
    tables = [
        table
        for table in soup.select("table")
        if compact(table.get_text(" ", strip=True)).startswith(
            "需求岗位需求人数需求学历需求专业其他要求"
        )
    ]
    check(len(tables) == 1, "华菱线缆岗位需求表缺失或重复")
    rows = tables[0].select("tr")
    check(len(rows) == 2, "华菱线缆岗位需求表新增或缺失行")
    header = tuple(compact(cell.get_text()) for cell in rows[0].select("th,td"))
    data = tuple(text(cell.get_text(" ", strip=True)) for cell in rows[1].select("th,td"))
    check(header == HEADERS and len(data) == 5, "华菱线缆需求表列结构变化")
    check(
        data[0] == "技术/管理储备"
        and data[1] == "26"
        and data[2] == "本科"
        and bool(data[3])
        and not data[4],
        "华菱线缆岗位、人数或学历变化",
    )
    return dates[0], {
        "title": data[0],
        "headcount": data[1],
        "education": data[2],
        "majors": data[3],
    }


class HunansteelHualingCable2027(Adapter):
    name = "hunansteel-hualing-cable-hust-2027"
    host = "job.hust.edu.cn"
    path = "/zpinfo1/2318768.htm"
    scope_description = "湖南钢铁集团子公司华菱线缆 2027 届简章唯一岗位需求表行"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "华菱线缆高校公告未就绪")
        published, row = demand(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="hualing-cable-hust-2027-2318768", expected=1)
        self.result.scopes.append(scope)
        for item in self.add_page(scope, [row], set(), lambda value: value["title"]):
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
                    "unit": "公告称华菱线缆为湖南钢铁集团子公司",
                    "title": "唯一岗位需求表行；正文三个方向不拆岗",
                    "education": "需求学历列",
                    "requirements": "需求专业列",
                    "published": "高校招聘信息发布时间",
                    "headcount": "唯一岗位需求表需求人数=26",
                    "location": "source_missing:公司地址不是岗位工作地点",
                    "duties": "source_missing:公告未列逐岗职责",
                    "deadline": "source_missing:公告未列申请截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
