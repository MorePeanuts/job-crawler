"""Aisidi's matched public employer catalog and 2027 campus announcement."""

import re
from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.adapters.tfme import ROOT, catalog, detail_document
from job_crawler.description import strip_heading
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

COMPANY = "深圳市爱施德股份有限公司"
EMPLOYER = ROOT + "/companydetail/view/id/345026"
ANNOUNCEMENT = "https://zqmc.bysjy.com.cn/detail/career?id=722314"


def role(title: str) -> str:
    return re.sub(r"管培生$", "", re.sub(r"^2027届(?:管理培训生|管培生)-+", "", title))


def campus_rows(html: str) -> list[dict[str, str]]:
    document = BeautifulSoup(html, "html.parser")
    intro = document.select_one("#pane-detail")
    check(
        intro is not None
        and COMPANY in intro.get_text()
        and "2027届" in intro.get_text()
        and "零售事业群" in intro.get_text()
        and "002416" in intro.get_text(),
        "爱施德补充简章主体或校招范围变化",
    )
    counts = document.select("#tab-jobs")
    check(len(counts) == 1, "爱施德简章招聘职位计数缺失")
    match = re.fullmatch(r"招聘职位\s*\((\d+)\)", counts[0].get_text(strip=True))
    check(match is not None, "爱施德简章职位计数结构变化")
    assert match is not None
    expected = int(match[1])
    pane = document.select_one("#pane-jobs")
    check(pane is not None, "爱施德简章职位页签缺失")
    assert pane is not None
    check(not pane.select(".el-pagination,.pagination,.pager"), "爱施德简章新增未处理分页")
    rows = []
    for card in pane.select(".career-job.job-item"):
        anchors = card.select("a.career-job-name[href]")
        check(len(anchors) == 1, "爱施德简章职位标题或链接不唯一")
        title = anchors[0].get_text(strip=True)
        check(
            re.match(r"^2027届(?:管理培训生|管培生)-+\S", title) is not None
            and "实习" not in title,
            "爱施德简章出现未经验证届别或类型",
        )
        url = urljoin(ANNOUNCEMENT, str(anchors[0]["href"]))
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        check(
            parts.hostname == "zqmc.bysjy.com.cn"
            and parts.path == "/detail/job"
            and query.get("career_id") == ["722314"]
            and len(query.get("id", [])) == 1
            and query["id"][0].isdigit(),
            "爱施德简章岗位链接身份变化",
        )
        fields: dict[str, str] = {}
        for selector, name in [("要求学历", "education"), ("工作地点", "location")]:
            nodes = card.select(f'.job-item-line2 span[title="{selector}"]')
            check(len(nodes) == 1, f"爱施德简章{name}缺失或重复")
            fields[name] = nodes[0].get_text(strip=True)
            check(bool(fields[name]), f"爱施德简章{name}为空")
        rows.append({"campus_id": query["id"][0], "campus_title": title, **fields})
    check(len(rows) == expected, "爱施德简章计数与完整卡片数不符")
    check(len({r["campus_id"] for r in rows}) == len(rows), "爱施德简章岗位ID重复")
    check(len({role(r["campus_title"]) for r in rows}) == len(rows), "爱施德简章岗位名不唯一")
    return rows


def match_rows(
    listings: list[dict[str, str]], supplements: list[dict[str, str]]
) -> list[dict[str, str]]:
    index = {role(r["campus_title"]): r for r in supplements}
    names = [role(row["title"]) for row in listings]
    check(
        len(names) == len(set(names)) == len(index) == len(supplements)
        and set(names) == set(index),
        "爱施德两源岗位目录无法唯一对应",
    )
    return [{**row, **index[role(row["title"])]} for row in listings]


def detail(html: str, row: dict[str, str]) -> dict[str, str]:
    document, body = detail_document(html, row, company=COMPANY, employer=EMPLOYER)
    check(
        all(isinstance(n, Tag) and n.name == "p" for n in body.contents if str(n).strip()),
        "爱施德岗位正文段落结构变化",
    )
    paragraphs = [p.get_text(" ", strip=True) for p in body.find_all("p", recursive=False)]
    paragraphs = [p for p in paragraphs if p]
    check(len(paragraphs) >= 2, "爱施德缺少职责或任职段落")
    check(
        not re.match(r"^(?:要求|任职|专业|学历|本科|硕士|博士)", paragraphs[0]),
        "爱施德职责与任职段落顺序变化",
    )
    duties = strip_heading(paragraphs[0], "duties")
    requirements = strip_heading("\n".join(paragraphs[1:]), "requirements")
    majors = [
        item.get_text("", strip=True)
        for item in document.select("li.full-width")
        if item.get_text("", strip=True).startswith("需求专业：")
    ]
    check(len(majors) == 1, "爱施德详情需求专业缺失或重复")
    addresses = document.select(".details-address .address-container > p")
    check(len(addresses) == 1, "爱施德工作地址结构变化")
    address = addresses[0].get_text(strip=True)
    if row["location"] != "深圳市":
        address = ""
    return {"duties": duties, "requirements": requirements + "\n" + majors[0], "address": address}


class AisidiCampus(Adapter):
    name = "aisidi-retail-campus"
    host = "www.91wllm.cn"
    path = "/companydetail/view/id/345026/tab/1"
    ready_endpoints = ("/companydetail/statInfo/id/345026",)
    scope_description = (
        "爱施德湖北官方就业平台完整企业目录，与2027零售事业群简章逐岗对应；全国岗位保留全国地点"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        expected, listings = catalog(await session.page.content(), company=COMPANY, title_suffix="")
        list_evidence = session.last_evidence
        await session.open(ANNOUNCEMENT)
        html = await session.page.content()
        session.snapshot("aisidi-2027-campus", html)
        campus_evidence = session.last_evidence
        rows = match_rows(listings, campus_rows(html))
        scope = Scope(name="aisidi-employer-345026", expected=expected)
        scope.evidence = [list_evidence, campus_evidence]
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda r: r["id"]):
            try:
                listing = self.job(row["id"], title=row["campus_title"], source_url=row["url"])
                reused = self.before_detail(
                    f"job:{row['id']}", row, scope, listing, evidence=list_evidence
                )
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                await session.open(row["url"])
                html = await session.page.content()
                session.snapshot(f"aisidi-job-{row['id']}", html)
                values = detail(html, row)
                job = self.job(
                    row["id"],
                    title=row["campus_title"],
                    unit=COMPANY,
                    source_url=row["url"],
                    work_type="校招",
                    education=row["education"],
                    location=row["location"],
                    **values,
                    field_sources={
                        "duties": "湖北官方就业平台.职位详情.首段职责",
                        "requirements": "湖北官方就业平台.职位详情.后续任职段落与需求专业",
                        "education": ANNOUNCEMENT + "#pane-jobs:同届同岗明确学历",
                        "location": ANNOUNCEMENT
                        + "#pane-jobs:同届同岗原始地点，优先于湖北默认深圳",
                        "address": (
                            "湖北官方就业平台.工作地址"
                            if values["address"]
                            else "source_conflict:全国岗位不沿用湖北页面统一深圳地址"
                        ),
                        "published": "source_missing:未披露岗位发布日期，宣讲日期不代填",
                        "deadline": "source_missing:未披露岗位截止，宣讲结束不等于招聘结束",
                    },
                )
                job.evidence = [list_evidence, campus_evidence, session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{row['id']}", row, [job])
            except Exception as exc:
                self.error(exc, row["id"])
                if isinstance(exc, CrawlError) and exc.code in {
                    "access_denied",
                    "request_budget",
                    "time_budget",
                }:
                    return
        scope.terminal = True
