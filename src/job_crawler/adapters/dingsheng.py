"""Dingsheng's public mixed directory reconciled with its full WUST catalog."""

import re
from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

COMPANY = "江苏鼎胜新能源材料股份有限公司"
ROOT = "https://www.dingshengxincai.com"
UNIVERSITY = "https://wust.91wllm.cn"
EMPLOYER = "/company/view/id/346005"
FAIR = "/largefairs/company/id/8624/sid/93/stype/1"


def official_catalog(html: str, page: int) -> tuple[list[dict[str, str]], int]:
    doc = BeautifulSoup(html, "html.parser")
    check(COMPANY in doc.get_text() and "虚位以待" in doc.get_text(), "鼎胜官网招聘主体变化")
    pagers = doc.select("ul.pagination")
    check(len(pagers) == 1, "鼎胜官网分页结构变化")
    pager = pagers[0]
    active = pager.select_one("li.active")
    check(active is not None, "鼎胜官网当前页缺失")
    assert active is not None
    check(active.get_text(strip=True) == str(page), "鼎胜官网页码错配")
    pages = [
        int(x.get_text(strip=True)) for x in pager.select("li") if x.get_text(strip=True).isdigit()
    ]
    check(pages == list(range(1, max(pages) + 1)), "鼎胜官网页码不连续")
    last = max(pages)
    for a in pager.select("a[href]"):
        target = urljoin(ROOT, str(a["href"]))
        check(
            re.fullmatch(re.escape(ROOT) + r"/channels/31(?:_\d+)?\.html", target) is not None,
            "鼎胜官网分页链接变化",
        )
    next_items = [x for x in pager.select("li") if x.get_text(strip=True) == "下一页"]
    check(
        len(next_items) == 1
        and ("disabled" in (next_items[0].get("class") or [])) == (page == last),
        "鼎胜官网末页标记矛盾",
    )
    rows = []
    for box in doc.select(".zhaopin_box"):
        links = box.select(".biaoti .wenzi a[href]")
        check(len(links) == 1, "鼎胜官网岗位标题链接缺失")
        a = links[0]
        url = urljoin(ROOT, str(a["href"]))
        match = re.fullmatch(re.escape(ROOT) + r"/contents/31/(\d+)\.html", url)
        check(match is not None, "鼎胜官网详情ID异常")
        assert match is not None
        rows.append({"id": match[1], "title": a.get_text(strip=True), "url": url})
    check(bool(rows), "鼎胜官网空目录不能证明零岗位")
    return rows, last


def official_body(html: str, row: dict[str, str]) -> str:
    doc = BeautifulSoup(html, "html.parser")
    check(COMPANY in doc.get_text(), "鼎胜官网详情主体变化")
    title = doc.select_one(".titles h3")
    check(title is not None and title.get_text(strip=True) == row["title"], "鼎胜官网详情标题错配")
    body = doc.select_one(".left_lie")
    check(body is not None, "鼎胜官网正文缺失")
    assert body is not None
    parts = []
    ended = False
    for node in body.children:
        if not isinstance(node, Tag) or "titles" in (node.get("class") or []):
            continue
        value = node.get_text(" ", strip=True)
        if "职位应聘联系方式" in value:
            ended = True
            break
        check(not node.select("img,a[href],iframe,object,embed"), "鼎胜官网正文含未解析附件")
        parts.append(value)
    text = "\n".join(parts).strip()
    check(ended and bool(text), "鼎胜官网正文边界不完整")
    # The current mixed directory has no graduate declaration. A new declaration
    # needs scope review; never quietly drop it under the historical exclusion.
    check(
        not re.search("应届|校招|校园|毕业生|管培", text + row["title"]),
        "鼎胜官网新增校园资格，需核对与高校目录的联合范围",
    )
    return text


def school_catalog(html: str, *, fair: bool = False) -> list[dict[str, str]]:
    doc = BeautifulSoup(html, "html.parser")
    check(COMPANY in doc.get_text(), "鼎胜高校目录主体变化")
    check(not doc.select(".pagination,.pager"), "鼎胜高校目录出现未处理分页")
    if fair:
        check(
            "2027届毕业生" in doc.get_text() and "9132110075321015XF" in doc.get_text(),
            "鼎胜招聘会主体或校园范围变化",
        )
    else:
        names = [n.get_text(strip=True) for n in doc.select(".unit-info .title h5")]
        check(names == [COMPANY], "鼎胜高校完整企业目录身份不符")
    rows = []
    for a in doc.select('table a[href*="/job/view/id/"]'):
        url = urljoin(UNIVERSITY, str(a["href"]))
        match = re.fullmatch(
            re.escape(UNIVERSITY) + r"/job/view/id/(\d+)(?:/from_type/2/from_id/57024)?", url
        )
        check(match is not None, "鼎胜高校详情链接变化")
        assert match is not None
        tr = a.find_parent("tr")
        check(tr is not None, "鼎胜高校表格行缺失")
        assert tr is not None
        controls = tr.select("a.apply_job[data-id]")
        check(
            len(controls) == 1 and str(controls[0]["data-id"]) == match[1],
            "鼎胜高校目录与详情ID错配",
        )
        rows.append(
            {
                "id": match[1],
                "title": a.get_text(strip=True),
                "url": UNIVERSITY + "/job/view/id/" + match[1],
            }
        )
    check(bool(rows) and len({x["id"] for x in rows}) == len(rows), "鼎胜高校目录空白或重复ID")
    if not fair:
        counts = doc.select("[v-text-job-total]")
        check(
            len(counts) == 1 and counts[0].get_text(strip=True) == f"{len(rows)}个",
            "鼎胜高校总数与完整列表不符",
        )
    return rows


