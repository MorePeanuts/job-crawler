"""PCCW/HKT graduate catalogues and their shared programme announcements."""

import re
from datetime import datetime
from typing import cast
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Collection, Job, Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://job.pccw.com"
PLAN = "Graduate-Development-Programmes-v2/"
CATEGORIES = {"pccw": "Graduate-Hiring_pccw/7939210/", "hkt": "Graduate-Hiring_hkt/7939110/"}
PROGRAMMES = {
    "Technology": {
        "Information-Technology": "Information Technology",
        "Engineering": "Engineering & Technology Services",
        "Solutions-Consulting": "Solutions Consulting",
        "Solutions-Delivery": "Solutions Delivery",
        "Transformation-Office": "Transformation Office",
    },
    "Business": {
        "Digital-Ventures": "Digital Ventures",
        "Media": "Media",
        "Sales-and-Marketing-B2B": "Sales & Marketing (B2B)",
        "Marketing-B2B": "Marketing (B2B)",
        "Telecommunication": "Telecommunication",
        "Business-Training": "Business Training",
        "Consumer-Business": "Consumer Business",
    },
}
INVITES = {"Technology": ("58548", "1329370866"), "Business": ("58547", "1329371066")}


def words(value: object) -> str:
    return " ".join(text(value).replace("\u200b", "").split())


def link(value: str) -> str:
    parts = urlsplit(urljoin(ROOT, value))
    check(parts.scheme == "https" and parts.netloc == "job.pccw.com", "PCCW入口跨站")
    check(not parts.query or parts.query == "locale=en_US", "PCCW入口存在筛选参数")
    return ROOT + parts.path.replace("Information Technology/", "Information-Technology/").replace(
        "Consumer Business/", "Consumer-Business/"
    )


def programme_url(tenant: str, stream: str, programme: str) -> str:
    return f"{ROOT}/{tenant}/content/{stream}-Stream---{programme}/"


def home(html: str, tenant: str) -> None:
    doc = BeautifulSoup(html, "html.parser")
    links = {link(str(a["href"])) for a in doc.select("a[href]") if "Graduate" in str(a["href"])}
    check(
        links == {f"{ROOT}/{tenant}/content/{PLAN}", f"{ROOT}/{tenant}/go/{CATEGORIES[tenant]}"},
        "PCCW毕业生首页范围变化",
    )


def plan(html: str, tenant: str) -> None:
    doc = BeautifulSoup(html, "html.parser")
    body = doc.select_one("#content > .inner")
    check(body is not None and "PCCW/HKT Graduate Development" in words(body), "PCCW计划身份缺失")
    assert body is not None
    links = {link(str(a["href"])) for a in body.select("a[href]")}
    check(
        links == {programme_url(tenant, s, next(iter(p))) for s, p in PROGRAMMES.items()},
        "PCCW计划主线或入口变化",
    )


def programme(html: str, tenant: str, stream: str, key: str) -> tuple[str, str]:
    doc = BeautifulSoup(html, "html.parser")
    body = doc.select_one("#content > .inner")
    check(body is not None, "PCCW项目正文缺失")
    assert body is not None
    active = body.select(".topbar a.active")
    check(len(active) == 1 and words(active[0]) == PROGRAMMES[stream][key], "PCCW项目身份不符")
    menu = {link(str(a["href"])) for a in body.select(".topbar a[href]")}
    check(
        menu == {programme_url(tenant, stream, p) for p in PROGRAMMES[stream] if p != key},
        "PCCW项目菜单缺项或新增",
    )
    invite = ROOT + "/job-invite/" + INVITES[stream][0] + "/"
    contact = body.select('a[href="https://forms.office.com/r/26G9kTuHXF"]')
    check(
        len(contact) == 1 and words(contact[0]) == "Click here to fill out the form",
        "PCCW历史联系入口变化",
    )
    hidden = contact[0].find_parent("div", class_="buttontext")
    check(
        hidden is not None
        and "display" in hidden.get_attribute_list("class")
        and "2024 has closed" in words(hidden),
        "PCCW历史联系入口不再是关闭项目",
    )
    brand_urls = (
        {
            "https://www.hktfinancialservices.com",
            "https://\u200bwww.theclub.com.hk",
            "https://clubcare.theclub.com.hk",
        }
        if key == "Digital-Ventures"
        else set()
    )
    brands = [a for a in body.select("a[href]") if a.get("href") in brand_urls]
    check(
        {str(a["href"]) for a in brands} == brand_urls
        and all(a.find_parent("p", class_="intro") is not None for a in brands),
        "PCCW业务品牌介绍入口变化",
    )
    links = {
        link(str(a["href"])) for a in body.select("a[href]") if a not in contact and a not in brands
    }
    check(links == menu | {invite}, "PCCW项目出现新招聘或附件入口")
    check(not body.select("iframe,object,embed"), "PCCW项目存在未处理嵌入正文")
    sections: list[str] = []
    for label in ["What we offer", "We are looking for"]:
        headers = [b for b in body.select("b") if words(b) == label]
        check(len(headers) == 1, "PCCW项目职责/资格分段变化")
        parent = headers[0].find_parent("div", class_="column")
        check(parent is not None and len(words(parent)) > len(label) + 20, "PCCW项目正文为空")
        assert parent is not None
        check(not parent.select("img,iframe,object,embed,a[href]"), "PCCW项目资格存在未处理附件")
        sections.append(words(parent).replace("Meida", "Media"))
    return sections[0], sections[1]


