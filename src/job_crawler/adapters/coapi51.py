"""Two verified public 51job COAPI campaigns with explicit callback accounting."""

import asyncio
import json
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.campaign51 import apply_id, split_jobinfo
from job_crawler.adapters.platforms import check
from job_crawler.filtering import select
from job_crawler.models import Job, Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession

DETAIL_JS = """id => new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('COAPI detail timeout')), 20000);
  coapi.getJobDetail(id, value => {clearTimeout(timer);resolve(value)});
})"""
LIST_JS = """params => new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('COAPI list timeout')), 20000);
  coapi.getJobList(params, value => {clearTimeout(timer);resolve(value)});
})"""


class Coapi(Adapter):
    ctmid = ""

    async def detail(self, job_id: str) -> tuple[dict[str, Any], str]:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "前程无忧详情浏览器页面丢失")
        assert session.page is not None
        session.consume_request()
        await asyncio.sleep(session.config.delay)
        response = await session.page.evaluate(DETAIL_JS, job_id)
        check(
            isinstance(response, dict) and isinstance(response.get("resultbody"), dict),
            "前程无忧详情回调结构改变",
        )
        row = response["resultbody"]
        check(str(row.get("jobid")) == job_id, "前程无忧详情与目录 ID 不一致")
        check(str(row.get("ctmid")) == self.ctmid, "前程无忧详情租户 ID 不一致")
        check(bool(row.get("jobinfo")), "前程无忧岗位正文缺失")
        path = session.output / "coapi-details" / f"{job_id}.json"
        write_json(path, response)
        return row, str(path)

    def listing_job(self, key: str, row: dict[str, Any], *, deadline: str = "") -> Job:
        url = f"https://xyz.51job.com/external/apply.aspx?jobid={key}&ctmid={self.ctmid}"
        check(apply_id(url) == key, "前程无忧申请 ID 无效")
        return self.job(
            key,
            title=text(row.get("jobName") or row.get("jobname")),
            source_url=f"https://{self.host}{self.path}",
            apply_url=url,
            unit=text(row.get("coName") or row.get("coname")),
            location=text(row.get("workArea") or row.get("jobareaname")),
            education=text(row.get("degree") or row.get("degreefrom")),
            category_raw=text(row.get("funType") or row.get("funtype")),
            published=text(row.get("issueDate") or row.get("issuedate")),
            deadline=deadline,
        )

    def complete_job(
        self,
        key: str,
        listed: dict[str, Any],
        detail: dict[str, Any],
        evidence: str,
        list_evidence: str,
    ) -> Job:
        job = self.listing_job(key, detail, deadline=text(listed.get("validDate")))
        job.published = text(listed.get("issueDate") or detail.get("issuedate"))
        duties, requirements = split_jobinfo(str(detail["jobinfo"]))
        if not duties and not requirements:
            # This campaign also publishes unheaded descriptions. Preserve the
            # source text as duties; a separate requirement is not asserted.
            duties = text(detail["jobinfo"])
        check(bool(duties), "前程无忧详情缺少可辨认的岗位职责")
        job.duties = duties
        job.requirements = requirements
        job.location = text(detail.get("jobareaname") or detail.get("workareaname"))
        job.education = text(detail.get("degreefrom"))
        job.category_raw = text(detail.get("funtype"))
        job.visible = str(detail.get("status")) == "24"
        job.field_sources = {
            "duties": (
                "coapi.getJobDetail.resultbody.jobinfo:岗位职责"
                if requirements
                else "coapi.getJobDetail.resultbody.jobinfo:未分段正文"
            ),
            "requirements": (
                "coapi.getJobDetail.resultbody.jobinfo:任职要求/任职资格"
                if requirements
                else "source_missing:独立任职要求"
            ),
            "published": (
                "position_list.data.list[].issueDate"
                if listed.get("issueDate")
                else "coapi.getJobDetail.resultbody.issuedate"
            ),
            "deadline": "position_list.data.list[].validDate"
            if listed.get("validDate")
            else "source_missing",
        }
        job.evidence = [list_evidence, evidence]
        return job


class Nbhx(Coapi):
    name = "coapi-nbhx"
    host = "campus.51job.com"
    path = "/NBHX/job.html"
    ctmid = "8074390"
    scope_description = "宁波华翔公开校招 COAPI 全目录；单次大页、逐条岗位详情"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "宁波华翔职位页不存在")
        assert session.page is not None
        document = BeautifulSoup(await session.page.content(), "html.parser")
        cards = [str(item["data-job"]) for item in document.select(".jobtitle[data-job]")]
        check(bool(cards) and len(cards) == len(set(cards)), "宁波华翔职位卡片为空或 ID 重复")
        session.consume_request()
        response = await session.page.evaluate(
            LIST_JS,
            {
                "ctmid": self.ctmid,
                "pagesize": 2000,
                "functype": "",
                "jobarea": "",
                "degreefrom": "",
                "keyword": "",
            },
        )
        check(
            isinstance(response, dict) and isinstance(response.get("resultbody"), dict),
            "宁波华翔目录回调结构改变",
        )
        body = response["resultbody"]
        expected = int(body["totalnum"])
        rows = body["joblist"]
        check(0 < expected <= 2000 and len(rows) == expected, "宁波华翔目录存在未处理分页")
        check({str(row["jobid"]) for row in rows} == set(cards), "宁波华翔列表与页面卡片 ID 不一致")
        evidence = session.output / "coapi-list.json"
        write_json(evidence, response)
        session.last_evidence = str(evidence)
        scope = Scope(name="nbhx-all-jobs", expected=expected)
        scope.evidence.append(str(evidence))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        self.add_page(scope, rows, seen, lambda row: str(row["jobid"]))
        for row in rows:
            key = str(row["jobid"])
            try:
                check(str(row["ctmid"]) == self.ctmid, "宁波华翔目录租户错误")
                listing = self.listing_job(key, row)
                resolved = self.before_detail(
                    f"job:{key}", row, scope, listing, evidence=str(evidence)
                )
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                detail, detail_evidence = await self.detail(key)
                job = self.complete_job(key, row, detail, detail_evidence, str(evidence))
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True


