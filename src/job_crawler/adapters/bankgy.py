"""Guiyang Bank's observed campus channel, using its ordinary search UI."""

import json
from typing import cast

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Collection, Scope
from job_crawler.transport import BrowserSession, CrawlError

ENTRY = "https://job.bankgy.com:7000/zp.html#/channel/01"
API = "https://job.bankgy.com:7000/ajax/ajaxService"
QUERY = [
    {"itemid": "z0321"},
    {"itemid": "z03aa", "value": ""},
    {"itemid": "z0351", "value": ""},
]
PUBLIC_FIELDS = (
    "functionId",
    "succeed",
    "hire_channel",
    "pageNum",
    "pageSize",
    "queryitem",
    "return_data",
)


def catalog(raw: object) -> tuple[int, dict[str, object]]:
    check(isinstance(raw, dict), "贵阳银行校园响应不是对象")
    assert isinstance(raw, dict)
    data = cast(dict[str, object], raw)
    check(
        data.get("functionId") == "ZP1000000001" and data.get("succeed") is True,
        "贵阳银行校园查询业务失败或响应错配",
    )
    check(
        data.get("hire_channel") == "01"
        and data.get("pageNum") == 1
        and data.get("pageSize") == 20
        and data.get("queryitem") == QUERY,
        "贵阳银行非校园频道或查询含筛选",
    )
    result = data.get("return_data")
    check(isinstance(result, dict), "贵阳银行目录结构变化")
    assert isinstance(result, dict)
    result = cast(dict[str, object], result)
    total, rows = result.get("posTotal"), result.get("position_data")
    check(type(total) is int and total >= 0 and isinstance(rows, list), "贵阳银行总数或数组缺失")
    assert isinstance(total, int) and isinstance(rows, list)
    check(len(rows) == min(20, total), "贵阳银行总数与首屏行数不一致")
    check(
        result.get("posMapKey") == ["需求单位`z0321"]
        and result.get("posMap")
        == {
            "需求单位`z0321": [
                {"hidden": False, "name": "不限", "check": True, "value": "z0321,需求单位,0"}
            ]
        },
        "贵阳银行需求单位筛选发生变化",
    )
    check(
        result.get("boardlist") == [] and result.get("batchList") == [],
        "贵阳银行存在尚未适配的校园公告或批次",
    )
    return total, {key: data[key] for key in PUBLIC_FIELDS}


class BankgyCampus(Adapter):
    name = "bankgy-campus"
    host = "job.bankgy.com"
    path = "/zp.html#/channel/01"
    scope_description = "贵阳银行官网校园频道01当前明确零岗位；未来非零分页详情须另验证"

    async def collect(self) -> Collection:
        try:
            check(self.source.url == ENTRY, "贵阳银行须使用已验证的7000端口校园入口")
            await self.session.open(ENTRY)
            await self.harvest()
        except Exception as exc:
            self.error(exc)
        return self.result

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        page = browser.page
        await page.get_by_text("搜索", exact=True).wait_for(timeout=30000)
        check(page.url == ENTRY, "贵阳银行校园页面发生跳转")
        check(
            await page.get_by_placeholder("职位名称、工作地点", exact=True).input_value() == "",
            "贵阳银行搜索关键词不是空值",
        )
        scope = Scope(name="bankgy-campus-01-all")
        self.result.scopes.append(scope)
        for index in range(2):
            async with page.expect_response(
                lambda response: response.url == API and response.request.method == "POST",
                timeout=25000,
            ) as response_info:
                await page.get_by_text("搜索", exact=True).click(timeout=10000)
            response = await response_info.value
            check(response.status == 200, "贵阳银行校园查询HTTP失败")
            total, public = catalog(await response.json())
            scope.evidence.append(
                browser.snapshot(
                    f"bankgy-campus-search-{index}", json.dumps(public, ensure_ascii=False)
                )
            )
            if index == 0:
                scope.expected = total
            check(total == scope.expected, "贵阳银行校园两次总数变化")
            if total:
                raise CrawlError("unsupported_scope", "贵阳银行校园出现岗位，分页和详情须先核验")
        await page.get_by_text("共0个职位", exact=True).wait_for(timeout=15000)
        await page.get_by_role("cell").get_by_text("暂无数据", exact=True).wait_for(timeout=15000)
        await page.get_by_text("校园招聘", exact=True).wait_for(timeout=15000)
        scope.evidence.append(browser.snapshot("bankgy-campus-empty", await page.content()))
        scope.terminal = True
