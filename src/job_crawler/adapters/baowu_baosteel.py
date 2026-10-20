"""Baosteel's explicitly named 2027 roles from its HUST campus notice."""

from typing import cast

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "宝山钢铁股份有限公司"
GROUP = "中国宝武钢铁集团有限公司"
CATEGORIES = (
    ("数据AI工程师", 4),
    ("工艺工程师", 5),
    ("设备工程师", 4),
    ("市场营销/海外贸易培训生", 1),
)


def compact(value: str) -> str:
    return "".join(text(value).split())


def roster(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    page = soup.get_text(" ", strip=True)
    check(
        "中国宝武2027届" in compact(page)
        and "宝钢股份“英才”招聘计划" in page
        and EMPLOYER in page
        and GROUP in page
        and "旗舰子公司" in page,
        "宝钢高校公告主体、届别或集团关系改变",
    )
    check("2027年应届本科生、硕士研究生、博士研究生" in compact(page), "宝钢招聘对象变化")
    headings = [p for p in soup.select("p") if compact(p.get_text()) == "二、招聘岗位"]
    check(len(headings) == 1, "宝钢岗位段落边界缺失或重复")
    sections: list[Tag] = []
    for sibling in headings[0].next_siblings:
        check(isinstance(sibling, Tag) or not str(sibling).strip(), "宝钢岗位区出现未处理内容")
        if not isinstance(sibling, Tag):
            continue
        check(sibling.name == "p", "宝钢岗位区出现未处理非段落结构")
        if compact(sibling.get_text()).startswith("三、薪酬福利"):
            break
        if compact(sibling.get_text()):
            check(not sibling.select("img,table,a[href],iframe"), "宝钢岗位段落出现未处理附件")
            sections.append(sibling)
    else:
        check(False, "宝钢岗位段落终点缺失")
    values = [compact(p.get_text(" ", strip=True)) for p in sections]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    cursor = 0
    for number, (category, count) in enumerate(CATEGORIES, start=1):
        check(cursor < len(values) and values[cursor] == category, "宝钢岗位类别顺序或名称变化")
        cursor += 1
        if count > 1:
            check(cursor < len(values), "宝钢岗位清单缺失")
            titles = values[cursor].split("、")
            check(len(titles) == count and all(titles), "宝钢岗位清单数量变化")
            cursor += 1
        else:
            titles = [category]
        check(cursor + 1 < len(values), "宝钢岗位地点或专业缺失")
        location = values[cursor]
        majors = values[cursor + 1]
        check(
            location.startswith("工作地点：")
            and bool(location.removeprefix("工作地点："))
            and majors.startswith("专业：")
            and bool(majors.removeprefix("专业：")),
            "宝钢类别地点或专业对应关系变化",
        )
        cursor += 2
        for title in titles:
            check(title not in seen, "宝钢细分岗位名重复")
            seen.add(title)
            rows.append(
                {
                    "id": f"{number}:{title}",
                    "title": title,
                    "category": category,
                    "location_range": location.removeprefix("工作地点："),
                    "majors": majors.removeprefix("专业："),
                }
            )
    check(cursor == len(values) and len(rows) == 14, "宝钢公告新增未处理岗位或总数变化")
    return rows


class BaowuBaosteel2027(Adapter):
    name = "baowu-baosteel-hust-2027"
    host = "job.hust.edu.cn"
    path = "/extxjh/221790490532876.do"
    scope_description = "中国宝武旗舰子公司宝钢股份在华中科技大学2027届公告中的14个细分岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "宝钢高校公告未就绪")
        rows = roster(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="baosteel-hust-2027-roles", expected=len(rows))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["id"]):
            job = self.job(
                row["id"],
                title=row["title"],
                source_url=self.source.url,
                unit=EMPLOYER,
                work_type="校招",
                education="本科",
                requirements=row["majors"],
                field_sources={
                    "unit": "高校公告：宝钢股份为中国宝武旗舰子公司",
                    "title": f"{row['category']}类别细分岗位",
                    "education": "公告四、招聘对象：2027年应届本科、硕士、博士",
                    "requirements": f"{row['category']}类别专业要求",
                    "location": "source_missing:类别城市范围="
                    + row["location_range"]
                    + "；不能确定逐岗城市",
                    "duties": "source_missing:公告未给逐岗职责",
                    "published": "source_missing:只有宣讲时间，没有岗位发布时间",
                    "deadline": "source_missing:公告未给网申截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
