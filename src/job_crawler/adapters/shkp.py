"""The original source's public mainland management-trainee programme."""

import re
from dataclasses import asdict, dataclass
from typing import cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import fingerprint
from job_crawler.transport import BrowserSession


@dataclass
class Direction:
    key: str
    title: str
    duties: str
    requirements: str
    location: str
    deadline: str
    batch: str
    apply_url: str


def section(soup: BeautifulSoup, label: str) -> Tag:
    headings = [h for h in soup.select("h3") if h.get_text(strip=True) == label]
    check(len(headings) == 1, f"新鸿基章节缺失或重复：{label}")
    parent = headings[0].parent
    check(isinstance(parent, Tag), "新鸿基章节结构变化")
    assert isinstance(parent, Tag)
    return parent


def parse(html: str) -> list[Direction]:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one("h1")
    check(
        heading is not None and heading.get_text(strip=True) == "管理培训生(内地)",
        "新鸿基项目身份变化",
    )
    check("新鸿基地产发展有限公司" in soup.get_text(), "新鸿基企业标识缺失")
    region = next(h for h in soup.select("h3") if h.get_text(strip=True) == "聘任地区")
    region_body = region.find_next_sibling()
    check(isinstance(region_body, Tag), "新鸿基地区正文缺失")
    location = text(str(region_body))
    check(bool(location), "新鸿基聘任地区为空")
    requirements = text(str(section(soup, "入职要求")))
    check("应届" in requirements and "毕业" in requirements, "新鸿基校园对象缺失")
    application = section(soup, "申请及查询")
    dates = []
    for row in application.select("tr"):
        cells = row.find_all("td")
        if len(cells) == 2 and "申请截止日期" in cells[0].get_text():
            dates.append(cells[1].get_text(strip=True))
    check(len(dates) == 1, "新鸿基申请截止日期缺失或重复")
    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", dates[0])
    check(match is not None, "新鸿基申请截止日期格式变化")
    assert match is not None
    deadline = "-".join(f"{int(v):02}" for v in match.groups())
    year = re.search(r"管理培训生\(内地\)招聘\s*(\d{4})年", application.get_text(" ", strip=True))
    check(year is not None, "新鸿基项目年度缺失")
    assert year is not None
    links = [
        str(a["href"])
        for a in application.select("a[href]")
        if urlsplit(str(a["href"])).hostname == "xyz.51job.com"
    ]
    check(len(set(links)) == 1, "新鸿基网申入口缺失或重复")
    apply_url = links[0]
    check(
        urlsplit(apply_url).path == "/External/Apply.aspx"
        and bool(parse_qs(urlsplit(apply_url).query).get("CtmID")),
        "新鸿基网申路径变化",
    )
    departments = section(soup, "聘任部门")
    items = departments.select(".accordion-item")
    check(bool(items), "新鸿基聘任部门为空，不能视为零岗位")
    result = []
    seen: set[str] = set()
    for item in items:
        title = item.select_one(".title")
        body = item.select_one(".accordion-content")
        check(title is not None and body is not None, "新鸿基部门标题或正文缺失")
        assert title is not None and body is not None
        name = title.get_text(strip=True)
        duties = text(str(body))
        check(bool(name) and bool(duties) and name not in seen, "新鸿基部门重复或全文缺失")
        check(not body.select("a[href]"), "新鸿基部门新增详情链接，须核验")
        seen.add(name)
        result.append(
            Direction(
                key=f"mainland:{year[1]}:{fingerprint(name)[:16]}",
                title=f"管理培训生（内地）—{name}",
                duties=duties,
                requirements=requirements,
                location=location,
                deadline=deadline,
                batch=f"{year[1]}年内地管理培训生",
                apply_url=apply_url,
            )
        )
    return result


class ShkpMainland(Adapter):
    name = "shkp-mainland-trainee-directions"
    host = "www.shkp.com"
    path = "/zh-CN/work-with-us/management-trainee-mainland"
    scope_description = (
        "用户指定新鸿基内地管理培训生项目全部聘任部门方向；非香港独立项目或子公司全目录"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        html = await session.page.content()
        evidence = session.snapshot("mainland-trainees", html)
        directions = parse(html)
        scope = Scope(name="mainland-trainee-directions", unit="招聘方向", expected=len(directions))
        self.result.scopes.append(scope)
        rows = self.add_page(scope, [asdict(d) for d in directions], set(), lambda r: r["key"])
        for row in rows:
            key = row.pop("key")
            job = self.job(
                key,
                source_url=f"https://{self.host}{self.path}",
                **row,
                field_sources={
                    "duties": "聘任部门各accordion-content全文",
                    "requirements": "入职要求章节",
                    "location": "同页聘任地区，不推定单一部门城市",
                    "deadline": "申请及查询表格申请截止日期",
                    "published": "source_missing",
                    "education": "source_missing：大学生不等于明确本科学历",
                },
            )
            resolved = self.before_detail(f"direction:{key}", row, scope, job, evidence=evidence)
            if resolved is not None:
                self.result.jobs.extend(resolved)
                continue
            self.result.jobs.append(job)
            scope.details += 1
            self.remember(f"direction:{key}", row, [job])
        scope.terminal = True
