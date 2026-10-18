"""Huishang Bank's current campus channel with an explicit empty-state contract."""

from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession

ROOT = "https://rczp.hsbank.com.cn"
ENTRY = ROOT + "/pc/"
CHANNEL = "/api/api/wtdf/json/channel"
LIST = "/api/job/wtdf/json/wcms/infoList"
CHANNEL_FORM = {"channelCode": "xyzp60682", "siteCode": "job"}
LIST_FORM = {"channelName": "校园招聘", **CHANNEL_FORM, "pageSize": "5"}
EMPTY = "对应的栏目目前没有招聘信息，敬请期待"


def business(data: dict[str, Any]) -> dict[str, Any]:
    check(data.get("errCode") == 0 and type(data.get("errCode")) is int, "徽商银行业务请求失败")
    body = data.get("data")
    check(isinstance(body, dict), "徽商银行公开接口data结构变化")
    assert isinstance(body, dict)
    return body


def channel(data: dict[str, Any]) -> None:
    body = business(data)
    check(
        body.get("name") == "校园招聘" and body.get("code") == "xyzp60682", "徽商银行校园栏目错配"
    )
    check(body.get("children") == [], "徽商银行校园栏目出现未遍历子树")
    check(
        all(body.get(k) is False for k in ("ref", "outLink", "innerLink")),
        "徽商银行校园栏目出现引用/跳转",
    )
    check(body.get("homeUrl") == body.get("listUrl") == "#", "徽商银行校园入口链接变化")


def empty_list(data: dict[str, Any]) -> None:
    body = business(data)
    check(
        set(body) == {"pageSize", "currentPage", "pageCount", "rowCount", "data"},
        "徽商银行校园分页字段变化",
    )
    check(
        all(type(body[k]) is int for k in ("pageSize", "currentPage", "pageCount", "rowCount")),
        "徽商银行校园计数不是整数",
    )
    check(
        body == {"pageSize": 5, "currentPage": 1, "pageCount": 1, "rowCount": 0, "data": []},
        "徽商银行校园非明确空目录，须实现公告详情后接入",
    )


def empty_dom(html: str) -> None:
    doc = BeautifulSoup(html, "html.parser")
    check("版权所有徽商银行" in doc.get_text(), "徽商银行招聘站主体缺失")
    sections = doc.select("#xyzp")
    check(len(sections) == 1, "徽商银行校园DOM区块缺失或重复")
    title = sections[0].select_one(".entirety-headline")
    notices = sections[0].select(".noList")
    check(title is not None and title.get_text(strip=True) == "校园招聘", "徽商银行校园DOM标题错配")
    check(
        len(notices) == 1 and notices[0].get_text(strip=True) == "暂无最新招聘公告",
        "徽商银行校园DOM不是明确空状态",
    )
    check(not sections[0].select("a[href],.el-pagination"), "徽商银行空校园区出现其他目录入口")


def observed_forms(responses: list[dict[str, Any]]) -> None:
    for endpoint, expected in ((CHANNEL, CHANNEL_FORM), (LIST, LIST_FORM)):
        matches = []
        for row in responses:
            if urlsplit(row["url"]).path != endpoint or row.get("status") != 200:
                continue
            form = parse_qs(row.get("post_data") or "", keep_blank_values=True)
            if form.get("channelCode") == ["xyzp60682"]:
                matches.append(form)
        check(
            bool(matches) and all(x == {k: [v] for k, v in expected.items()} for x in matches),
            "徽商银行未观察到无筛选校园请求",
        )


class HsbankCampus(Adapter):
    name = "hsbank-campus"
    host = "rczp.hsbank.com.cn"
    path = "/pc/"
    ready_endpoints = (CHANNEL, LIST)
    scope_description = (
        "徽商银行现行统一校园招聘栏目xyzp60682；不含社会招聘/实习；本版只接受完整明确零公告状态"
    )

    async def harvest(self) -> None:
        check(self.source.url == ENTRY, "徽商银行来源须为已验证的现行官方招聘平台")
        browser = cast(BrowserSession, self.session)
        scope = Scope(name="hsbank-current-campus", unit="校园公告")
        self.result.scopes.append(scope)
        await browser.observed_path(CHANNEL)
        await browser.observed_path(LIST)
        observed_forms(browser.responses)
        empty_dom(await browser.page.content())
        scope.evidence.append(browser.last_evidence)
        metadata = await browser.request(ROOT + CHANNEL, form=CHANNEL_FORM)
        channel(metadata)
        scope.evidence.append(browser.last_evidence)
        data = await browser.request(ROOT + LIST, form=LIST_FORM)
        empty_list(data)
        scope.evidence.append(browser.last_evidence)
        await browser.page.get_by_text("校园招聘", exact=True).first.click(timeout=10000)
        await browser.page.get_by_text(EMPTY, exact=True).wait_for(state="visible", timeout=10000)
        html = await browser.page.content()
        empty_dom(html)
        scope.evidence.append(browser.snapshot("hsbank-campus-empty", html))
        scope.expected = 0
        scope.terminal = True
        # Retain only the non-sensitive business proof in a compact artifact.
        proof = {"channel": "xyzp60682", "counts": business(data), "visible_message": EMPTY}
        path = browser.output / "hsbank-campus-counts.json"
        write_json(path, proof)
        scope.evidence.append(str(path))
