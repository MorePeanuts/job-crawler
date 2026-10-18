"""Avary's legacy server-rendered campus pages, including every published park."""

from datetime import date
from typing import cast
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://avaryholding.zhiye.com"
COMPANY = "鹏鼎控股（深圳）股份有限公司"
PARKS = {
    "sz": ("深圳园区", "3^12"),
    "ha": ("淮安园区", "3^11"),
    "qhd": ("秦皇岛园区", "3^10"),
    "yk": ("营口园区", ""),
}


def park_url(park: str) -> str:
    return f"{ROOT}/{park}xz?sub={park}"


def entry_parks(html: str) -> None:
    document = BeautifulSoup(html, "html.parser")
    links = document.select('a[class*="icon5"][href][title]')
    actual = [(urljoin(ROOT, str(a["href"])), text(a["title"])) for a in links]
    expected = {(park_url(key), PARKS[key][0]) for key in ("sz", "ha", "qhd")}
    check(len(actual) == 3 and set(actual) == expected, "鹏鼎校园园区导航缺失、新增或变化")


def park_document(html: str, park: str) -> BeautifulSoup:
    document = BeautifulSoup(html, "html.parser")
    check(COMPANY in text(document.select_one(".footer")), "鹏鼎园区招聘主体变化")
    check(text(document.select_one(".logo span")) == PARKS[park][0], "鹏鼎园区身份错配")
    active = document.select_one("#xyzp.now")
    check(
        active is not None
        and text(active) == "校园招聘"
        and urljoin(ROOT, str(active.get("href"))) == park_url(park),
        "鹏鼎页面不是当前园区校园目录",
    )
    return document


def catalog(html: str, park: str) -> list[dict[str, str]]:
    document = park_document(html, park)
    for selector, value in (("#k", ""), ("#hidcity", ""), ("#hidtime", "-1")):
        element = document.select_one(selector)
        check(element is not None and element.get("value") == value, "鹏鼎目录存在局部筛选")
    category = document.select("select#p option[selected]")
    check(
        len(category) == 1 and category[0].get("value") == "1^-1",
        "鹏鼎职位类别不是全部",
    )
    departments = document.select("select#n")
    check(len(departments) == 1, "鹏鼎公司部门选择器缺失")
    options = departments[0].select("option")
    if park == "yk":
        check(not options, "鹏鼎营口部门范围新增，需核对公开导航")
    else:
        check(
            len(options) == 1
            and options[0].get("value") == PARKS[park][1]
            and options[0].has_attr("selected")
            and text(options[0]) == PARKS[park][0],
            "鹏鼎目录公司部门范围变化",
        )
    tables = document.select(".zwlb table")
    check(len(tables) == 1, "鹏鼎岗位表缺失或不唯一")
    table = tables[0]
    check(
        [text(x) for x in table.select("th")]
        == ["职位名称", "职位类别", "工作地点", "发布日期", "操作"],
        "鹏鼎岗位表头变化",
    )
    records = [tr for tr in table.select("tr") if tr.find("td") is not None]
    check(bool(records), "鹏鼎空表不能证明零岗位")
    if len(records) == 1 and text(records[0]) == "暂无职位":
        check(
            len(records[0].select("td")) == 4
            and all(not a.get("href") for a in records[0].select("a")),
            "鹏鼎零岗位占位行结构变化",
        )
        return []
    check(park != "yk", "鹏鼎营口新增岗位，部门范围需核验")
    check("&PageIndex=" in html and f'"/{park}xz?k="' in html, "鹏鼎搜索分页契约变化")
    rows = []
    for record in records:
        cells = record.select("td")
        check(len(cells) == 5, "鹏鼎岗位行字段数量变化")
        links = record.select("a[href]")
        urls = {urljoin(ROOT, str(a["href"])) for a in links}
        check(len(links) == 5 and len(urls) == 1, "鹏鼎岗位行详情链接错配")
        url = urls.pop()
        parts = urlsplit(url)
        query = parse_qs(parts.query, keep_blank_values=True)
        check(
            parts.scheme == "https"
            and parts.netloc == "avaryholding.zhiye.com"
            and parts.path == f"/{park}xzxq"
            and not parts.fragment
            and set(query) == {"jobId", "sub"}
            and len(query["jobId"]) == 1
            and query["jobId"][0].isdigit()
            and query["sub"] == [park],
            "鹏鼎详情ID或园区关联异常",
        )
        title, category, location, published, action = (text(x) for x in cells)
        check(bool(title) and action == "查看", "鹏鼎岗位标题或查看入口缺失")
        check(date.fromisoformat(published).isoformat() == published, "鹏鼎岗位发布日期异常")
        rows.append(
            {
                "id": query["jobId"][0],
                "title": title,
                "category": category,
                "location": location,
                "published": published,
                "url": url,
            }
        )
    return rows


def search_url(park: str, page: int) -> str:
    return (
        f"{ROOT}/{park}xz?"
        + urlencode(
            {
                "k": "",
                "p": "1^-1," + PARKS[park][1],
                "c": "",
                "d": "-1",
                "PageIndex": page,
                "sub": park,
            }
        )
        + "#zw"
    )


