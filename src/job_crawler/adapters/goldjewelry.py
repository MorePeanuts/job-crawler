"""China Gold Jewelry's explicitly empty, unfiltered campus directory."""

import re
from typing import cast
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession

HOST = "chnau99999.com"
ROOT = f"https://{HOST}/page/tiIndex"
ENTRY = f"https://{HOST}/page/social/1"
SEARCH = f"https://{HOST}/page/social/Search/1?profession=&province=&title=&pageNum=1"
COMPANY = "中国黄金集团黄金珠宝股份有限公司"
HEADERS = ["岗位名称", "职位类别", "工作地点", "详情"]


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def document(html: str) -> BeautifulSoup:
    doc = BeautifulSoup(html, "html.parser")
    check(f"版权所有：{COMPANY}" in doc.get_text(), "中国黄金珠宝招聘主体缺失或变化")
    return doc


def navigation(html: str) -> dict[str, str]:
    doc = document(html)
    cards = doc.select(".tab-box-li-2")
    check(len(cards) == 3, "中国黄金珠宝人才入口数量变化")
    result: dict[str, str] = {}
    for card in cards:
        titles = card.select(".tab-box-li-2-title")
        links = card.select("a[href]")
        check(len(titles) == len(links) == 1, "中国黄金珠宝入口标题/链接不唯一")
        label = clean(titles[0].get_text())
        check(label not in result, "中国黄金珠宝招聘类型重复")
        result[label] = urljoin(ROOT, str(links[0]["href"]))
    expected = {
        label: f"https://{HOST}/page/social/{i}"
        for i, label in enumerate(["社会招聘", "校园招聘", "门店招聘"])
    }
    check(result == expected, "中国黄金珠宝校园招聘类型或入口变化")
    return result


def empty_campus(html: str) -> None:
    doc = document(html)
    scripts = "\n".join(s.get_text() for s in doc.select("script:not([src])"))
    counts = re.findall(r"new\s+Paging\s*\(\s*\{\s*total\s*:\s*(\d+)\s*\}\s*\)", scripts)
    check(
        counts == ["0"] and len(re.findall(r"new\s+Paging\b", scripts)) == 1,
        "中国黄金珠宝目录非零或计数未知；非零详情尚未支持",
    )
    check(
        re.findall(r"\bvar\s+zhaopintype\s*=\s*(\d+)\s*;", scripts) == ["1"],
        "中国黄金珠宝响应不是校园类型1",
    )
    check(
        '"/page/social/Search/" + zhaopintype' in scripts
        and all(
            p in scripts for p in ['"?profession="', '"&province="', '"&title="', '"&pageNum="']
        ),
        "中国黄金珠宝公开搜索表单契约变化",
    )
    bodies = doc.select(".social-content")
    check(len(bodies) == 1, "中国黄金珠宝校园目录容器缺失或重复")
    body = bodies[0]
    children = body.find_all(recursive=False)
    check(
        [c.get("class") for c in children]
        == [["social-content-search"], ["social-content-table"], ["page"]],
        "中国黄金珠宝校园目录出现未知分支",
    )
    check(
        not body.select("a[href],img,iframe,object,embed,video,form,.social-content-table-tdata"),
        "中国黄金珠宝零目录出现岗位/附件/媒体",
    )
    tables = body.select(".social-content-table")
    check(
        len(tables) == 1
        and [clean(x.get_text()) for x in tables[0].select(".thead-li")] == HEADERS,
        "中国黄金珠宝岗位表头缺失或变化",
    )
    check(
        clean(tables[0].get_text(" ", strip=True)) == " ".join(HEADERS),
        "中国黄金珠宝零计数与实际岗位正文矛盾",
    )
    pagers = body.select(".paging")
    check(
        len(pagers) == 1 and re.sub(r"\s+", "", pagers[0].get_text()) == "1/0",
        "中国黄金珠宝源端计数与可见页码不一致",
    )
    selects = body.select("select")
    check(
        [s.get("id") for s in selects] == ["zhiweileibie", "gongzuodidian"],
        "中国黄金珠宝目录筛选维度变化",
    )
    for select in selects:
        options = select.select("option[selected]") or select.select("option")[:1]
        check(len(options) == 1 and options[0].get("value") == "", "中国黄金珠宝存在局部筛选")
    inputs = body.select("input")
    check(
        len(inputs) == 1
        and inputs[0].get("id") == "gangweimingcheng"
        and inputs[0].get("value", "") == "",
        "中国黄金珠宝关键词不为空",
    )


class GoldJewelryCampus(Adapter):
    name = "goldjewelry-campus"
    host = HOST
    path = "/page/tiIndex"
    scope_description = "中国黄金珠宝官网人才引进校园类型1完整空目录；非零详情尚未支持"

    async def harvest(self) -> None:
        check(self.source.url == ENTRY, "中国黄金珠宝来源须为已验证校园栏目")
        browser = cast(BrowserSession, self.session)
        nav = Scope(
            name="goldjewelry-recruitment-types", expected=3, listed=3, unique=3, unit="招聘类型"
        )
        campus = Scope(name="goldjewelry-campus-catalog", expected=0, unit="岗位")
        self.result.scopes.extend([nav, campus])
        check(browser.page.url == ROOT, "中国黄金珠宝人才入口发生跳转")
        links = navigation(await browser.page.content())
        nav.evidence.append(browser.last_evidence)
        nav.skipped_out_of_scope = 2
        for url in [links["校园招聘"], SEARCH]:
            await browser.open(url)
            check(browser.page.url == url, "中国黄金珠宝校园目录发生跳转")
            empty_campus(await browser.page.content())
            campus.evidence.append(browser.last_evidence)
        nav.details = 1
        nav.terminal = campus.terminal = True
        path = browser.output / "goldjewelry-campus-disposition.json"
        write_json(
            path,
            {
                "navigation": links,
                "checked": [ENTRY, SEARCH],
                "source_total": 0,
                "disposition": "校园类型1无筛选零目录；两响应计数与可见页码一致",
            },
        )
        campus.evidence.append(str(path))
