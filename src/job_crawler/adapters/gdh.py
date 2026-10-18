"""GDH's legacy mobile campus catalog, including its server-side 100-row cap."""

import asyncio
import json
from datetime import date
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://gdhchina.m.zhiye.com"
ENTRY = ROOT + "/segment.html?jc=2"
ALL = ROOT + "/recruitment.html?c2=3_-1&k=all"
LIST = ROOT + "/JobAd/_SearchJobAd"
INFO = ROOT + "/JobAd/_Info"
QUERY = {
    "in": "1",
    "jc": "2",
    "ky": "",
    "c1": "-1",
    "c2": "3_-1",
    "c": "-1",
    "d": "-1",
    "pi": "1",
    "ps": "1000",
}
# Public commonautopage.js maps recruitment regions to presentation keys.
REGIONS = {
    "广东粤港投资开发有限公司": "ygt",
    "粤海置业投资(国际)有限公司": "yhzytzgj",
    "粤海投资有限公司": "yhtz",
    "广东粤海粤西供水有限公司": "yhyxgs",
    "广东粤海粤东供水有限公司": "yhydgs",
    "粤海永顺泰集团股份有限公司": "yhystjt",
    "广东省水利电力勘测设计研究院有限公司": "sldlkcsjyjy",
    "广东粤海珠三角供水有限公司": "yhzsjgs",
    "粤海广南（集团）有限公司": "yhgnjt",
    "广东粤海集团企业服务有限公司": "yhjtqyfw",
    "广东粤海水务股份有限公司": "yhsw",
    "广东粤港供水有限公司": "yggs",
    "粤海置地控股有限公司": "yhzd",
    "广东粤海天河城（集团）股份有限公司": "yhthc",
    "粤海资本集团有限公司": "yhzbjt",
}


def region(row: dict[str, Any], *, detail: bool = False) -> tuple[int, str]:
    items = row.get("Categories")
    check(
        isinstance(items, list) and all(isinstance(item, dict) for item in items),
        "粤海招聘区域结构变化",
    )
    assert isinstance(items, list)
    values = [item for item in items if item.get("TypeId") == 3]
    check(len(values) == 1, "粤海岗位缺少唯一招聘区域")
    item = values[0]
    ident = item.get("ConstValue" if detail else "CategoryId")
    name = text(item.get("ConstText" if detail else "CategoryName"))
    check(type(ident) is int and ident > 0 and bool(name), "粤海招聘区域身份缺失")
    return ident, name


def listed(row: dict[str, Any]) -> None:
    check(type(row.get("JobAdId")) is int and row["JobAdId"] > 0, "粤海岗位ID无效")
    check(row.get("TenantId") == 603372 and row.get("CategoryId") == 2, "粤海租户或校园类型变化")
    check(
        (row.get("KindId"), row.get("KindName")) in {(1, "全职"), (3, "实习")}, "粤海工作性质未知"
    )
    check(
        bool(text(row.get("JobAdName"))) and bool(text(row.get("Department"))),
        "粤海标题或招聘子单位缺失",
    )
    region(row)
    date.fromisoformat(row["ToPostDate"])


def detail_url(row: dict[str, Any]) -> str:
    return (
        ROOT
        + "/details.html?"
        + urlencode(
            {
                "adId": row["JobAdId"],
                "jc": 2,
                "k": REGIONS.get(region(row)[1], ""),
                "fgs": 0,
                "c2": "3_-1",
            }
        )
    )


def fields(row: dict[str, Any], detail: dict[str, Any]) -> dict[str, str]:
    for key in ("TenantId", "JobAdId", "JobAdName", "Department"):
        check(detail.get(key) == row.get(key), f"粤海详情{key}与列表不一致")
    check(
        detail.get("Kind") == row["KindId"] and detail.get("KindName") == row["KindName"],
        "粤海详情工作性质不符",
    )
    check(region(detail, detail=True) == region(row), "粤海详情招聘区域不符")
    check(detail.get("PostDateStr") == row["ToPostDate"], "粤海详情发布日期不符")
    for name in ("DutyStr", "RequireStr"):
        check(isinstance(detail.get(name), str), f"粤海缺少{name}正文")
        document = BeautifulSoup(detail[name], "html.parser")
        check(
            not document.select("img, iframe, object, embed, a[href]"),
            "粤海正文包含未解析附件或外链",
        )
    deadline = text(detail.get("EndTimeStr"))
    if row.get("ToEndDate") == "2222-02-02":
        check(deadline == "-", "粤海截止哨兵不一致")
        deadline = ""
    else:
        date.fromisoformat(deadline)
        check(deadline == row.get("ToEndDate"), "粤海截止日期不一致")
    return {
        "title": text(detail["JobAdName"]),
        "unit": text(detail["Department"]),
        "location": text(detail.get("LocName")),
        "education": text(detail.get("DegreeStr")),
        "address": text(detail.get("DetailAddress")),
        "duties": text(detail["DutyStr"]),
        "requirements": text(detail["RequireStr"]),
        "published": detail["PostDateStr"],
        "deadline": deadline,
        "category_raw": text(row.get("Class1Name")).removeprefix("职位类型:"),
    }