def closed(html: str, identity: str) -> bool:
    doc = BeautifulSoup(html, "html.parser")
    canonical = doc.select_one('link[rel="canonical"]')
    check(canonical is not None, "PCCW详情canonical缺失")
    assert canonical is not None
    check(
        re.fullmatch(
            r"https://job\.pccw\.com/(?:pccw|hkt)/job/[^/]+/" + re.escape(identity) + r"/",
            str(canonical.get("href")),
        )
        is not None,
        "PCCW详情postingID错配",
    )
    state = doc.select(".jobDisplay .job p strong")
    return any(words(x) == "Sorry, this position has been filled." for x in state)


def closed_programme(html: str, stream: str) -> None:
    if not closed(html, INVITES[stream][1]):
        raise CrawlError(
            "unsupported_scope", "PCCW项目招聘公告状态变化，需验证新的开放公告及展开关系"
        )
    doc = BeautifulSoup(html, "html.parser")
    title = doc.select_one('meta[property="og:title"]')
    check(
        title is not None
        and title.get("content")
        == f"PCCW/HKT Graduate Development Programme 2026 ({stream} Stream)",
        "PCCW招满公告项目身份不符",
    )


def catalog(
    html: str, url: str, offset: int, category: str
) -> tuple[int, list[dict[str, str]], str]:
    doc = BeautifulSoup(html, "html.parser")
    check(words(doc.select_one("#category-name")) == category, "PCCW职位栏目身份不符")
    for field in doc.select('input[name="q"],input[name="q2"],input[name="alertId"],.filter-input'):
        check(not field.get("value"), "PCCW职位目录存在搜索筛选")
    for field in doc.select("select.optionsFacet-select"):
        check(
            not any(x.get("value") for x in field.select("option[selected]")),
            "PCCW职位目录存在类别筛选",
        )
    rows = doc.select("#searchresults tr.data-row")
    if doc.select_one("#noresults"):
        check(
            not rows
            and offset == 0
            and words(doc.select_one("#noresults #attention"))
            == "There are currently no open positions matching this category or location."
            and "The 0 most recent jobs posted by hktservice"
            in words(doc.select_one("#noresults-message")),
            "PCCW不是明确空目录，或存在推荐职位",
        )
        return 0, [], ""
    labels = {words(x) for x in doc.select(".paginationLabel")}
    check(len(labels) == 1, "PCCW列表总数缺失或冲突")
    match = re.fullmatch(r"Results (\d+) – (\d+) of (\d+)", labels.pop())
    check(match is not None, "PCCW列表计数格式变化")
    assert match is not None
    first, last, total = map(int, match.groups())
    check(
        first == offset + 1
        and last == min(offset + 20, total)
        and len(rows) == last - offset
        and 0 < total <= 2000,
        "PCCW列表页码、数量或预算异常",
    )
    records = []
    for row in rows:
        anchors = row.select("a.jobTitle-link[href]")
        paths = {str(a["href"]) for a in anchors}
        check(
            len(anchors) == 2 and len(paths) == 1 and words(anchors[0]) == words(anchors[1]),
            "PCCW桌面/移动职位身份不一致",
        )
        target = link(paths.pop())
        key = re.fullmatch(r"https://job\.pccw\.com/(?:pccw|hkt)/job/[^/]+/(\d+)/", target)
        check(key is not None, "PCCW职位链接身份异常")
        assert key is not None
        records.append(
            {
                "id": key[1],
                "url": target,
                "title": words(anchors[0]),
                "location": words(row.select_one("td.colLocation .jobLocation")),
                "published": datetime.strptime(
                    words(row.select_one("td.colDate .jobDate")), "%b %d, %Y"
                )
                .date()
                .isoformat(),
            }
        )
    next_url = ""
    if last < total:
        targets = {
            urljoin(url, str(a["href"]))
            for a in doc.select(f'a[title="Page {offset // 20 + 2}"][href]')
        }
        check(len(targets) == 1, "PCCW下一页链接缺失或冲突")
        next_url = targets.pop()
        parts, base = urlsplit(next_url), urlsplit(url)
        path = re.sub(r"/\d+/$", "/", base.path) if offset else base.path
        # Category IDs also end in digits: only remove an offset on later pages.
        check(
            parts.netloc == base.netloc
            and parts.path == path + str(last) + "/"
            and parts.query == "q=&sortColumn=referencedate&sortDirection=desc",
            "PCCW下一页筛选或偏移量异常",
        )
    return total, records, next_url