class Cofco(Coapi):
    name = "coapi-cofco"
    host = "campus.51job.com"
    path = "/cofco/campus.html"
    ctmid = "8970513"
    ready_endpoints = ("https://be.51job.com/zhongliang/index.php/index/position_list",)
    scope_description = "中粮集团公开校招无筛选完整分页目录及逐条 COAPI 详情"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        observed = await self.session.observed("/zhongliang/index.php/index/position_list")
        check(
            observed["url"].endswith("/zhongliang/index.php/index/position_list"),
            "中粮目录接口改变",
        )
        from urllib.parse import parse_qs

        form_values = parse_qs(observed["post_data"], keep_blank_values=True)
        check(
            set(form_values) == {"pageIndex", "pageSize", "orgId", "degree", "workArea", "keyword"}
            and form_values["pageIndex"] == ["1"]
            and all(form_values[key] == [""] for key in ("orgId", "degree", "workArea", "keyword")),
            "中粮目录存在未清除的单位或字段筛选",
        )
        size = int(form_values["pageSize"][0])
        check(0 < size <= 100, "中粮分页大小异常")
        scope = Scope(name="cofco-all-organizations")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = (
                json.loads(observed["body"])
                if page == 1
                else await session.request(
                    observed["url"],
                    form={
                        "pageIndex": str(page),
                        "pageSize": str(size),
                        "orgId": "",
                        "degree": "",
                        "workArea": "",
                        "keyword": "",
                    },
                )
            )
            check(response.get("code") == "0000", "中粮岗位列表业务失败")
            data = response["data"]
            expected = int(data["total"])
            check(expected >= 0, "中粮目录总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "中粮翻页期间总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["jobId"]))
            list_evidence = self.session.last_evidence
            for row in rows:
                key = str(row["jobId"])
                try:
                    listing = self.listing_job(key, row, deadline=text(row.get("validDate")))
                    if select(listing, "all", self.as_of).reason == "expired":
                        listing.detail_mode = "listing_only"
                        self.result.jobs.append(listing)
                        scope.skipped_expired += 1
                        continue
                    resolved = self.before_detail(
                        f"job:{key}", row, scope, listing, evidence=list_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    detail, detail_evidence = await self.detail(key)
                    job = self.complete_job(key, row, detail, detail_evidence, list_evidence)
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "中粮分页提前为空")
            page += 1


class Scg(Coapi):
    name = "coapi-scg"
    host = "ideal.51job.com"
    path = "/scg/index4.html"
    ctmid = "4963893"
    scope_description = "上海建工校园招聘页筛选后可见的应届岗位全目录及 COAPI 详情"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "上海建工招聘页不存在")
        assert session.page is not None
        document = BeautifulSoup(await session.page.content(), "html.parser")
        cards = {
            parse_qs(urlsplit(str(anchor.get("href", ""))).query)["jobid"][0]
            for anchor in document.select('.xr a[href*="jobid="]')
        }
        check(bool(cards), "上海建工页面未显示应届岗位")
        session.consume_request()
        response = await session.page.evaluate(
            LIST_JS,
            {
                "ctmid": self.ctmid,
                "pagesize": "999",
                "poscode": "",
                "divid": "",
                "jobarea": "",
                "keyword": "",
                "jobid": "",
                "coid": "",
            },
        )
        check(
            isinstance(response, dict) and isinstance(response.get("resultbody"), dict),
            "上海建工目录回调结构改变",
        )
        body = response["resultbody"]
        all_rows = body["joblist"]
        total = int(body["totalnum"])
        check(0 < total <= 999 and len(all_rows) == total, "上海建工无筛选目录不完整")
        rows = [row for row in all_rows if "应届" in text(row.get("jobname"))]
        check({str(row["jobid"]) for row in rows} == cards, "上海建工页面卡片与应届目录不一致")
        evidence = session.output / "coapi-list.json"
        write_json(evidence, response)
        session.last_evidence = str(evidence)
        scope = Scope(name="scg-visible-graduate", expected=len(rows))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        self.add_page(scope, rows, seen, lambda row: str(row["jobid"]))
        for row in rows:
            key = str(row["jobid"])
            try:
                check(str(row["ctmid"]) == self.ctmid, "上海建工目录租户错误")
                listing = self.listing_job(key, row)
                listing.source_url = f"https://{self.host}/scg/job1.html?jobid={key}"
                resolved = self.before_detail(
                    f"job:{key}", row, scope, listing, evidence=str(evidence)
                )
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                detail, detail_evidence = await self.detail(key)
                job = self.complete_job(key, row, detail, detail_evidence, str(evidence))
                job.source_url = listing.source_url
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True


TENANTS = (Nbhx, Cofco, Scg)
