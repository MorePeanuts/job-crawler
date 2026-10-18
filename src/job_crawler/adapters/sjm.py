"""SJM's complete mixed vacancy directory, with explicit graduate eligibility."""

import re
from datetime import datetime
from typing import cast
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://www.sjmjob.com"
LANGUAGE = ROOT + "/Home/SetLanguage?culture=en-GB&returnUrl=%2FHome"


def words(value: object) -> str:
    return " ".join(text(value).split())


def posted(value: str) -> str:
    check(re.fullmatch(r"\d{2}/\d{2}/\d{4}", value) is not None, "澳娱刊登日期格式变化")
    return datetime.strptime(value, "%d/%m/%Y").date().isoformat()


def page_url(page: int) -> str:
    return ROOT + "/Jobs?" + urlencode({"page": page, "sortedBy": "Apply Date"})


def page_number(url: str) -> int:
    parts = urlsplit(urljoin(ROOT + "/Jobs", url))
    query = parse_qs(parts.query)
    check(
        parts.netloc == "www.sjmjob.com"
        and parts.path == "/Jobs"
        and set(query) == {"page", "sortedBy"}
        and query["sortedBy"] == ["Apply Date"]
        and len(query["page"]) == 1
        and query["page"][0].isdigit(),
        "澳娱分页入口存在局部筛选或排序变化",
    )
    return int(query["page"][0])


def document(html: str) -> BeautifulSoup:
    doc = BeautifulSoup(html, "html.parser")
    check("SJM Resorts, S.A." in words(doc.select_one(".footer")), "澳娱招聘主体不符")
    check(
        any(
            words(a) == "Browse Job" and a.get("href") == "/Jobs"
            for a in doc.select(".navbar a[href]")
        ),
        "澳娱导航或英文会话异常",
    )
    return doc


def catalog(html: str, page: int) -> tuple[int, list[dict[str, str]]]:
    doc = document(html)
    for label in ("locationFilter", "departmentFilter"):
        active = doc.select(f'ul[aria-labelledby="{label}"] li.active')
        check(len(active) == 1 and words(active[0]) == "All", "澳娱目录并非全部地区及部门")
    search = doc.select_one("#searchBar")
    check(search is not None and search.get("value", "") == "", "澳娱目录存在关键词筛选")
    pagers = doc.select('form[action="/Jobs"]')
    check(len(pagers) == 2, "澳娱分页控件缺失或变化")
    totals = []
    for pager in pagers:
        options = pager.select('select[name="page"] option')
        pages = [str(x.get("value")) for x in options]
        check(
            0 < len(pages) <= 100 and pages == [str(n) for n in range(1, len(pages) + 1)],
            "澳娱页码选项缺失或超过100页预算",
        )
        last = len(pages)
        check(
            [str(x.get("value")) for x in options if x.has_attr("selected")] == [str(page)],
            "澳娱当前页码错配",
        )
        for label, target, disabled in [
            ("Previous", max(1, page - 1), page == 1),
            ("Next", min(last, page + 1), page == last),
        ]:
            links = [a for a in pager.select("a[href]") if words(a) == label]
            check(
                len(links) == 1
                and page_number(str(links[0]["href"])) == target
                and ("disabled" in links[0].get_attribute_list("class")) == disabled,
                "澳娱前后页或末页状态异常",
            )
        totals.append(last)
    check(totals[0] == totals[1], "澳娱上下分页总页数不一致")
    rows = []
    for card in doc.select(".post"):
        links = card.select("a.view-detail[href]")
        check(
            len(links) == 2 and len({str(a["href"]) for a in links}) == 1,
            "澳娱卡片详情链接缺失或不一致",
        )
        path = str(links[0]["href"])
        match = re.fullmatch(r"/Jobs/(\d+)", path)
        check(match is not None, "澳娱详情链接ID异常")
        assert match is not None
        key = match[1]
        title = words(card.select_one(".header.view-detail"))
        department = card.select_one(".meta a.category[href]")
        location = card.select_one(".extra-body a[href]")
        check(
            bool(title) and department is not None and location is not None,
            "澳娱职位名称、部门或地区缺失",
        )
        assert department is not None and location is not None
        check(
            str(department["href"]).startswith("/Jobs?dept=DN")
            and str(location["href"]) in {"/Jobs?loc=MP", "/Jobs?loc=COT", "/Jobs?loc=HK"},
            "澳娱部门或工作地区身份变化",
        )
        applications = card.select('a[href^="/Jobs/Apply/"]')
        check(
            len(applications) == 1 and applications[0]["href"] == "/Jobs/Apply/" + key,
            "澳娱卡片申请ID错配",
        )
        rows.append(
            {
                "id": key,
                "title": title,
                "department": words(department),
                "department_path": str(department["href"]),
                "location": words(location),
                "location_path": str(location["href"]),
                "published": posted(words(card.select_one(".time"))),
                "url": ROOT + path,
            }
        )
    check(
        (len(rows) == 21 if page < totals[0] else 0 < len(rows) <= 21),
        "澳娱目录缺行或空状态尚未验证，不能认定零岗位",
    )
    return totals[0], rows


