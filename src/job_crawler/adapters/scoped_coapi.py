"""Public campaign filters with explicit entity and campus project boundaries."""

import asyncio
import re
from typing import Any, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import text
from job_crawler.adapters.coapi51 import LIST_JS, Coapi
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession


class ScopedCoapi(Coapi):
    host = "campus.51job.com"
    codes: tuple[str, ...] = ()
    page_size = 10

    async def validate_page(self, document: BeautifulSoup) -> None:
        raise NotImplementedError

    def include(self, row: dict[str, Any], code: str) -> bool:
        return str(row.get("poscode")) == code

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        await self.validate_page(BeautifulSoup(await session.page.content(), "html.parser"))
        page_evidence = session.last_evidence
        completed: dict[str, Job] = {}
        for code in self.codes:
            try:
                await self.catalog(code, page_evidence, completed)
            except Exception as exc:
                self.error(exc, code)

    async def catalog(self, code: str, page_evidence: str, completed: dict[str, Job]) -> None:
        session = cast(BrowserSession, self.session)
        scope = Scope(name=f"poscode-{code}", evidence=[page_evidence])
        self.result.scopes.append(scope)
        page = 1
        seen: set[str] = set()
        while True:
            session.consume_request()
            await asyncio.sleep(session.config.delay)
            response = await session.page.evaluate(
                LIST_JS,
                {
                    "ctmid": self.ctmid,
                    "pagesize": self.page_size,
                    "pagenum": page,
                    "poscode": code,
                    "jobarea": "",
                    "keyword": "",
                },
            )
            check(str(response.get("status")) == "1", "校园 COAPI 目录业务失败")
            body = response["resultbody"]
            count = int(body["totalnum"])
            check(count >= 0, "校园 COAPI 目录总数无效")
            if scope.expected is None:
                scope.expected = count
            check(scope.expected == count, "校园 COAPI 分页期间总数变化")
            evidence = session.output / f"poscode-{code}-page-{page}.json"
            write_json(evidence, response)
            session.last_evidence = str(evidence)
            rows = self.add_page(scope, body["joblist"], seen, lambda r: str(r["jobid"]))
            check(len(rows) <= self.page_size, "校园 COAPI 返回超大页")
            for row in rows:
                key = str(row["jobid"])
                try:
                    check(str(row.get("ctmid")) == self.ctmid, "校园 COAPI 租户错配")
                    if not self.include(row, code):
                        scope.skipped_out_of_scope += 1
                        continue
                    if key in completed:
                        check(completed[key].title == text(row["jobname"]), "重复岗位标题不一致")
                        completed[key].evidence.append(str(evidence))
                        scope.reused_details += 1
                        continue
                    listing = self.listing_job(key, row)
                    cached = self.before_detail(key, row, scope, listing, evidence=str(evidence))
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        if len(cached) == 1:
                            completed[key] = cached[0]
                        continue
                    detail, detail_evidence = await self.detail(key)
                    check(
                        text(detail["jobname"]) == text(row["jobname"]), "校园 COAPI 详情标题错配"
                    )
                    check(str(detail.get("status")) in {"24", "0"}, "校园 COAPI 详情状态未知")
                    job = self.complete_job(key, row, detail, detail_evidence, str(evidence))
                    self.result.jobs.append(job)
                    completed[key] = job
                    scope.details += 1
                    self.remember(key, row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if scope.unique >= count:
                scope.terminal = True
                break
            check(bool(rows), "校园 COAPI 分页提前为空")
            page += 1


class KsfCampus(ScopedCoapi):
    name = "coapi-ksf-campus"
    path = "/ksf/job.html"
    ctmid = "8861224"
    codes = tuple(f"{kind}{project}" for kind in range(1, 9) for project in ("a", "aa"))
    scope_description = "康师傅全部八类应届生与管培生校园岗位；排除实习生项目，不限事业部"

    async def validate_page(self, document: BeautifulSoup) -> None:
        values: set[str] = set()
        for item in document.select("a[rel]"):
            rel = item.get("rel")
            if rel:
                values.add(rel if isinstance(rel, str) else rel[0])
        check(values >= {"a", "aa", "b", *map(str, range(1, 9))}, "康师傅项目或类别筛选变化")
        check(
            re.search(r'ctmid:\s*["\']8861224["\']', str(document)) is not None,
            "康师傅租户配置变化",
        )

    def include(self, row: dict[str, Any], code: str) -> bool:
        value = str(row.get("poscode", ""))
        match = re.fullmatch(r"[A-G]?([1-8])(aa|a|b)", value)
        check(match is not None, "康师傅岗位复合类别编码变化")
        assert match is not None
        return match[1] + match[2] == code


class BcdhListedCampus(ScopedCoapi):
    name = "coapi-bcdh-listed-campus"
    path = "/bcdh2026/post.html"
    ctmid = "7324087"
    codes = ("1",)
    page_size = 500
    scope_description = "首开2026官方校园门户仅首开股份 poscode=1；集团、房地、城运、城更板块排除"

    async def validate_page(self, document: BeautifulSoup) -> None:
        nodes = document.select('p[data-id="1"]')
        check(
            len(nodes) == 1 and nodes[0].get_text(strip=True) == "首开股份", "首开股份板块身份变化"
        )
        check(document.select_one('script[src="js/job.js"]') is not None, "首开岗位脚本变化")
        session = cast(BrowserSession, self.session)
        script = await session.request_html(
            f"https://{self.host}/bcdh2026/js/job.js", validate_html=False
        )
        check(re.search(r'ctmid:\s*["\']7324087["\']', script) is not None, "首开租户配置变化")

    def include(self, row: dict[str, Any], code: str) -> bool:
        check(str(row.get("poscode")) in {"1", "2", "3", "4", "5"}, "首开板块编码未知")
        return super().include(row, code)
