"""Verified classic Hotjob GET pagination with explicit tenant scope hooks."""

from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, query
from job_crawler.adapters.platforms import check
from job_crawler.filtering import select
from job_crawler.models import Job, Scope


class GetRequester(Protocol):
    async def observed(self, needle: str) -> dict[str, Any]: ...
    async def request(self, url: str, *, detail: bool = False) -> dict[str, Any]: ...


class ClassicHotjobCampus(Adapter):
    endpoint = ""
    catalog_scope = ""

    def in_scope(self, row: dict[str, Any]) -> bool:
        raise NotImplementedError

    def _job(self, row: dict[str, Any], evidence: str) -> Job:
        raise NotImplementedError

    async def harvest(self) -> None:
        requester = cast(GetRequester, self.session)
        observed = await requester.observed(self.endpoint)
        check(urlsplit(observed["url"]).hostname == self.host, "经典 Hotjob列表接口域名改变")
        params = parse_qs(urlsplit(observed["url"]).query, keep_blank_values=True)
        check(params.get("recruitType") == ["1"], "经典 Hotjob列表不是校招")
        check(params.get("page") == ["1"], "经典 Hotjob列表不是第一页")
        check(params.get("brandCode") == ["1"], "经典 Hotjob品牌编码改变")
        for key in (
            "positionType",
            "comPart",
            "sicCorpCode",
            "releaseTime",
            "projectId",
            "workPlace",
            "keyWord",
        ):
            check(params.get(key) == [""], f"经典 Hotjob列表有未知筛选：{key}")
        check(params.get("site", [""]) == [""], "经典 Hotjob 目录存在站点筛选")
        scope = Scope(name=self.catalog_scope)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        pages = 0
        row_size = 0
        while True:
            response = await requester.request(query(observed["url"], page=page))
            check(response.get("req_state") == 9200, "经典 Hotjob列表业务失败")
            returned_page = int(response["page"])
            returned_pages = int(response["pageCount"])
            returned_size = int(response["rowSize"])
            total = int(response["rowCount"])
            check(returned_page == page, "经典 Hotjob返回了错误页码")
            check(0 < returned_size <= 100 and 0 <= returned_pages <= 100, "经典 Hotjob分页异常")
            if scope.expected is None:
                scope.expected = total
                pages = returned_pages
                row_size = returned_size
            check(
                (total, returned_pages, returned_size) == (scope.expected, pages, row_size),
                "经典 Hotjob分页总量改变",
            )
            rows = self.add_page(scope, response["postList"], seen, lambda row: str(row["postId"]))
            evidence = self.session.last_evidence
            for row in rows:
                check(str(row.get("recruitType")) == "1", "经典 Hotjob校招目录混入其他招聘类型")
                if not self.in_scope(row):
                    scope.skipped_out_of_scope += 1
                    continue
                check(
                    "workContent" in row and "serviceCondition" in row, "经典 Hotjob 缺少正文字段"
                )
                job = self._job(row, evidence)
                self.result.jobs.append(job)
                if select(job, "all", self.as_of).reason == "expired":
                    scope.skipped_expired += 1
                else:
                    scope.details += 1
            if page >= pages:
                check(len(seen) == scope.expected, "经典 Hotjob末页与目录总数不符")
                scope.terminal = True
                break
            check(len(rows) == row_size, "经典 Hotjob分页提前结束")
            page += 1
