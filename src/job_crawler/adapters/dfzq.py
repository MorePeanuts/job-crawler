"""Orient Securities' observed legacy Moka campus empty catalog."""

import json
from typing import Any, cast

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.moka import decode
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://app.mokahr.com"
ENDPOINT = "/api/outer/ats-apply/website/jobs"
QUERY = {
    "limit": 15,
    "offset": 0,
    "siteId": 4928,
    "orgId": "dfzq",
    "site": "campus",
    "needStat": True,
}


def catalog(response: dict[str, Any]) -> int:
    check(response.get("code") == 0 and response.get("success") is True, "东方证券校园业务失败")
    data = response.get("data")
    check(isinstance(data, dict), "东方证券校园目录结构变化")
    assert isinstance(data, dict)
    stats, rows = data.get("jobStats"), data.get("jobs")
    check(isinstance(stats, dict) and isinstance(rows, list), "东方证券校园总数或数组缺失")
    assert isinstance(stats, dict) and isinstance(rows, list)
    total = stats.get("total")
    check(
        stats.get("orgId") == "dfzq" and type(total) is int and total >= 0,
        "东方证券校园租户或总数错配",
    )
    assert isinstance(total, int)
    check(len(rows) == min(15, total), "东方证券校园总数与页行数不一致")
    return total


class DfzqCampus(Adapter):
    name = "dfzq-campus"
    host = "app.mokahr.com"
    path = "/campus_apply/dfzq/4928#/jobs"
    ready_endpoints = (ENDPOINT,)
    scope_description = (
        "东方证券官网4928正式校园目录当前明确为空；未来非零详情须另验证，实习/社招排除"
    )

    async def harvest(self) -> None:
        check(self.source.url == ROOT + self.path, "东方证券须使用已验证的无筛选校园入口")
        browser = cast(BrowserSession, self.session)
        observed = await browser.observed_path(ENDPOINT)
        check(observed["url"] == ROOT + ENDPOINT, "东方证券校园接口路径错配")
        check(json.loads(observed["post_data"]) == QUERY, "东方证券校园请求带有筛选或租户变化")
        iv = await browser.page.evaluate("() => window.TurboApply?.data?.aesIv")
        first = catalog(decode(json.loads(observed["body"]), iv))
        scope = Scope(name="dfzq-campus-4928-all", expected=first)
        self.result.scopes.append(scope)
        scope.evidence.append(browser.last_evidence)
        if first:
            raise CrawlError(
                "unsupported_scope", "东方证券校园出现非零岗位，旧版分页与详情契约须先核验"
            )
        await browser.page.get_by_text("尚无任何相关职位", exact=True).wait_for(timeout=15000)
        repeated = catalog(decode(await self.session.request(ROOT + ENDPOINT, payload=QUERY), iv))
        check(repeated == first, "东方证券校园总数发生变化")
        scope.evidence.append(self.session.last_evidence)
        html = await browser.page.content()
        check("尚无任何相关职位" in html, "东方证券校园缺少明确空状态")
        scope.evidence.append(browser.snapshot("dfzq-campus-empty", html))
        scope.terminal = True
