"""Rongsheng Holding's six named 2027 campus roles on HEBUT."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

COMPANY = "浙江荣盛控股集团有限公司"
GROUPS = ("集团总部", "商务板块", "炼化板块", "创新中心")
PUBLISHED = re.compile(r"发布时间：\s*(\d{4}-\d{2}-\d{2})")
LINE = re.compile(r"^([^（]+)（([^）]+)）：(.+)$")


def split_roles(value: str) -> list[str]:
    roles: list[str] = []
    depth = 0
    buffer = ""
    for character in value:
        if character == "（":
            depth += 1
        elif character == "）":
            depth -= 1
            check(depth >= 0, "荣盛岗位括号未配对")
        if character == "、" and depth == 0:
            roles.append(buffer)
            buffer = ""
        else:
            buffer += character
    roles.append(buffer)
    check(depth == 0 and all(roles), "荣盛岗位清单为空或括号未配对")
    return roles


def roster(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    headline = soup.select_one(".zhaopinxx_con1 .p1")
    employer = soup.select_one(".zhaopinxx_con1 .p2")
    date = soup.select_one(".zhaopinxx_con1 .p3")
    check(
        headline is not None
        and text(headline.get_text()) == "荣盛集团2027届全球校园招聘正式启动"
        and employer is not None
        and text(employer.get_text()) == COMPANY
        and date is not None,
        "荣盛高校公告主体、标题或发布日期缺失",
    )
    assert date is not None
    date_match = PUBLISHED.search(date.get_text(" ", strip=True))
    check(date_match is not None, "荣盛公告发布时间缺失")
    assert date_match is not None
    descriptions = [
        node
        for node in soup.select(".zhaopinxx_con2_con")
        if "荣盛集团2027届校园招聘" in node.get_text()
    ]
    check(len(descriptions) == 1, "荣盛招聘正文缺失或重复")
    description = descriptions[0]
    paragraphs = [
        text(p.get_text(" ", strip=True)) for p in description.find_all("p", recursive=False)
    ]
    check(
        len(paragraphs) >= 9
        and paragraphs[0] == "荣盛集团2027届校园招聘"
        and paragraphs[1] == "一、【专业大类】"
        and paragraphs[3] == "二、【招聘岗位】"
        and paragraphs[8] == "三、【网申链接】",
        "荣盛招聘正文边界或届别变化",
    )
    majors = paragraphs[2]
    check(bool(majors), "荣盛专业大类缺失")
    poster = description.select_one('a[title="易拉宝.png"]')
    check(
        poster is not None and poster.get("href") == "/Upload/file/20261008/1791423919814812.png",
        "荣盛公告海报附件变化，须复核范围",
    )
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, (group, value) in enumerate(zip(GROUPS, paragraphs[4:8], strict=True), start=1):
        matched = LINE.fullmatch(value)
        check(matched is not None and matched[1] == group, "荣盛板块岗位或地点格式变化")
        assert matched is not None
        for title in split_roles(matched[3]):
            check(title not in seen, "荣盛公告岗位名重复")
            seen.add(title)
            result.append(
                {
                    "id": f"{index}:{title}",
                    "title": title,
                    "unit": group,
                    "location": matched[2],
                    "majors": majors,
                }
            )
    check(len(result) == 6, "荣盛公告细分岗位总数变化")
    return date_match[1], result


class RongshengHebut2027(Adapter):
    name = "rongsheng-hebut-2027"
    host = "career.hebut.edu.cn"
    path = "/home/correcruit/content/id/81697.html"
    scope_description = "荣盛控股河北工业大学2027届简章四个板块的六个明确岗位；海报职类不额外计数"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "荣盛高校公告未就绪")
        published, rows = roster(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="rongsheng-hebut-2027-81697", expected=len(rows))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["id"]):
            job = self.job(
                row["id"],
                title=row["title"],
                source_url=self.source.url,
                unit=row["unit"],
                location=row["location"],
                work_type="校招",
                education="本科",
                requirements="公告专业大类：" + row["majors"],
                published=published,
                field_sources={
                    "unit": "招聘正文逐行板块；公司账号为浙江荣盛控股集团",
                    "title": "二、招聘岗位逐行岗位名；管培生括号方向为同一岗",
                    "location": "二、招聘岗位各板块括号内工作地域",
                    "education": "高校岗位元数据：学历要求本科",
                    "requirements": "公告整体专业大类，未映射逐岗专业",
                    "published": "高校招聘信息发布时间",
                    "duties": "source_missing:公告未列逐岗职责",
                    "deadline": "source_missing:公告未列网申截止日期",
                    "headcount": "公告整体招聘人数 50；不分摊到岗位",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
