"""Hongwang's two 2027 graduate roles linked from its KMUST campus event."""

import re
from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

COMPANY = "宏旺控股集团有限公司"
CAREER_ID = "714546"
ENTRY = f"https://kmust.uat.bysjy.com.cn/detail/career?id={CAREER_ID}"


def roster(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    page = soup.get_text(" ", strip=True)
    check("宏旺控股集团2027届校园招聘宣讲会" in page and COMPANY in page, "宏旺校招主体或届别变化")
    count = soup.select("#tab-jobs")
    check(len(count) == 1, "宏旺职位计数缺失或重复")
    matched = re.fullmatch(r"招聘职位\s*\((\d+)\)", count[0].get_text(strip=True))
    check(matched is not None, "宏旺职位计数格式变化")
    assert matched is not None
    pane = soup.select_one("#pane-jobs")
    check(
        pane is not None and not pane.select(".el-pagination,.pagination,.pager"),
        "宏旺职位页签或分页变化",
    )
    assert pane is not None
    rows: list[dict[str, str]] = []
    for card in pane.select(".career-job.job-item"):
        anchors = card.select("a.career-job-name[href]")
        check(len(anchors) == 1, "宏旺岗位链接缺失或重复")
        url = urljoin(ENTRY, str(anchors[0]["href"]))
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        check(
            parts.hostname == "kmust.uat.bysjy.com.cn"
            and parts.path == "/detail/job"
            and query.get("career_id") == [CAREER_ID]
            and len(query.get("id", [])) == 1
            and query["id"][0].isdigit(),
            "宏旺岗位不属于本次宣讲",
        )
        title = text(anchors[0].get_text())
        check(bool(title), "宏旺岗位标题为空")
        rows.append({"id": query["id"][0], "title": title, "url": url})
    check(len(rows) == int(matched[1]) == 2, "宏旺本次宣讲职位数量变化")
    check(len({row["id"] for row in rows}) == len(rows), "宏旺岗位 ID 重复")
    return rows


def detail(html: str, row: dict[str, str]) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".job-hero-title")
    company = soup.select_one(".job-hero-company")
    check(
        title is not None
        and text(title.get_text()) == row["title"]
        and company is not None
        and text(company.get_text()) == COMPANY,
        "宏旺岗位详情主体或标题错配",
    )
    conditions = soup.select(".job-hero-cond span")
    check(len(conditions) == 3 and text(conditions[2].get_text()) == "全职", "宏旺岗位性质改变")
    education = text(conditions[0].get_text())
    listed_location = text(conditions[1].get_text())
    check(education == "本科及以上" and bool(listed_location), "宏旺学历或列表地点异常")
    dates = [
        stat.select_one(".job-hero-stat-value")
        for stat in soup.select(".job-hero-stat")
        if "发布时间" in stat.get_text()
    ]
    check(len(dates) == 1 and dates[0] is not None, "宏旺发布时间缺失")
    assert dates[0] is not None
    date_match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text(dates[0].get_text()))
    check(date_match is not None, "宏旺发布时间格式改变")
    assert date_match is not None
    sections: dict[str, str] = {}
    for block in soup.select(".job-desc-block"):
        label = block.select_one(".job-desc-label")
        body = block.select_one(".job-desc-text")
        if label is None or body is None:
            continue
        name = text(label.get_text()).rstrip("：")
        if name in {"岗位职责", "岗位要求"}:
            check(name not in sections, "宏旺详情章节重复")
            items = [text(li.get_text(" ", strip=True)) for li in body.select("li")]
            check(len(items) >= 2 and all(items), "宏旺详情职责或要求不完整")
            sections[name] = "\n".join(items)
    check(set(sections) == {"岗位职责", "岗位要求"}, "宏旺岗位职责或要求缺失")
    check(re.search(r"2027\s*届应届", sections["岗位要求"]) is not None, "宏旺岗位不再是2027届校招")
    location = listed_location
    if row["title"] == "财务专员（海外）":
        check("工作地点为坦桑尼亚" in sections["岗位要求"], "宏旺海外财务实际工作地变化")
        location = "坦桑尼亚"
    return {
        "education": education,
        "location": location,
        "duties": sections["岗位职责"],
        "requirements": sections["岗位要求"],
        "published": f"{date_match[1]}-{int(date_match[2]):02d}-{int(date_match[3]):02d}",
    }


class HongwangKmust2027(Adapter):
    name = "hongwang-kmust-2027"
    host = "kmust.uat.bysjy.com.cn"
    path = "/detail/career?id=714546"
    scope_description = "宏旺控股昆明理工大学2027届宣讲关联的两个公开岗位；不扩展至集团其他校园渠道"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "宏旺高校宣讲页面未就绪")
        rows = roster(await session.page.content())
        list_evidence = session.last_evidence
        scope = Scope(name="hongwang-kmust-2027-714546", expected=len(rows))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["id"]):
            try:
                listing = self.job(row["id"], title=row["title"], source_url=row["url"])
                cached = self.before_detail(row["id"], row, scope, listing, evidence=list_evidence)
                if cached is not None:
                    self.result.jobs.extend(cached)
                    continue
                await session.open(row["url"])
                check(session.page is not None, "宏旺岗位详情未就绪")
                values = detail(await session.page.content(), row)
                job = self.job(
                    row["id"],
                    title=row["title"],
                    source_url=row["url"],
                    work_type="校招",
                    unit=COMPANY,
                    **values,
                    field_sources={
                        "title": "昆明理工大学宣讲岗位卡片与关联详情",
                        "unit": "关联详情招聘企业",
                        "education": "关联详情学历要求",
                        "location": (
                            "关联详情岗位要求实际工作地；卡片佛山为冲突地点"
                            if row["title"] == "财务专员（海外）"
                            else "关联详情工作地点"
                        ),
                        "duties": "关联详情岗位职责列表",
                        "requirements": "关联详情岗位要求列表",
                        "published": "关联详情发布时间",
                        "deadline": "source_missing:未披露报名截止日期，宣讲结束不是截止",
                    },
                )
                job.evidence = [list_evidence, session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(row["id"], row, [job])
            except Exception as exc:
                self.error(exc, row["id"])
        scope.terminal = True
