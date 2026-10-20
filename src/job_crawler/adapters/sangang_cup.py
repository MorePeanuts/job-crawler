"""三钢集团 2027 届公告中的上市公司三明中心岗位代码。"""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "福建三钢闽光股份有限公司"
UNIT = "三明闽光生产运营中心"
CODE = re.compile(r"(?:SG|XCL)-[A-Z]+-[A-Z0-9]+")
DATE = re.compile(r"发布时间：\s*(2026)年(\d{1,2})月(\d{1,2})日")


def roster(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    check(
        "福建省三钢（集团）有限责任公司2027年专业技术人员招聘" in page_text, "三钢2027公告标题改变"
    )
    check("2027届专业技术岗高校毕业生招聘计划汇总表" in page_text, "三钢当届招聘计划缺失")
    date_match = DATE.search(page_text)
    check(date_match is not None, "三钢招聘公告发布时间缺失")
    assert date_match is not None
    published = (
        f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    )
    tables = [table for table in soup.select("table") if "岗位代码" in table.get_text()]
    check(len(tables) == 1, "三钢招聘计划表缺失或重复")
    table = tables[0]
    rows = table.select("tr")
    check(len(rows) == 49, "三钢招聘计划 47 行范围改变")
    first = rows[2].find_all(["td", "th"], recursive=False)
    check(
        len(first) == 8
        and text(first[1].get_text()) == EMPLOYER
        and first[1].get("rowspan") == "28"
        and text(first[2].get_text()) == UNIT
        and first[2].get("rowspan") == "10"
        and text(first[6].get_text()) == "大学本科及以上"
        and text(first[7].get_text()) == "福建三明",
        "三钢上市公司及三明中心合并单元格边界改变",
    )
    all_codes: set[str] = set()
    result: list[dict[str, str]] = []
    for index, row in enumerate(rows[2:], start=1):
        cells = [
            text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["td", "th"], recursive=False)
        ]
        check(bool(cells) and cells[0] == str(index), "三钢招聘计划行序号不连续")
        matched = [(i, value) for i, value in enumerate(cells) if CODE.fullmatch(value)]
        check(len(matched) == 1, "三钢招聘计划岗位代码缺失或重复")
        code_index, code = matched[0]
        check(code not in all_codes, "三钢招聘计划出现重复岗位代码")
        all_codes.add(code)
        check(code_index >= 1 and code_index + 1 < len(cells), "三钢招聘人数或专业字段缺失")
        count = cells[code_index - 1]
        major = cells[code_index + 1]
        check(count.isdigit() and int(count) > 0 and bool(major), "三钢招聘人数或专业无效")
        included = index <= 10
        if included:
            check(code == f"SG-SM-{index:02d}", "三钢三明中心岗位代码连续性变化")
        result.append(
            {
                "id": code,
                "major": major,
                "count": count,
                "included": "1" if included else "0",
            }
        )
    check(len(all_codes) == 47, "三钢招聘计划代码总数变化")
    return published, result


class SangangMingguang2027(Adapter):
    name = "sangang-mingguang-cup-2027"
    host = "career.cup.edu.cn"
    path = "/news/view/aid/95956/tag/xwzp"
    scope_description = (
        "三钢集团2027公告47行完整计划，仅保留上市公司三明闽光生产运营中心10个岗位代码"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "三钢高校招聘公告未就绪")
        published, rows = roster(await session.page.content())
        evidence = self.session.last_evidence
        scope = Scope(name="sangang-2027-plan", expected=len(rows))
        self.result.scopes.append(scope)
        listed = self.add_page(scope, rows, set(), lambda row: row["id"])
        for row in listed:
            if row["included"] != "1":
                scope.skipped_out_of_scope += 1
                continue
            job = self.job(
                row["id"],
                title="2027届专业技术岗",
                work_type="校招",
                source_url=self.source.url,
                unit=UNIT,
                location="福建三明",
                education="本科",
                requirements=row["major"],
                published=published,
                field_sources={
                    "unit": "招聘计划表 招聘单位及下属企业合并单元格",
                    "title": f"招聘计划表标题及岗位代码 {row['id']}",
                    "education": "招聘计划表 大学本科及以上",
                    "requirements": "招聘计划表 专业要求",
                    "published": "招聘公告发布时间；同一计划的发布时间",
                    "duties": "source_missing:公告未列逐岗职责",
                    "deadline": "source_missing:公告未列招聘截止日期",
                    "headcount": f"招聘计划表 招聘人数={row['count']}；不按人数拆分",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
