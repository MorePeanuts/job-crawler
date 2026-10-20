"""Satellite Group's 2027 graduate demand table at HUST."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "卫星化学股份有限公司"
HEADERS = ("岗位", "专业", "学历", "人数")
TITLES = (
    "大宗交易研究员",
    "生产工艺工程师",
    "研发工程师",
    "设备工程师",
    "仪表工程师",
    "电气工程师",
    "公用工程工程师",
    "储运工程师",
    "化验工程师",
    "实验工程师",
    "质量管理工程师",
    "销售业务经理",
    "外贸业务经理",
    "应用技术工程师",
    "采购专员",
    "财务专员",
    "法务专员",
    "人力资源专员",
    "信息技术专员",
)


def compact(value: str) -> str:
    return "".join(text(value).split())


def demand(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".nyrtit .tit")
    info = soup.select_one(".nyrtit .time")
    body = soup.select_one(".arc-con .content")
    check(
        title is not None
        and compact(title.get_text()) == "卫星集团2027届校园招聘简章"
        and info is not None
        and body is not None,
        "卫星集团高校公告标题或版面变化",
    )
    assert info is not None and body is not None
    date = re.fullmatch(r"发布时间：(\d{4}-\d{2}-\d{2})", compact(info.get_text()))
    check(date is not None, "卫星集团高校发布时间变化")
    assert date is not None
    page = compact(body.get_text(" ", strip=True))
    check(
        "卫星集团2027届校园招聘简章" in page
        and "卫星化学创立于1992年" in page
        and "招聘岗位：" in page
        and "网申通道：关注“卫星招聘”微信公众号-校园招聘-应届生-招聘职位-投递简历" in page,
        "卫星集团招聘主体、届别或申请状态变化",
    )
    tables = body.select("table")
    check(len(tables) == 3, "卫星集团招聘、薪酬或高校附表数量变化")
    rows = tables[0].select("tr")
    check(len(rows) == 21, "卫星集团主招聘表新增或缺失行")
    cells = [
        tuple(compact(cell.get_text(" ", strip=True)) for cell in row.select("th,td"))
        for row in rows
    ]
    check(cells[0] == HEADERS and cells[-1] == ("合计", "401"), "卫星集团表头或合计变化")
    check(
        tuple(row[0] for row in cells[1:-1]) == TITLES
        and all(len(row) == 4 and row[1] and row[2] and row[3].isdigit() for row in cells[1:-1])
        and sum(int(row[3]) for row in cells[1:-1]) == 401,
        "卫星集团岗位、专业、学历或招聘人数变化",
    )
    return date[1], [
        {"title": row[0], "majors": row[1], "education": row[2], "headcount": row[3]}
        for row in cells[1:-1]
    ]


class SatelliteHust2027(Adapter):
    name = "satellite-hust-2027"
    host = "job.hust.edu.cn"
    path = "/zpinfo1/2409250.htm"
    scope_description = "浙江卫星控股旗下卫星化学 2027 届高校公告首张完整招聘表 19 岗"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "卫星集团高校公告未就绪")
        published, rows = demand(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="satellite-hust-2027-2409250", expected=len(rows))
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
                    "unit": "高校公告主体卫星化学；卫星控股官网和半年报核对母子关系",
                    "title": "首张招聘岗位表岗位列；部分重复附表排除",
                    "education": "首张招聘岗位表学历列原文",
                    "requirements": "首张招聘岗位表专业列",
                    "published": "高校公告发布时间",
                    "headcount": f"首表逐岗人数={item['headcount']}，19 岗合计 401 名额",
                    "location": "source_missing:公告只有统一多地范围，未关联逐岗地点",
                    "duties": "source_missing:公告未列逐岗职责",
                    "deadline": "source_missing:公告未列申请截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
