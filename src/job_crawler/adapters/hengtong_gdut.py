"""Seven linked Hengtong 2027 graduate vacancies at GDUT."""

import re
from typing import cast
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "亨通集团有限公司"
TITLES = (
    "生产计划",
    "生产储备",
    "连接器工艺工程师",
    "光器件研发工程师",
    "质量工程师",
    "客户经理",
    "采购专员",
)


def compact(value: str) -> str:
    return "".join(text(value).split())


def listing(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".details-mge .aContent")
    tables = soup.select(".details-table .css-table table")
    check(body is not None and len(tables) == 1, "亨通高校公告或关联职位表缺失")
    assert body is not None
    page = compact(body.get_text(" ", strip=True))
    check(
        "亨通集团2027届校园招聘简章" in page
        and "亨通集团，是中国光纤光网" in page
        and len(body.select("table")) == 1,
        "亨通公告主体、届别或宣传职类变化",
    )
    rows = tables[0].select("tr")
    check(len(rows) == 8, "亨通关联职位列表增减")
    check(
        tuple(compact(x.get_text()) for x in rows[0].select("th,td"))
        == ("序号", "职位信息", "需求专业", "操作"),
        "亨通关联职位表头变化",
    )
    jobs: list[dict[str, str]] = []
    for i, row in enumerate(rows[1:]):
        cells = row.select("td")
        check(
            len(cells) == 4 and compact(cells[0].get_text()) == f"{i + 1:02d}",
            "亨通职位行序号或列变化",
        )
        anchor = cells[1].select_one('a[href^="/job/view/id/"]')
        items = [text(li.get_text(" ", strip=True)) for li in cells[1].select("li")]
        check(anchor is not None and len(items) == 4, "亨通岗位链接或地点/全职/学历缺失")
        assert anchor is not None
        title = text(anchor.get_text(" ", strip=True))
        href = str(anchor.get("href") or "")
        match = re.fullmatch(r"/job/view/id/(\d+)/from_type/3/from_id/191542", href)
        check(
            title == TITLES[i]
            and match is not None
            and items[2] == "全职"
            and bool(items[1])
            and bool(items[3]),
            "亨通岗位标题、关联 ID 或全职属性变化",
        )
        assert match is not None
        jobs.append(
            {
                "key": match[1],
                "title": title,
                "url": urljoin("https://career.gdut.edu.cn", href),
                "location": items[1],
                "education": items[3],
                "majors": text(cells[2].get_text(" ", strip=True)),
            }
        )
    check(len({row["key"] for row in jobs}) == 7, "亨通关联岗位 ID 重复")
    return jobs


def detail(html: str, expected_title: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".details-title .title-message .title")
    info = soup.select_one(".details-title .title-message")
    share = soup.select_one(".details-title .share")
    unit = soup.select_one(".siderinfo .unit-info .title a")
    check(
        title is not None
        and text(title.get_text()) == expected_title
        and info is not None
        and "全职" in info.get_text(" ", strip=True)
        and share is not None
        and unit is not None
        and text(unit.get_text()) == EMPLOYER,
        "亨通岗位详情标题、全职属性或学校账号错配",
    )
    assert share is not None
    date = re.search(r"(\d{4}-\d{2}-\d{2})发布", compact(share.get_text()))
    check(date is not None, "亨通详情发布日期缺失")
    assert date is not None
    return date[1]


class HengtongGdut2027(Adapter):
    name = "hengtong-gdut-2027"
    host = "career.gdut.edu.cn"
    path = "/teachin/view/id/191542"
    scope_description = "亨通集团广东工业大学 2027 届宣讲会关联七个独立全职岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "亨通高校公告未就绪")
        rows = listing(await session.page.content())
        scope = Scope(name="hengtong-gdut-2027-191542", expected=len(rows))
        self.result.scopes.append(scope)
        for item in self.add_page(scope, rows, set(), lambda row: row["key"]):
            try:
                await session.open(item["url"])
                check(session.page is not None, "亨通关联详情未就绪")
                published = detail(await session.page.content(), item["title"])
                job = self.job(
                    item["key"],
                    title=item["title"],
                    source_url=item["url"],
                    unit=EMPLOYER,
                    work_type="校招",
                    location=item["location"],
                    education=item["education"],
                    requirements=item["majors"],
                    published=published,
                    field_sources={
                        "unit": "宣讲会及关联详情均标亨通集团有限公司",
                        "title": "宣讲会关联职位列表和唯一 ID 详情一致",
                        "location": "关联职位表逐岗地点",
                        "education": "关联职位表逐岗学历",
                        "requirements": "关联职位表逐岗需求专业",
                        "published": "关联岗位详情发布日期；非宣讲日期",
                        "duties": "source_missing:详情正文字体混淆，未可靠解码",
                        "deadline": "source_missing:公告未列申请截止日",
                    },
                )
                self.result.jobs.append(job)
                scope.details += 1
                scope.evidence.append(session.last_evidence)
            except Exception as exc:
                self.error(exc, item["key"])
        scope.terminal = scope.details == len(rows)