class GdhMobileCampus(Adapter):
    name = "gdh-mobile-campus"
    host = "gdhchina.m.zhiye.com"
    path = "/segment.html?jc=2"
    scope_description = "粤海集团五业务板块全部校园目录jc=2/c2=3_-1；保留招聘子单位，排除实习"

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        html = await browser.page.content()
        doc = BeautifulSoup(html, "html.parser")
        links = {text(a): urljoin(ENTRY, str(a.get("href", ""))) for a in doc.select("a[href]")}
        check(links.get("全部职位") == ALL, "粤海全部职位入口变化")
        for label in ("集团总部", "水务环境", "城建运营", "食品生物", "产业投资"):
            check(
                label in links and links[label].startswith(ROOT + "/recruitment.html?"),
                "粤海板块目录不完整",
            )
        root_evidence = browser.snapshot("gdh-campus-segments", html)
        await self.session.open(ALL, ready_endpoints=(LIST,))
        observed = await self.session.observed(LIST)
        parts = urlsplit(observed["url"])
        check(parts.scheme + "://" + parts.netloc + parts.path == LIST, "粤海目录接口改变")
        check(
            parse_qs(parts.query, keep_blank_values=True) == {k: [v] for k, v in QUERY.items()},
            "粤海目录存在局部筛选或非校园类型",
        )
        html = await browser.page.content()
        check("校园招聘岗位" in text(BeautifulSoup(html, "html.parser")), "粤海页面未确认校园范围")
        scope = Scope(
            name="gdh-all-campus-regions",
            evidence=[root_evidence, browser.snapshot("gdh-campus-all", html)],
        )
        self.result.scopes.append(scope)
        rows: list[tuple[dict[str, Any], str]] = []
        seen: set[str] = set()
        first = json.loads(observed["body"])
        check(type(first.get("RowCount")) is int and first["RowCount"] >= 0, "粤海初始总数无效")
        scope.expected = first["RowCount"]
        check(scope.expected <= 20000, "粤海目录超过分页预算")
        for page in range(1, (scope.expected + 99) // 100 + 2):
            response = await self.session.request(query(LIST, **{**QUERY, "pi": page, "ps": 100}))
            items, total = response.get("DataResult"), response.get("RowCount")
            check(
                isinstance(items, list) and all(isinstance(item, dict) for item in items),
                "粤海列表结构变化",
            )
            assert isinstance(items, list)
            expected = min(100, max(0, scope.expected - (page - 1) * 100))
            check(len(items) == expected, "粤海分页缺行或末页仍有数据")
            check(
                type(total) is int and total == (scope.expected if items else 0), "粤海分页总数变化"
            )
            if not items:
                if not seen:
                    check(
                        "暂无" in text(BeautifulSoup(html, "html.parser")),
                        "粤海零目录缺少明确页面空状态",
                    )
                scope.evidence.append(self.session.last_evidence)
                scope.terminal = True
                break
            for row in self.add_page(scope, items, seen, lambda item: str(item.get("JobAdId", ""))):
                listed(row)
                rows.append((row, self.session.last_evidence))
        check(len(seen) == scope.expected and scope.terminal, "粤海完整目录未核对")
        # The first observed screen must agree with the first page we traversed.
        check(
            [x[0]["JobAdId"] for x in rows[:100]] == [x["JobAdId"] for x in first["DataResult"]],
            "粤海初始目录与分页不一致",
        )
        detail_endpoint = ""
        lock = asyncio.Lock()
        limit = asyncio.Semaphore(3)
        abort: CrawlError | None = None

        async def read(row: dict[str, Any], evidence: str) -> None:
            nonlocal detail_endpoint, abort
            async with limit:
                if abort is not None:
                    return
                key = str(row["JobAdId"])
                try:
                    if row["KindId"] == 3:
                        scope.skipped_out_of_scope += 1
                        return
                    url = detail_url(row)
                    listing = self.job(
                        key,
                        title=row["JobAdName"],
                        source_url=url,
                        published=row["ToPostDate"],
                        deadline="" if row["ToEndDate"] == "2222-02-02" else row["ToEndDate"],
                    )
                    resolved = self.before_detail(
                        "job:" + key, row, scope, listing, evidence=evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        return
                    async with lock:
                        if not detail_endpoint:
                            await self.session.open(url, ready_endpoints=(INFO,))
                            info = await self.session.observed(INFO)
                            check(
                                info["url"] == query(INFO, adid=key, **{"in": 1}),
                                "粤海详情公开接口身份不符",
                            )
                            detail_endpoint = INFO
                    detail = await self.session.request(
                        query(detail_endpoint, adid=key, **{"in": 1}), detail=True
                    )
                    parsed = fields(row, detail)
                    job = self.job(
                        key,
                        **parsed,
                        work_type="校招",
                        source_url=url,
                        apply_url=url,
                        field_sources={
                            "duties": "_Info.DutyStr",
                            "requirements": "_Info.RequireStr",
                            "published": "_Info.PostDateStr，与列表ToPostDate核对",
                            "deadline": "_Info.EndTimeStr；2222-02-02与'-'为未知",
                            "unit": "_Info.Department；集团全部招聘区域下实际子单位",
                            "location": "_Info.LocName",
                            "address": "_Info.DetailAddress",
                        },
                    )
                    job.evidence = [evidence, self.session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember("job:" + key, row, [job])
                except Exception as exc:
                    self.error(exc, key)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "auth_required",
                        "time_budget",
                        "request_budget",
                    }:
                        abort = exc

        await asyncio.gather(*(read(row, evidence) for row, evidence in rows))
