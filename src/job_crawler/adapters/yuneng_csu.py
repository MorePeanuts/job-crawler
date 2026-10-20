"""湖南裕能在中南大学 2027 届双选会公开展位表的岗位。"""

import re
from typing import cast

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "湖南裕能新能源电池材料股份有限公司"
CREDIT_CODE = "91430300MA4L54TU10"
PATH = "/largefairs/company/id/1312/sid/104/stype/1"


def row_id(row: Tag) -> str:
    anchor = row.select_one(".apply_job[data-id]")
    check(anchor is not None, "湖南裕能岗位申请 ID 缺失")
    assert anchor is not None
    return text(str(anchor["data-id"]))


def roster(html: str, employer: str = EMPLOYER, credit_code: str = CREDIT_CODE) -> list[Tag]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("h1")
    table = soup.select_one("#lTable")
    check(title is not None and "2027届" in text(title.get_text()), "中南大学双选会届别改变")
    check(table is not None, "湖南裕能中南大学展位表缺失")
    assert table is not None
    cells = [text(cell.get_text(" ", strip=True)) for cell in table.select("tr td")]
    check(
        "单位全称" in cells
        and employer in cells
        and "统一社会信用代码" in cells
        and credit_code in cells,
        "湖南裕能中南大学展位主体改变",
    )
    check("招聘内容" in cells, "湖南裕能中南大学招聘内容缺失")
    check(not soup.select(".pagination, .pages, .page"), "湖南裕能展位表出现分页")
    rows = [tr for tr in table.select("tr") if tr.select_one(".apply_job[data-id]")]
    check(bool(rows), "湖南裕能展位表未证明有公开岗位或明确零岗位")
    ids = [row_id(row) for row in rows]
    check(all(re.fullmatch(r"\d+", key) for key in ids), "湖南裕能岗位申请 ID 无效")
    check(len(set(ids)) == len(ids), "湖南裕能岗位申请 ID 重复")
    return rows


def job_row(row: Tag) -> dict[str, str]:
    anchor = row.select_one(".apply_job[data-id]")
    cells = [text(cell.get_text(" ", strip=True)) for cell in row.select("td")]
    check(anchor is not None and len(cells) == 7, "湖南裕能岗位行结构改变")
    assert anchor is not None
    check(
        bool(cells[0]) and bool(cells[1]) and cells[4] in {"本科", "硕士", "博士"},
        "湖南裕能岗位字段缺失",
    )
    check(cells[2].isdigit() and int(cells[2]) > 0, "湖南裕能招聘人数无效")
    check(cells[5] == "全职", "湖南裕能双选会混入非全职岗位")
    return {
        "id": row_id(row),
        "title": cells[0],
        "majors": cells[1],
        "headcount": cells[2],
        "education": cells[4],
    }


class CsuFair2027(Adapter):
    host = "career.csu.edu.cn"
    employer = ""
    credit_code = ""
    fair_sid = ""
    scope_description = "中南大学 2027 届秋季第二场双选会企业展位公开全职岗位行"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "中南大学企业展位页未就绪")
        rows = roster(await session.page.content(), self.employer, self.credit_code)
        evidence = self.session.last_evidence
        scope = Scope(name=f"csu-largefair-1312-{self.fair_sid}", expected=len(rows))
        scope.evidence.append(evidence)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        by_id = {row_id(row): row for row in rows}
        listed = self.add_page(
            scope, [{"id": key} for key in by_id], seen, lambda item: str(item["id"])
        )
        for listed_row in listed:
            key = str(listed_row["id"])
            try:
                data = job_row(by_id[key])
                job = self.job(
                    data["id"],
                    title=data["title"],
                    work_type="校招",
                    source_url=self.source.url,
                    unit=self.employer,
                    education=data["education"],
                    requirements=data["majors"],
                    field_sources={
                        "unit": "中南大学双选会展位表 单位全称及统一社会信用代码",
                        "title": f"展位表 申请 ID={data['id']}",
                        "education": "展位表 学历",
                        "requirements": "展位表 专业",
                        "headcount": f"展位表 数量={data['headcount']}；不按人数拆分",
                        "duties": "source_missing:展位表未提供逐岗职责",
                        "location": "source_missing:展位表未提供逐岗工作地点",
                        "published": "source_missing:活动时间不是岗位发布时间",
                        "deadline": "source_missing:活动时间不是岗位截止日期",
                    },
                )
                job.evidence = [evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True


class YunengCsu2027(CsuFair2027):
    name = "yuneng-csu-2027"
    path = PATH
    employer = EMPLOYER
    credit_code = CREDIT_CODE
    fair_sid = "104"


class ZhongjinlingnanCsu2027(CsuFair2027):
    name = "zhongjinlingnan-csu-2027"
    path = "/largefairs/company/id/1312/sid/320/stype/1"
    employer = "深圳市中金岭南有色金属股份有限公司"
    credit_code = "914403001922063360"
    fair_sid = "320"


class ShagangCsu2027(CsuFair2027):
    name = "shagang-csu-2027"
    path = "/largefairs/company/id/1312/sid/361/stype/1"
    employer = "江苏沙钢集团有限公司"
    credit_code = "91320582134789270G"
    fair_sid = "361"
