"""Yili's public Hotjob campus catalog, restricted to headquarters jobs."""

from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.filtering import select
from job_crawler.models import Job, Scope


class GetRequester(Protocol):
    async def observed(self, needle: str) -> dict[str, Any]: ...

    async def request(self, url: str, *, detail: bool = False) -> dict[str, Any]: ...


class YiliHeadquarters(Adapter):
    name = "yili-headquarters"
    host = "yili.hotjob.cn"
    path = (
        "/wt/yili/web/templet1000/index/"
        "corpwebPosition1000yili!gotoPostListForAjax?brandCode=1&recruitType=1"
    )
    scope_description = "伊利官网 recruitType=1 全量校招；仅总部 2027 届正式岗位"

    async def harvest(self) -> None:
        requester = cast(GetRequester, self.session)
        observed = await requester.observed("/wt/yili/web/json/position/list")
        check(urlsplit(observed["url"]).hostname == self.host, "伊利列表接口域名改变")
        params = parse_qs(urlsplit(observed["url"]).query, keep_blank_values=True)
        check(params.get("recruitType") == ["1"], "伊利列表不是校招")
        check(params.get("page") == ["1"], "伊利列表不是第一页")
        check(params.get("brandCode") == ["1"], "伊利品牌编码改变")
        for key in (
            "positionType",
            "comPart",
            "sicCorpCode",
            "releaseTime",
            "projectId",
            "workPlace",
            "keyWord",
        ):
            check(params.get(key) == [""], f"伊利列表有未知筛选：{key}")
        scope = Scope(name="campus-headquarters")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        pages = 0
        row_size = 0
        while True:
            response = await requester.request(query(observed["url"], page=page))
            check(response.get("req_state") == 9200, "伊利列表业务失败")
            returned_page = int(response["page"])
            returned_pages = int(response["pageCount"])
            returned_size = int(response["rowSize"])
            total = int(response["rowCount"])
            check(returned_page == page, "伊利返回了错误页码")
            check(0 < returned_size <= 100 and 0 <= returned_pages <= 100, "伊利分页异常")
            if scope.expected is None:
                scope.expected = total
                pages = returned_pages
                row_size = returned_size
            check(
                (total, returned_pages, returned_size) == (scope.expected, pages, row_size),
                "伊利分页总量改变",
            )
            rows = self.add_page(scope, response["postList"], seen, lambda row: str(row["postId"]))
            evidence = self.session.last_evidence
            for row in rows:
                check(str(row.get("recruitType")) == "1", "伊利校招目录混入其他招聘类型")
                if text(row.get("orgName")) != "总部":
                    scope.skipped_out_of_scope += 1
                    continue
                check(text(row.get("deptOrgName")).startswith("总部"), "伊利总部岗位部门归属不明")
                title = text(row.get("postName"))
                if "2027届校招" not in title:
                    scope.skipped_out_of_scope += 1
                    continue
                check(
                    bool(text(row.get("workContent"))) and bool(text(row.get("serviceCondition"))),
                    "伊利总部岗位缺少正文",
                )
                job = self._job(row, evidence)
                self.result.jobs.append(job)
                if select(job, "all", self.as_of).reason == "expired":
                    scope.skipped_expired += 1
                else:
                    scope.details += 1
            if page >= pages:
                check(len(seen) == scope.expected, "伊利末页与目录总数不符")
                scope.terminal = True
                break
            check(len(rows) == row_size, "伊利分页提前结束")
            page += 1

    def _job(self, row: dict[str, Any], evidence: str) -> Job:
        post_id = str(row["postId"])
        job = self.job(
            post_id,
            title=text(row["postName"]),
            unit="总部",
            location=text(row.get("workPlace")),
            education=text(row.get("education")),
            category_raw=text(row.get("postType")),
            batch="2027届校招",
            duties=text(row.get("workContent")),
            requirements=text(row.get("serviceCondition")),
            published=text(row.get("publishDate")),
            deadline=text(row.get("endDate")),
            source_url=f"https://{self.host}{self.path}",
            field_sources={
                "duties": "postList[].workContent",
                "requirements": "postList[].serviceCondition",
                "published": "postList[].publishDate",
                "deadline": "postList[].endDate",
                "unit": "postList[].orgName=总部，deptOrgName以总部开头",
                "location": "postList[].workPlace；无省级路径则保留原文",
            },
        )
        job.evidence = [evidence]
        return job
