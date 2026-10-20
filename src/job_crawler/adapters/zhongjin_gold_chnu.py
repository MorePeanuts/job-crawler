"""Zhongjin Gold's 2027 recruiting rows in a university announcement."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

SMELTER = "河南中原黄金冶炼厂有限责任公司"
MATERIALS = "河南中金中原新材料有限责任公司"
INSTITUTE = "关键金属未来材料研究院"
HEADER = ("企业/单位", "岗位", "招聘人数", "学历要求", "专业要求", "联系人")


def roster(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article.articleCon")
    check(article is not None, "中原黄金高校公告主体缺失")
    assert article is not None
    heading = article.select_one("h2.title")
    property_line = article.select_one(".property")
    body = article.select_one(".conTxt")
    check(
        heading is not None
        and SMELTER + "2027年校园招聘简章" in text(heading.get_text())
        and property_line is not None
        and body is not None,
        "中原黄金高校公告标题或正文变化",
    )
    assert property_line is not None and body is not None
    published = re.search(r"发布时间：(\d{4}-\d{2}-\d{2})", property_line.get_text(" ", strip=True))
    check(published is not None, "中原黄金高校公告发布时间缺失")
    body_text = text(body.get_text(" ", strip=True))
    check(
        "上市公司中金黄金股份有限公司全资子公司" in body_text
        and f"{MATERIALS}是中原黄金冶炼厂全资子公司" in body_text,
        "中原黄金与上市公司及二级子公司关系变化",
    )
    tables = [table for table in body.select("table") if "招聘人数" in table.get_text()]
    check(len(tables) == 1, "中原黄金招聘岗位表缺失或重复")
    lines = tables[0].select("tr")
    check(len(lines) == 24, "中原黄金招聘岗位行数变化")
    check(
        tuple(text(cell.get_text()) for cell in lines[0].select("th,td")) == HEADER,
        "中原黄金招聘表表头变化",
    )
    groups = ((SMELTER, 12), (MATERIALS, 6), (INSTITUTE, 5))
    rows: list[dict[str, str]] = []
    position = 1
    for unit, count in groups:
        for group_index in range(count):
            cells = lines[position].select("th,td")
            if group_index == 0:
                check(
                    len(cells) == (5 if unit == INSTITUTE else 6)
                    and text(cells[0].get_text()) == unit
                    and str(cells[0].get("rowspan")) == str(count),
                    "中原黄金招聘单位分组变化",
                )
                values = cells[1:5]
            else:
                check(len(cells) == 4, "中原黄金招聘岗位列数变化")
                values = cells
            title, headcount, education, majors = (
                text(cell.get_text(" ", strip=True)) for cell in values
            )
            check(
                bool(title and education and majors) and headcount.isdigit() and int(headcount) > 0,
                "中原黄金招聘岗位关键字段缺失",
            )
            rows.append(
                {
                    "id": str(position),
                    "unit": unit,
                    "title": title,
                    "headcount": headcount,
                    "education": education,
                    "majors": majors,
                }
            )
            position += 1
    check(position == len(lines), "中原黄金岗位表未遍历至末尾")
    assert published is not None
    return published[1], rows


class ZhongjinGoldChnu2027(Adapter):
    name = "zhongjin-gold-chnu-2027"
    host = "yjsc.chnu.edu.cn"
    path = "/yjsjy/content_153035"
    scope_description = "淮北师大 2027 简章中中金黄金所属冶炼厂及其全资子公司招聘表"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "中原黄金高校公告未就绪")
        published, rows = roster(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="zhongjin-gold-chnu-153035", expected=len(rows))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["id"]):
            if row["unit"] == INSTITUTE:
                scope.skipped_out_of_scope += 1
                continue
            job = self.job(
                row["id"],
                title=row["title"],
                source_url=self.source.url,
                unit=row["unit"],
                work_type="校招",
                education=row["education"],
                requirements=row["majors"],
                published=published,
                field_sources={
                    "unit": "高校公告前两组招聘单位；正文确认中金黄金全资及二级全资关系",
                    "title": "招聘表岗位列；重复岗位以招聘单位+行序识别",
                    "education": "招聘表学历要求列",
                    "requirements": "招聘表专业要求列",
                    "headcount": f"招聘表人数={row['headcount']}；不按人数拆岗",
                    "published": "高校公告发布时间；不是逐岗发布时间",
                    "location": "source_missing:通讯地址不是逐岗工作地点",
                    "duties": "source_missing:公告未给逐岗职责",
                    "deadline": "source_missing:公告未给投递截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