def field(doc: BeautifulSoup, name: str) -> str:
    nodes = doc.select(f'[data-careersite-propertyid="{name}"]')
    check(len(nodes) == 1, "PCCW详情字段缺失或重复: " + name)
    return words(nodes[0])


def detail(html: str, row: dict[str, str]) -> dict[str, str]:
    check(not closed(html, row["id"]), "PCCW职位已关闭")
    doc = BeautifulSoup(html, "html.parser")
    check(
        field(doc, "title") == row["title"] and field(doc, "location") == row["location"],
        "PCCW详情标题或地点错配",
    )
    date = doc.select_one('meta[itemprop="datePosted"]')
    check(date is not None, "PCCW发布时间缺失")
    assert date is not None
    published = (
        datetime.strptime(str(date.get("content")), "%a %b %d %H:%M:%S UTC %Y")
        .replace(tzinfo=ZoneInfo("UTC"))
        .astimezone(ZoneInfo("Asia/Shanghai"))
    )
    check(published.date().isoformat() == row["published"], "PCCW列表与详情发布日期不符")
    bodies = doc.select(".jobdescription")
    check(len(bodies) == 1, "PCCW职位正文缺失或重复")
    body = bodies[0]
    check(
        not re.search(
            r"application deadline|closing date|apply (?:by|before)|截止", words(body), re.I
        ),
        "PCCW详情出现尚未验证的截止字段",
    )
    check(not body.select("img,iframe,object,embed,a[href]"), "PCCW职位正文附件尚未处理")
    blocks = [x for x in body.find_all(recursive=False) if isinstance(x, Tag) and words(x)]
    boundaries = [i for i, x in enumerate(blocks) if words(x).rstrip(":") == "Requirements"]
    check(len(boundaries) == 1, "PCCW资格分段尚未验证")
    split = boundaries[0]
    duties = "\n".join(text(x) for x in blocks[:split])
    requirements = "\n".join(text(x) for x in blocks[split + 1 :])
    check(bool(duties and requirements), "PCCW职责或资格为空")
    return {
        "published": published.isoformat(),
        "unit": field(doc, "businessunit"),
        "duties": duties,
        "requirements": requirements,
        "work_type": "实习" if re.search(r"\bintern(?:ship)?\b", row["title"], re.I) else "校招",
    }