def detail(html: str, row: dict[str, str], park: str) -> dict[str, str]:
    document = park_document(html, park)
    check(text(document.select_one(".zwxqbt h2")) == row["title"], "鹏鼎详情标题错配")
    identity = document.select_one("#apply[url]")
    check(identity is not None, "鹏鼎详情缺少可核对的公开ID")
    assert identity is not None
    parts = urlsplit(str(identity["url"]))
    check(
        parts.path == "/Portal/Resume/ResumeItem" and parse_qs(parts.query) == {"jid": [row["id"]]},
        "鹏鼎详情ID错配",
    )
    values = {}
    for element in document.select(".zwxqbt li"):
        label, separator, value = text(element).partition("：")
        check(bool(separator) and label not in values, "鹏鼎详情结构字段缺失或重复")
        values[label] = value
    check(
        set(values) == {"职位类型", "招聘单位", "工作地址", "发布时间"}
        and values["招聘单位"] == PARKS[park][0]
        and values["发布时间"] == row["published"]
        and values["职位类型"] == row["category"],
        "鹏鼎详情单位、日期或分类与目录不一致",
    )
    body = document.select_one(".zwxqbm")
    check(body is not None, "鹏鼎岗位正文缺失")
    assert body is not None
    check(not body.select("img,a[href],iframe,object,embed"), "鹏鼎正文含未处理附件")
    labels = [text(x) for x in body.select(".zwxqbml")]
    blocks = body.select(".zwxqbmr")
    check(labels == ["工作职责：", "任职职责："] and len(blocks) == 2, "鹏鼎正文章节变化")
    duties, requirements = (text(block) for block in blocks)
    return {
        "duties": "" if duties == row["title"] else duties,
        "requirements": "" if requirements == row["title"] else requirements,
        "unit": values["招聘单位"],
        "location": values["工作地址"],
    }


class AvaryCampus(Adapter):
    name = "avary-campus"
    host = "avaryholding.zhiye.com"
    path = "/campus"
    scope_description = "鹏鼎旧版北森深圳、淮安、秦皇岛校园目录及公开脚本营口入口；逐页到明确空页"

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        entry_parks(await browser.page.content())
        all_ids: set[str] = set()
        for park in PARKS:
            scope = Scope(name="avary-campus-" + park)
            self.result.scopes.append(scope)
            await self.session.open(park_url(park))
            html = await browser.page.content()
            scope.evidence.append(browser.snapshot("avary-" + park + "-entry", html))
            rows = catalog(html, park)
            if park == "sz":
                check('"/ykxz?sub=yk"' in html, "鹏鼎公开营口导航声明变化")
            if rows:
                initial_rows = rows
                await self.session.open(search_url(park, 1))
                html = await browser.page.content()
                scope.evidence.append(browser.snapshot("avary-" + park + "-search", html))
                rows = catalog(html, park)
                check(rows == initial_rows, "鹏鼎规范搜索首页与原校园目录不一致")
            seen: set[str] = set()
            for page in range(1, 51):
                listing_evidence = self.session.last_evidence
                scope.evidence.append(listing_evidence)
                if not rows:
                    scope.expected = len(seen)
                    scope.terminal = True
                    break
                for row in self.add_page(scope, rows, seen, lambda item: item["id"]):
                    key = row["id"]
                    check(key not in all_ids, "鹏鼎跨园区岗位ID重复，需核对联合范围")
                    all_ids.add(key)
                    try:
                        job = self.job(
                            key,
                            title=row["title"],
                            source_url=row["url"],
                            published=row["published"],
                            unit=PARKS[park][0],
                            category_raw=row["category"],
                        )
                        job.evidence = [listing_evidence]
                        reused = self.before_detail(
                            "job:" + key, row, scope, job, evidence=listing_evidence
                        )
                        if reused is not None:
                            self.result.jobs.extend(reused)
                            continue
                        await self.session.open(row["url"])
                        detail_html = await browser.page.content()
                        fields = detail(detail_html, row, park)
                        job.evidence.append(browser.snapshot("avary-detail-" + key, detail_html))
                        for name, value in fields.items():
                            setattr(job, name, value)
                        job.field_sources = {
                            "published": "详情发布时间与列表发布日期一致；不根据标题届别改写",
                            "deadline": "source_missing:未提供截止日期",
                            "location": "详情工作地址区域原文；不使用截断列表地点",
                            "address": "source_missing:未提供详细工作地址",
                            "education": "source_missing:未提供独立学历字段；资格按正文原文处理",
                            "duties": "详情工作职责"
                            if fields["duties"]
                            else "source_missing:工作职责为空或仅重复标题",
                            "requirements": "详情任职职责"
                            if fields["requirements"]
                            else "source_missing:任职职责为空或仅重复标题",
                        }
                        self.result.jobs.append(job)
                        scope.details += 1
                        self.remember("job:" + key, row, [job])
                    except Exception as exc:
                        self.error(exc, key)
                        if isinstance(exc, CrawlError) and exc.code in {
                            "access_denied",
                            "request_budget",
                            "time_budget",
                        }:
                            raise
                await self.session.open(search_url(park, page + 1))
                html = await browser.page.content()
                browser.snapshot(f"avary-{park}-page-{page + 1}", html)
                rows = catalog(html, park)
            check(scope.terminal, "鹏鼎目录超过50页预算，未到明确空页")
