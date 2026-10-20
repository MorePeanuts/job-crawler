"""Country Garden Services' two immediate-signing 2027 campus roles."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

TITLES = ("项目管理岗（管楼盘物业）", "生活服务岗（做经营服务）")


def compact(value: str) -> str:
    return "".join(text(value).split())


def demand(html: str) -> tuple[str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".aTitle")
    info = soup.select_one(".aInfo")
    body = soup.select_one(".aContent")
    check(
        title is not None
        and compact(title.get_text()) == "【碧桂园服务集团2027届校园招聘】"
        and info is not None
        and body is not None,
        "碧桂园服务高校公告标题或正文变化",
    )
    assert info is not None and body is not None
    date = re.search(r"发布时间：(\d{4})年(\d{2})月(\d{2})日\d{2}:\d{2}", compact(info.get_text()))
    check(date is not None, "碧桂园服务高校公告发布时间缺失")
    assert date is not None
    page = compact(body.get_text(" ", strip=True))
    check(
        page.count("一、招聘岗位：") == 1
        and page.count("二、相关要求：") == 1
        and "2027届本科及以上学历毕业生" in page
        and "三、工作地点：惠州市。" in page
        and "终面通过即签约，现在投递，现在可安排面试" in page,
        "碧桂园服务届别、地点、签约状态或岗位边界变化",
    )
    section = page.split("一、招聘岗位：", 1)[1].split("二、相关要求：", 1)[0]
    matches = re.findall(r"([1-9])、([^0-9]+?)(?=(?:[1-9]、|（以上均为|$))", section)
    check(
        matches == [("1", TITLES[0]), ("2", TITLES[1])]
        and section.endswith("（以上均为非销售岗位）"),
        "碧桂园服务招聘条目增加、缺失或性质变化",
    )
    return f"{date[1]}-{date[2]}-{date[3]}", list(TITLES)


class BgyfwXasyxy2027(Adapter):
    name = "bgyfw-xasyxy-2027"
    host = "job.xasyxy.com"
    path = "/news/view/aid/408964/tag/tzgg"
    scope_description = "碧桂园服务西安思源学院 2027 届惠州两岗，即时面试签约公告"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "碧桂园服务高校公告未就绪")
        published, titles = demand(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="bgyfw-xasyxy-2027-408964", expected=len(titles))
        self.result.scopes.append(scope)
        rows = [{"title": title} for title in titles]
        for item in self.add_page(scope, rows, set(), lambda row: row["title"]):
            job = self.job(
                item["title"],
                title=item["title"],
                source_url=self.source.url,
                unit="碧桂园服务集团",
                work_type="校招",
                location="惠州市",
                education="本科及以上",
                requirements="经管类、社会工作、景观园林、工程管理等相关专业优先",
                published=published,
                field_sources={
                    "unit": "高校公告以碧桂园服务集团品牌发布，名录主体为碧桂园服务控股",
                    "title": "一、招聘岗位两条原文；括号解释保留在标题内",
                    "location": "三、工作地点统一写惠州市",
                    "education": "二、相关要求统一写2027届本科及以上",
                    "requirements": "二、相关要求统一列优先专业",
                    "published": "高校发布时间",
                    "duties": "source_missing:公告未逐岗列出职责",
                    "deadline": "source_missing:公告称现在投递，未列截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
