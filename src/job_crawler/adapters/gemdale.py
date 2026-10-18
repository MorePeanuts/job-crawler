"""Gemdale's currently empty campus scopes; future nonzero jobs fail explicitly."""

from hashlib import sha256
from typing import cast
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Collection, Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://gemdale.zhiye.com"
PLANS = {
    "31": ("金鹰计划", "jyjh"),
    "30": ("鸿鹄计划", "hhjh"),
    "29": ("新鹰生计划", "xjxysjh"),
    "28": ("弘鹄生计划", "tyhhsjh"),
}
INTRO_NAMES = {
    "jyjh": "金鹰计划",
    "hhjh": "鸿鹄计划",
    "tyhhsjh": "体育弘鹄生计划",
    "xjxysjh": "新家新鹰生计划",
}
INTRO_DIGESTS = {
    "jyjh": "ef278492583d97387c37073a9751b4e311da7bab7afe652f3d096cd2b8e5546b",
    "hhjh": "16b0a3c406de7abe9f6dddb1ed96a084a31d0381e95dc17d8f7f8b12b7c89dde",
    "tyhhsjh": "e17b92ddecf24d02b354a04e588d69ebda941622feb45f9dbac5f54cd32f717c",
    "xjxysjh": "77ca5771f47bdf3142502a2a3cb35123200d5d977b7db2ed01870d20e2bea967",
}


def search_url(category: str) -> str:
    return (
        ROOT
        + "/campus?"
        + urlencode(
            {
                "k": "",
                "c": "-1",
                "p": "1^-1,3^" + category,
                "day": "-1",
                "PageIndex": 1,
                "t": "",
                "class": 2,
            }
        )
        + "#zw"
    )


def document(html: str) -> BeautifulSoup:
    doc = BeautifulSoup(html, "html.parser")
    check(
        "金地（集团）股份有限公司 版权所有" in text(doc.select_one(".footer")), "金地招聘主体变化"
    )
    active = doc.select(".nav a.now")
    check(
        len(active) == 1 and active[0].get("href") == "/campus" and text(active[0]) == "校园招聘",
        "金地页面不是校园招聘",
    )
    categories = doc.select(".shax .categoryConditions")
    expected = [("3^-1", "全部")] + [("3^" + key, value[0]) for key, value in PLANS.items()]
    check(
        [(x.get("datavalue"), text(x)) for x in categories] == expected, "金地校园招聘计划集合变化"
    )
    menus = [dl for dl in doc.select(".shax dl") if text(dl.find("dt")) == "招聘计划介绍"]
    check(len(menus) == 1, "金地计划介绍导航缺失")
    links = [(urljoin(ROOT, str(a.get("href"))), text(a)) for a in menus[0].select("a[href]")]
    check(
        links == [(ROOT + "/" + path + "#zw", label) for path, label in INTRO_NAMES.items()],
        "金地计划介绍导航新增或变化",
    )
    return doc


def empty_catalog(html: str, category: str, scope: Scope) -> None:
    doc = document(html)
    for selector, value in (
        (".categoryConditions.act", "3^" + category),
        (".categoryConditions1.act", ""),
        (".citiesConditions.act", "-1"),
        (".dateConditions.act", "-1"),
    ):
        selected = doc.select(selector)
        check(
            len(selected) == 1 and selected[0].get("datavalue") == value,
            "金地校园目录存在局部筛选或类别错配",
        )
    keyword, kind = doc.select_one("#k"), doc.select_one("#ss")
    check(
        keyword is not None
        and keyword.get("value", "") == ""
        and kind is not None
        and kind.get("value") == "2",
        "金地搜索类型或关键词变化",
    )
    lists = doc.select(".zwlb")
    check(len(lists) == 1, "金地岗位目录缺失或不唯一")
    rows = lists[0].select(".job-li")
    if rows:
        scope.listed = len(rows)
        ids = [str(row.get("jobadid", "")) for row in rows]
        scope.unique = len(set(ids))
        check(
            all(key.isdigit() for key in ids) and scope.unique == scope.listed,
            "金地新增校园目录身份缺失或重复",
        )
        raise CrawlError("unsupported_scope", "金地出现非零校园岗位，需验证真实分页和详情契约")
    check(
        text(lists[0]) == "抱歉!暂无在招职位"
        and len(lists[0].select("li")) == 1
        and not lists[0].select("a[href],img,iframe,object,embed"),
        "金地校园目录不是明确零岗位状态",
    )


def empty_introduction(html: str, path: str) -> None:
    doc = document(html)
    blocks = doc.select(".jyjh")
    check(len(blocks) == 1 and not doc.select(".job-li,.zwlb"), "金地计划介绍新增职位目录")
    body = blocks[0]
    check(not body.select("a[href],iframe,object,embed,form,script"), "金地计划介绍新增入口或附件")
    fingerprint = (
        " ".join(body.stripped_strings)
        + "\n"
        + "\n".join(str(img["src"]) for img in body.select("img[src]"))
    )
    check(
        sha256(fingerprint.encode()).hexdigest() == INTRO_DIGESTS[path],
        "金地计划介绍文字或图片引用变化，需重新核对岗位范围",
    )


class GemdaleCampus(Adapter):
    name = "gemdale-campus"
    host = "gemdale.zhiye.com"
    path = "/campus"
    scope_description = "金地四计划校园目录及介绍当前明确零岗位；非零校园分页详情尚待验证"

    async def collect(self) -> Collection:
        if self.source.url.rstrip("/") != ROOT + self.path:
            self.error(CrawlError("entry_mismatch", "金地必须使用无筛选校园入口"))
            return self.result
        return await super().collect()

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        entry = await browser.page.content()
        for category in ["-1", *PLANS]:
            scope = Scope(name="gemdale-campus-" + category)
            self.result.scopes.append(scope)
            try:
                if category == "-1":
                    scope.evidence.append(browser.snapshot("gemdale-campus-entry", entry))
                    empty_catalog(entry, category, scope)
                await self.session.open(search_url(category))
                html = await browser.page.content()
                scope.evidence.append(browser.snapshot("gemdale-campus-" + category, html))
                empty_catalog(html, category, scope)
                scope.expected = 0
                scope.terminal = True
            except Exception as exc:
                self.error(exc, category)
        for path in INTRO_NAMES:
            scope = Scope(name="gemdale-introduction-" + path)
            self.result.scopes.append(scope)
            try:
                await self.session.open(ROOT + "/" + path + "#zw")
                html = await browser.page.content()
                scope.evidence.append(browser.snapshot("gemdale-introduction-" + path, html))
                empty_introduction(html, path)
                scope.expected = 0
                scope.terminal = True
            except Exception as exc:
                self.error(exc, path)