def work_type(title: str, requirements: str) -> str:
    if re.search(r"\bintern(?:ship)?\b|实习|實習", title, re.I) or re.search(
        r"\bthis is an? internship\b", requirements, re.I
    ):
        return "实习"
    if re.search(
        r"\bgraduate (?:trainee|associate|programme|program|recruitment)\b", title, re.I
    ) or re.search(
        r"\b(?:fresh|recent|new) (?:university |college )?graduates?\b|"
        r"\bgraduates? (?:are )?(?:welcome|encouraged to apply)\b|应届|應屆|校招",
        requirements,
        re.I,
    ):
        return "校招"
    check(
        not re.search(
            r"campus recruit|school leaver|graduate programme|graduate program|"
            r"应届|應屆|校招|毕业生|畢業生",
            title + "\n" + requirements,
            re.I,
        ),
        "澳娱出现尚未确认的毕业生招聘表述，需核对范围",
    )
    return "未明确校招"


def detail(html: str, row: dict[str, str]) -> dict[str, str]:
    doc = document(html)
    tables = doc.select("dl.dl-jobs-detail")
    check(len(tables) == 1, "澳娱详情字段表缺失或重复")
    table = tables[0]
    labels = [words(x) for x in table.find_all("dt", recursive=False)]
    values = table.find_all("dd", recursive=False)
    check(
        labels
        == [
            "Position",
            "Department",
            "Working Location",
            "Post Date",
            "Requirements",
            "Responsibilities",
        ]
        and len(values) == 6,
        "澳娱详情字段结构变化",
    )
    check(
        words(values[0]) == row["title"]
        and words(values[1]) == row["department"]
        and words(values[2]) == row["location"]
        and posted(words(values[3])) == row["published"],
        "澳娱详情标题、单位、地点或日期错配",
    )
    for node, field in [(values[1], "department_path"), (values[2], "location_path")]:
        anchors = node.select("a[href]")
        check(len(anchors) == 1 and anchors[0]["href"] == row[field], "澳娱详情部门或地点编码错配")
    applications = doc.select('a[href^="/Jobs/Apply/"]')
    check(
        len(applications) == 1 and applications[0]["href"] == "/Jobs/Apply/" + row["id"],
        "澳娱详情岗位ID错配",
    )
    for node in values[4:]:
        check(not node.select("a[href],img,iframe,object,embed"), "澳娱正文含未解析附件")
    requirements, duties = (text(node).replace("\r", "\n").strip() for node in values[4:])
    requirements = "" if requirements == "N/A" else requirements
    duties = "" if duties == "N/A" else duties
    return {
        "requirements": requirements,
        "duties": duties,
        "work_type": work_type(row["title"], requirements),
    }


class SjmPublicJobs(Adapter):
    name = "sjm-public-jobs"
    host = "www.sjmjob.com"
    path = "/Home/SetLanguage?culture=en-GB&returnUrl=%2FHome"
    scope_description = "澳娱全部地区/部门公开Jobs目录；仅明确应届资格纳入正式校招"

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        document(await browser.page.content())
        scope = Scope(name="sjm-all-public-vacancies")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        last: int | None = None
        for page in range(1, 101):
            html = await browser.request_html(page_url(page))
            evidence = self.session.last_evidence
            pages, rows = catalog(html, page)
            if last is None:
                last = pages
            check(pages == last, "澳娱遍历期间总页数变化")
            for row in self.add_page(scope, rows, seen, lambda item: item["id"]):
                try:
                    job = self.job(
                        row["id"],
                        title=row["title"],
                        source_url=row["url"],
                        unit="SJM Resorts, S.A. / " + row["department"],
                        location=row["location"],
                        published=row["published"],
                    )
                    job.evidence = [evidence]
                    reused = self.before_detail(
                        "job:" + row["id"], row, scope, job, evidence=evidence
                    )
                    if reused is not None:
                        self.result.jobs.extend(reused)
                        continue
                    fields = detail(await browser.request_html(row["url"]), row)
                    job.evidence.append(self.session.last_evidence)
                    for name, value in fields.items():
                        setattr(job, name, value)
                    job.field_sources = {
                        "published": "公开Post Date与目录刊登日期一致，DD/MM/YYYY转ISO；不采用排序名推断",
                        "deadline": "source_missing:未提供截止日期",
                        "location": "Working Location原文；不改为招募中心地址",
                        "address": "source_missing:未提供工作详细地址",
                        "education": "source_missing:未提供独立学历字段；资格原文交公共流程",
                        "requirements": "公开Requirements"
                        if fields["requirements"]
                        else "source_missing:N/A或空资格",
                        "duties": "公开Responsibilities"
                        if fields["duties"]
                        else "source_missing:N/A或空职责",
                        "work_type": "依据标题及Requirements明确应届/实习表述；学历graduate和经验优先不算校招",
                    }
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember("job:" + row["id"], row, [job])
                except Exception as exc:
                    self.error(exc, row["id"])
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if page == last:
                scope.expected = len(seen)
                scope.terminal = True
                break
        check(scope.terminal, "澳娱未遍历至已确认末页")
