"""SAS Dragon's complete experienced-hire notice, not synthetic job rows."""

import hashlib
import re
from typing import cast
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession

ENTRY = "https://sasdragon.com.cn/article.php?AId=5"
SEMANTIC_HASH = "cde8fffebcef59bc143164f9f1c1d9548bebb52a18488b96b942f3e84317b9af"
FUNCTIONS = [
    "Sales and Marketing",
    "Research and Development",
    "Administration",
    "Accounting",
    "Logistics",
]


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def notice(html: str) -> dict[str, object]:
    doc = BeautifulSoup(html, "html.parser")
    page = clean(doc.get_text(" ", strip=True))
    check("S.A.S. Dragon Holdings Ltd." in page and "Stock Code:1184" in page, "时捷招聘主体变化")
    titles = doc.select(".detail .title")
    check(len(titles) == 1 and clean(titles[0].get_text()) == "Careers", "时捷招聘栏目标题缺失")
    bodies = doc.select(".detail .del")
    check(len(bodies) == 1, "时捷招聘说明缺失或不唯一")
    body = bodies[0]
    check(not body.select("img,iframe,object,embed,video,form"), "时捷招聘说明出现未支持媒体/表单")
    check(
        not doc.select('[class*="pager"],[class*="pagination"],.load-more'), "时捷招聘栏目出现分页"
    )
    for anchor in doc.select("a[href]"):
        label = clean(anchor.get_text(" ", strip=True))
        if re.search(r"careers?|jobs?|recruit|graduate|校园|校園|招聘", label, re.I):
            check(urljoin(ENTRY, str(anchor["href"])) == ENTRY, "时捷页面出现另一个招聘入口")
    value = clean(body.get_text(" ", strip=True))
    urls = [str(a["href"]) for a in body.select("a[href]")]
    check(len(urls) == 1 and urls[0].startswith("mailto:"), "时捷说明出现职位或附件链接")
    check("high caliber and well-experienced people" in value, "时捷招聘经验要求改变")
    check(
        not re.search(r"graduate|entry[- ]level|internship|应届|應屆|校招|實習|实习", value, re.I),
        "时捷出现应届/实习招聘内容",
    )
    directions = [
        clean(x).removeprefix("· ")
        for strong in body.select("strong")
        for x in strong.get_text("\n", strip=True).splitlines()
    ]
    check(directions == FUNCTIONS, "时捷招聘职能方向变化")
    digest = hashlib.sha256((value + "\n" + "\n".join(urls)).encode()).hexdigest()
    check(digest == SEMANTIC_HASH, "时捷招聘全文变化，需重新核验校招范围")
    return {
        "url": ENTRY,
        "text": value,
        "links": urls,
        "functions": directions,
        "semantic_sha256": digest,
        "disposition": "明确有经验人员招聘说明；五职能不是五条校园岗位",
    }


class SasDragonCareers(Adapter):
    name = "sasdragon-careers"
    host = "sasdragon.com.cn"
    path = "/article.php?AId=5"
    scope_description = (
        "时捷集团官网统一Careers公开招聘说明；不推定附属公司独立系统；当前明确面向有经验人员"
    )

    async def harvest(self) -> None:
        check(self.source.url == ENTRY, "时捷来源须为已验证的官方Careers栏目")
        browser = cast(BrowserSession, self.session)
        scope = Scope(
            name="sasdragon-careers-notice", unit="招聘说明", expected=1, listed=1, unique=1
        )
        self.result.scopes.append(scope)
        check(browser.page.url == ENTRY, "时捷招聘入口发生跳转")
        record = notice(await browser.page.content())
        scope.evidence.append(browser.last_evidence)
        p = browser.output / "sasdragon-notice-disposition.json"
        write_json(p, record)
        scope.evidence.append(str(p))
        scope.skipped_out_of_scope = 1
        scope.terminal = True
