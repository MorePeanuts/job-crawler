"""Seven named roles of China Railway Engineering's Zhongtie Jianggong branch."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "中铁建工集团第二建设有限公司"
HEADINGS = (
    "2.中铁建工集团第二建设有限公司（青岛）",
    "3.中铁建工集团第三建设有限公司（天津）",
)
ROLES = (
    "土建技术岗",
    "商务预算岗",
    "安装技术岗",
    "安全管理岗",
    "综合管理岗",
    "财务管理岗",
    "法律合规岗",
)


def compact(value: str) -> str:
    return "".join(text(value).split())


def roster(html: str) -> tuple[str, list[str], str]:
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(".zpxq")
    check(panel is not None, "中铁建工高校公告缺失")
    assert panel is not None
    title = panel.select_one(".title")
    account = panel.select_one('.info a[href="/company/index/id/3801.html"]')
    published = panel.select_one(".info .fb")
    bodies = panel.select(".content")
    check(
        title is not None
        and "中国中铁建工集团有限公司2027届校园招聘简章" in compact(title.get_text())
        and account is not None
        and text(account.get_text()) == "【中铁建工集团山东有限公司】"
        and published is not None
        and len(bodies) == 2,
        "中铁建工公告届别、账号或版面变化",
    )
    assert published is not None
    date = re.search(r"发布时间：\s*(\d{4}-\d{2}-\d{2})", published.get_text(" ", strip=True))
    check(date is not None, "中铁建工公告发布时间缺失")
    assert date is not None
    paragraphs = [
        compact(p.get_text(" ", strip=True)) for p in bodies[1].find_all("p", recursive=False)
    ]
    check(
        "中铁建工集团有限公司（简称“中铁建工”）是世界500强——中国中铁股份有限公司的全资子公司"
        in compact(bodies[1].get_text()),
        "中铁建工与中国中铁主体关系变化",
    )
    starts = [i for i, value in enumerate(paragraphs) if value == HEADINGS[0]]
    ends = [i for i, value in enumerate(paragraphs) if value == HEADINGS[1]]
    check(
        len(starts) == 1 and len(ends) == 1 and ends[0] == starts[0] + 4,
        "中铁建工二公司单位边界变化",
    )
    start = starts[0]
    check(
        paragraphs[start - 1].startswith("（3）简历投递方式：")
        and paragraphs[start + 1].startswith("（1）工作地点：")
        and paragraphs[start + 3].startswith("（3）简历投递方式："),
        "中铁建工二公司地点或投递边界变化",
    )
    role_line = paragraphs[start + 2]
    check(role_line.startswith("（2）招聘岗位："), "中铁建工二公司岗位行缺失")
    titles = role_line.removeprefix("（2）招聘岗位：").split("、")
    check(tuple(titles) == ROLES, "中铁建工二公司岗位名称或总数变化")
    return date[1], titles, paragraphs[start + 1].removeprefix("（1）工作地点：")


class CrecgZhongtieJianggong2027(Adapter):
    name = "crecg-zhongtiejianggong-hebut-2027"
    host = "career.hebut.edu.cn"
    path = "/correcruit/content/id/80900.html"
    scope_description = "中国铁路工程集团旗下中铁建工二公司河北工大 2027 届公告的七个明确岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "中铁建工高校公告未就绪")
        published, titles, location_range = roster(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="crecg-zhongtiejianggong-hebut-2027-80900", expected=len(titles))
        self.result.scopes.append(scope)
        for title in self.add_page(
            scope, [{"title": item} for item in titles], set(), lambda item: item["title"]
        ):
            job = self.job(
                title["title"],
                title=title["title"],
                source_url=self.source.url,
                unit=EMPLOYER,
                work_type="校招",
                education="本科",
                published=published,
                field_sources={
                    "unit": "二、分子公司相关信息第 2 单位；中国中铁为中铁工控股企业",
                    "title": "第 2 单位（2）招聘岗位逐项列示",
                    "education": "高校招聘元信息学历要求本科",
                    "published": "高校招聘元信息发布时间",
                    "location": "source_missing:二公司城市范围="
                    + location_range
                    + "；不能确定单岗地点",
                    "duties": "source_missing:公告未给逐岗职责",
                    "requirements": "source_missing:公告未给逐岗专业要求",
                    "deadline": "source_missing:公告未给截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