class PccwGraduate(Adapter):
    name = "pccw-graduate"
    host = "job.pccw.com"
    path = "/pccw/content/" + PLAN + "?locale=en_US"
    scope_description = "PCCW/HKT双毕业生职位目录、两主线12培养方向及公开公告；不含专业社招/实习"

    async def collect(self) -> Collection:
        if self.source.url != ROOT + self.path:
            self.error(CrawlError("entry_mismatch", "PCCW必须使用官方新版毕业生入口"))
            return self.result
        return await super().collect()

    async def read(self, url: str) -> str:
        return await cast(BrowserSession, self.session).request_html(url)

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        scope = Scope(name="pccw-hkt-programmes", expected=12)
        self.result.scopes.append(scope)
        try:
            bodies: dict[str, tuple[str, str]] = {}
            for tenant in CATEGORIES:
                home(await self.read(f"{ROOT}/{tenant}/"), tenant)
                scope.evidence.append(browser.last_evidence)
                plan(await self.read(f"{ROOT}/{tenant}/content/{PLAN}?locale=en_US"), tenant)
                scope.evidence.append(browser.last_evidence)
                for stream, programmes in PROGRAMMES.items():
                    for key in programmes:
                        body = programme(
                            await self.read(programme_url(tenant, stream, key)), tenant, stream, key
                        )
                        scope.evidence.append(browser.last_evidence)
                        identity = stream + "/" + key
                        if tenant == "pccw":
                            bodies[identity] = body
                            scope.listed += 1
                            scope.unique += 1
                        else:
                            check(bodies[identity] == body, "PCCW/HKT项目正文范围不一致")
            for stream, (invite, _) in INVITES.items():
                closed_programme(await self.read(ROOT + "/job-invite/" + invite + "/"), stream)
                scope.evidence.append(browser.last_evidence)
                scope.skipped_closed += len(PROGRAMMES[stream])
            scope.terminal = True
        except Exception as exc:
            self.error(exc, "programmes")
        emitted: dict[str, Job] = {}
        for tenant, category in CATEGORIES.items():
            scope = Scope(name="pccw-graduate-hiring-" + tenant)
            self.result.scopes.append(scope)
            try:
                url = f"{ROOT}/{tenant}/go/{category}"
                seen: set[str] = set()
                offset = 0
                for _ in range(100):
                    html = await self.read(url)
                    evidence = browser.last_evidence
                    total, rows, next_url = catalog(html, url, offset, "Graduate Hiring_" + tenant)
                    if scope.expected is None:
                        scope.expected = total
                    check(total == scope.expected, "PCCW分页期间总数变化")
                    for row in self.add_page(scope, rows, seen, lambda item: item["id"]):
                        try:
                            job = self.job(
                                row["id"],
                                title=row["title"],
                                location=row["location"],
                                published=row["published"],
                                source_url=row["url"],
                                work_type="校招",
                            )
                            job.evidence = [evidence]
                            entity = tenant + ":" + row["id"]
                            reused = self.before_detail(entity, row, scope, job, evidence=evidence)
                            if reused is None:
                                detail_html = await self.read(row["url"])
                                scope.evidence.append(browser.last_evidence)
                                if closed(detail_html, row["id"]):
                                    scope.skipped_closed += 1
                                    continue
                                for name, value in detail(detail_html, row).items():
                                    setattr(job, name, value)
                                job.evidence.append(browser.last_evidence)
                                job.field_sources = {
                                    "published": "公开datePosted UTC转上海并核对列表日期",
                                    "deadline": "source_missing:未提供截止",
                                    "address": "source_missing:未提供详细工作地址",
                                    "education": "source_missing:资格原文交公共补全",
                                    "work_type": "正式Graduate Hiring栏目；实习标题排除",
                                }
                                scope.details += 1
                                self.remember(entity, row, [job])
                            else:
                                check(len(reused) == 1, "PCCW详情缓存数量异常")
                                job = reused[0]
                            prior = emitted.get(row["id"])
                            if prior is not None:
                                keys = [
                                    "title",
                                    "location",
                                    "published",
                                    "unit",
                                    "duties",
                                    "requirements",
                                    "work_type",
                                ]
                                check(
                                    all(getattr(prior, k) == getattr(job, k) for k in keys),
                                    "PCCW双门户同ID正文冲突",
                                )
                                prior.evidence.extend(job.evidence)
                            else:
                                self.result.jobs.append(job)
                                emitted[row["id"]] = job
                        except Exception as exc:
                            self.error(exc, row["id"])
                            if isinstance(exc, CrawlError) and exc.code in {
                                "access_denied",
                                "request_budget",
                                "time_budget",
                            }:
                                raise
                    if not next_url:
                        check(len(seen) == total, "PCCW末页唯一数与总数不符")
                        scope.terminal = True
                        break
                    offset += len(rows)
                    url = next_url
                check(scope.terminal, "PCCW超过分页预算")
            except Exception as exc:
                self.error(exc, tenant)
