"""Observed empty LightBolt campus and announcement scopes for Ningbo Zhoushan Port."""

import json
from typing import cast
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://nbport.m.zhiye.com"
ENTRY = ROOT + "/#/jobs?jc=2"
INFO = "/LightBoltAPI/MainView/GetCompanyInfo"
SCOPES = (
    ("campus", "/#/jobs?jc=2", "/LightBoltAPI/JobAd/List"),
    ("activities", "/#/activity", "/LightBoltAPI/RecruitEvent/List"),
    ("notices", "/#/micro", "/LightBoltAPI/Message/List"),
)
QUERY = {
    "jc": "2",
    "jobads": "",
    "code": "",
    "c1": "",
    "c2": "",
    "ky": "",
    "c": "",
    "ct": "",
    "o": "",
    "rewardjob": "0",
    "shareid": "",
    "shopid": "",
    "From": "/jobs?jc=2",
}


def mapping(raw: object) -> dict[str, object]:
    check(isinstance(raw, dict), "宁波港响应对象结构变化")
    return cast(dict[str, object], raw)


def business(raw: object) -> object:
    obj = mapping(raw)
    check(
        obj.get("Code") == 200 and obj.get("RedirectUrl") is None and "Data" in obj,
        "宁波港公开请求业务失败或跳转",
    )
    return obj["Data"]


def identity(raw: object) -> None:
    obj = mapping(business(raw))
    check(
        obj.get("Title") == "宁波舟山港股份有限公司"
        and obj.get("TenantId") == 111157
        and obj.get("PortalId") == 11115700,
        "宁波港主体或租户变化",
    )


def count(raw: object, *, campus: bool) -> int:
    data = business(raw)
    if not campus:
        check(isinstance(data, list), "宁波港公告不是数组")
        assert isinstance(data, list)
        return len(data)
    obj = mapping(data)
    check(
        all(
            obj.get(k) == v for k, v in {"pi": "1", "ps": "10", "jc": "2", "rewardjob": "0"}.items()
        )
        and all(
            obj.get(k) == "" for k in ("c1", "c2", "ky", "c", "ct", "o", "jid", "code", "shopid")
        )
        and obj.get("JobAdId") is None,
        "宁波港校园响应有筛选或页码变化",
    )
    rows = mapping(obj.get("data"))
    total, items = rows.get("RowCount"), rows.get("DataResult")
    check(type(total) is int and total >= 0 and isinstance(items, list), "宁波港目录总数或数组缺失")
    assert isinstance(total, int) and isinstance(items, list)
    check(len(items) == min(total, 10), "宁波港首屏与总数不符")
    if total == 0:
        check(
            rows.get("PageCount") == 0
            and rows.get("PageSize") == 0
            and rows.get("CurPageSize") == 1,
            "宁波港空目录页数矛盾",
        )
    return total


class NbportCampus(Adapter):
    name = "nbport-campus"
    host = "nbport.m.zhiye.com"
    path = "/#/jobs?jc=2"
    ready_endpoints = (SCOPES[0][2],)
    scope_description = "宁波舟山港股份官方校园2及招聘活动/动态当前空目录；未来非零须另验收"

    async def harvest(self) -> None:
        check(self.source.url == ENTRY, "宁波港来源须为完整无筛选校园入口")
        browser = cast(BrowserSession, self.session)
        observed = await browser.observed_path(INFO)
        check(observed["url"] == ROOT + INFO, "宁波港公司身份接口错配")
        identity(json.loads(observed["body"]))
        identity_evidence = browser.last_evidence
        for index, (name, path, endpoint) in enumerate(SCOPES):
            scope = Scope(name="nbport-" + name, evidence=[identity_evidence])
            self.result.scopes.append(scope)
            try:
                if index:
                    await browser.open(ROOT + path, ready_endpoints=(endpoint,))
                check(browser.page.url == ROOT + path, "宁波港目录发生跳转")
                observed = await browser.observed_path(endpoint)
                parts = urlsplit(observed["url"])
                expected = QUERY if index == 0 else {"pageIndex": "1", "pageSize": "10"}
                check(
                    parts.scheme == "https"
                    and parts.netloc == self.host
                    and parts.path == endpoint
                    and parse_qs(parts.query, keep_blank_values=True)
                    == {k: [v] for k, v in expected.items()}
                    and not observed.get("post_data"),
                    "宁波港实际目录请求包含筛选或错路径",
                )
                total = count(json.loads(observed["body"]), campus=index == 0)
                scope.expected = total
                scope.evidence.append(browser.last_evidence)
                if total:
                    raise CrawlError("unsupported_scope", "宁波港出现岗位或公告，须核对正文和分页")
                repeated = count(await browser.request(observed["url"]), campus=index == 0)
                check(repeated == total, "宁波港重复查询总数变化")
                scope.evidence.append(browser.last_evidence)
                await browser.page.get_by_text("这里什么都没有...", exact=True).wait_for(
                    timeout=15000
                )
                scope.evidence.append(
                    browser.snapshot("nbport-" + name, await browser.page.content())
                )
                scope.terminal = True
            except Exception as exc:
                self.error(exc)
