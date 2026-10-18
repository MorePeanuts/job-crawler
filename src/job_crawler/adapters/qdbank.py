"""Qingdao Bank public directories; protected details remain explicitly blocked."""

import json
from copy import deepcopy
from typing import Any, cast
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Collection, Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://ehr.qdboffice.com:7000"
CAMPUS = ROOT + "/TalentRecruit/campus-recruitment"
NEWS = ROOT + "/TalentRecruit/latest-news"
API = ROOT + "/api/ciic-ihr-rcr-service/rcr-positionLibrary/"
LIST = API + "query-rcr-door-list"
ANNOUNCEMENTS = API + "query-rcr-anno-list"
QUERY = {
    "page": 1,
    "limit": 10,
    "total": 0,
    "filters": [],
    "condition": {
        "reqType": "P3528000002",
        "plName": "",
        "plType": [],
        "dept": [],
        "workExp": [],
    },
    "orders": [],
}
NEWS_QUERY = {**QUERY, "condition": {"plName": ""}}


def observed_body(observed: dict[str, Any], endpoint: str, payload: dict[str, Any]) -> Any:
    check(observed.get("url") == endpoint, "青岛银行目录接口身份改变")
    check(
        json.loads(observed["post_data"]) == payload,
        "青岛银行目录存在局部筛选或请求参数变化",
    )
    return json.loads(observed["body"])


def catalog(response: Any, page: int) -> tuple[int, list[dict[str, Any]]]:
    check(isinstance(response, dict) and response.get("code") == "0", "青岛银行目录业务失败")
    data = response.get("data")
    check(isinstance(data, dict), "青岛银行目录数据结构变化")
    total, rows = data.get("total"), data.get("records")
    check(
        type(total) is int
        and total >= 0
        and type(data.get("current")) is int
        and data["current"] == page
        and type(data.get("size")) is int
        and data["size"] == 10
        and type(data.get("pages")) is int
        and data["pages"] == (total + 9) // 10
        and isinstance(rows, list)
        and all(isinstance(row, dict) for row in rows),
        "青岛银行页码、大小、总数或目录结构异常",
    )
    assert isinstance(total, int) and isinstance(rows, list)
    check(len(rows) == min(10, max(0, total - (page - 1) * 10)), "青岛银行分页缺行或提前为空")
    return total, rows


class QdbankCampus(Adapter):
    name = "qdbank-campus"
    host = "ehr.qdboffice.com"
    path = "/TalentRecruit/campus-recruitment"
    scope_description = (
        "青岛银行全部公开校园职位及最新动态；当前两目录为零，非零详情需登录则明确受阻"
    )
    ready_endpoints = (LIST,)

    async def collect(self) -> Collection:
        try:
            parts = urlsplit(self.source.url)
            check(
                parts.scheme == "https"
                and parts.netloc == "ehr.qdboffice.com:7000"
                and parts.path == self.path
                and not parts.query
                and not parts.fragment,
                "青岛银行校园入口、端口或筛选参数变化",
            )
            await self.session.open(CAMPUS, ready_endpoints=self.ready_endpoints)
            await self.harvest()
        except Exception as exc:
            self.error(exc)
        return self.result

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        observed = await self.session.observed(LIST)
        response = observed_body(observed, LIST, QUERY)
        listing_evidence = self.session.last_evidence
        html = await browser.page.content()
        document = BeautifulSoup(html, "html.parser")
        check(
            text(document.select_one(".menuList .active")) == "校园招聘"
            and "青岛银行招聘门户" in text(document),
            "青岛银行校园页面或主体不符",
        )
        scope = Scope(name="qdbank-campus-all-departments")
        self.result.scopes.append(scope)
        scope.evidence.append(browser.snapshot("qdbank-campus", html))
        page = 1
        seen: set[str] = set()
        while True:
            total, rows = catalog(response, page)
            if scope.expected is None:
                scope.expected = total
            check(total == scope.expected, "青岛银行分页期间总数变化")
            scope.evidence.append(listing_evidence)
            if total == 0:
                check(
                    text(document.select_one(".nodata")) == "暂无职位",
                    "青岛银行零目录缺少校园页面空状态证据",
                )
            for row in self.add_page(scope, rows, seen, lambda item: text(item.get("id"))):
                check(bool(text(row.get("plName"))), "青岛银行目录岗位名称缺失")
                self.error(
                    CrawlError(
                        "auth_required",
                        "青岛银行非零校园职位详情要求登录，未取得职责和条件；未调用受保护接口",
                    ),
                    text(row["id"]),
                )
            if len(seen) == total:
                scope.terminal = True
                break
            page += 1
            payload = deepcopy(QUERY)
            payload.update(page=page, total=total)
            response = await self.session.request(LIST, payload=payload)
            listing_evidence = self.session.last_evidence

        # A new announcement may add jobs outside the position list. Do not ignore it.
        await browser.page.get_by_text("最新动态", exact=True).click(timeout=10000)
        await browser.page.wait_for_function(
            "() => location.pathname === '/TalentRecruit/latest-news' && "
            "document.querySelector('.menuList .active')?.innerText.trim() === '最新动态'",
            timeout=10000,
        )
        check(browser.page.url == NEWS, "青岛银行公告导航跳转异常")
        browser.url = NEWS
        observed = await self.session.observed(ANNOUNCEMENTS)
        response = observed_body(observed, ANNOUNCEMENTS, NEWS_QUERY)
        evidence = self.session.last_evidence
        news_html = await browser.page.content()
        news_document = BeautifulSoup(news_html, "html.parser")
        check(
            text(news_document.select_one(".menuList .active")) == "最新动态"
            and "青岛银行招聘门户" in text(news_document),
            "青岛银行公告页面或主体不符",
        )
        news = Scope(name="qdbank-public-announcements", unit="公告")
        self.result.scopes.append(news)
        news.evidence.extend([evidence, browser.snapshot("qdbank-news", news_html)])
        total, rows = catalog(response, 1)
        news.expected = total
        news.listed = len(rows)
        check(total == 0, "青岛银行出现公开公告，需核对正文和招聘范围后才能完成验收")
        news.terminal = True