def school_detail(html: str, row: dict[str, str]) -> dict[str, str]:
    doc = BeautifulSoup(html, "html.parser")
    title = doc.select_one(".title-message .title")
    check(title is not None and title.get_text(strip=True) == row["title"], "鼎胜高校详情标题错配")
    employers = doc.select(f'.unit-info a[href="{EMPLOYER}"]')
    check(
        len(employers) == 1 and employers[0].get_text(strip=True) == COMPANY, "鼎胜高校详情雇主错配"
    )
    shares = doc.select(".share-link a.icon-qq[href]")
    check(len(shares) == 1, "鼎胜高校详情身份缺失")
    urls = parse_qs(urlsplit(str(shares[0]["href"])).query).get("url", [])
    check(
        len(urls) == 1
        and re.fullmatch(re.escape(row["url"]) + r"(?:/from_type/2/from_id/57024)?", urls[0])
        is not None,
        "鼎胜高校详情ID错配",
    )
    bodies = [
        n.select_one(".aContent")
        for n in doc.select(".details-mge")
        if (heading := n.select_one(".mge-title")) is not None
        and heading.get_text(strip=True) == "职位详情"
    ]
    check(len(bodies) == 1 and bodies[0] is not None, "鼎胜高校正文缺失")
    body = bodies[0]
    assert body is not None
    check(not body.select("img,a[href],iframe,object,embed"), "鼎胜高校正文含未处理附件")
    raw = body.get_text("\n", strip=True)
    check(bool(raw), "鼎胜高校正文为空")
    duties, requirements = split_sections(raw)
    information = doc.select_one(".title-message .education")
    check(information is not None, "鼎胜高校岗位属性缺失")
    assert information is not None
    attributes = [x.strip() for x in information.get_text(" ", strip=True).split("|") if x.strip()]
    check(
        len(attributes) == 3 and attributes[1] in {"全职", "不限"}, "鼎胜高校出现实习或未知岗位类型"
    )
    dates = re.findall(r"(\d{4}-\d{2}-\d{2})发布", doc.get_text(" ", strip=True))
    check(len(dates) == 1, "鼎胜高校发布日期缺失或重复")
    extras = [
        n.get_text(" ", strip=True)
        for n in doc.select("li")
        if n.get_text(" ", strip=True).startswith(("工作经验：", "需求专业："))
    ]
    check(len(extras) == 2, "鼎胜高校经验或专业要求字段缺失")
    check(
        "应届" in raw or "应届毕业生" in "\n".join(extras) or "管培生" in raw,
        "鼎胜高校岗位缺少应届/管培资格证据",
    )
    address = doc.select(".address-container > p")
    check(len(address) == 1, "鼎胜高校工作地址结构变化")
    return dict(
        duties=duties,
        requirements="\n".join(filter(None, [requirements, *extras])),
        published=dates[0],
        location=attributes[0],
        education=attributes[2],
        address=address[0].get_text(strip=True),
    )


class DingshengCampus(Adapter):
    name = "dingsheng-campus"
    host = "www.dingshengxincai.com"
    path = "/channels/31.html"
    scope_description = (
        "鼎胜官网完整混合目录逐项资格核对；武汉科大完整企业在招目录与校园招聘会集合一致"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        official = Scope(name="official-mixed-directory")
        self.result.scopes.append(official)
        seen: set[str] = set()
        html = await session.page.content()
        page, maximum = 1, None
        while True:
            rows, last = official_catalog(html, page)
            maximum = maximum or last
            check(maximum == last, "鼎胜官网翻页期间页数变化")
            for row in self.add_page(official, rows, seen, lambda x: x["id"]):
                try:
                    official_body(await session.request_html(row["url"], detail=True), row)
                    official.skipped_out_of_scope += 1
                except Exception as exc:
                    self.error(exc, row["id"])
                    if isinstance(exc, CrawlError) and exc.code in {
                        "request_budget",
                        "time_budget",
                        "access_denied",
                    }:
                        raise
            if page == last:
                official.expected = len(seen)
                official.terminal = True
                break
            page += 1
            html = await session.request_html(ROOT + f"/channels/31_{page}.html")
        await session.open(UNIVERSITY + EMPLOYER + "/tab/1")
        rows = school_catalog(await session.page.content())
        evidence = session.last_evidence
        fair_html = await session.request_html(UNIVERSITY + FAIR)
        fair = school_catalog(fair_html, fair=True)
        check(
            {(x["id"], x["title"]) for x in rows} == {(x["id"], x["title"]) for x in fair},
            "鼎胜高校企业目录与校园招聘会范围不一致",
        )
        scope = Scope(name="wust-company-346005", expected=len(rows))
        scope.evidence.extend([evidence, session.last_evidence])
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda x: x["id"]):
            try:
                reused = self.before_detail("job:" + row["id"], row, scope, evidence=evidence)
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                await session.open(row["url"])
                html = await session.page.content()
                session.snapshot("dingsheng-job-" + row["id"], html)
                values = school_detail(html, row)
                job = self.job(
                    row["id"],
                    title=row["title"],
                    source_url=row["url"],
                    work_type="校招",
                    **values,
                    field_sources={
                        "published": "高校岗位详情明确发布日期，不取招聘会日期或官网更新日期",
                        "deadline": "source_missing:岗位未披露截止日期",
                        "duties": "高校职位详情；无标题短正文保留原文，不虚构分段",
                        "requirements": "明确要求章节及详情专业/经验字段；原届别不改写",
                        "address": "岗位详情工作地址章节，非企业简介地址",
                        "education": "高校岗位详情摘要明确学历",
                        "location": "高校岗位详情摘要明确工作地点",
                    },
                )
                job.evidence.insert(0, evidence)
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
                    return
        scope.terminal = True
