"""Two verified public 51job COAPI campaigns with explicit callback accounting."""

import asyncio
import json
import re
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.campaign51 import apply_id, split_jobinfo
from job_crawler.adapters.platforms import check
from job_crawler.filtering import select
from job_crawler.models import Issue, Job, Scope
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


class Wanxiang(Coapi):
    name = "coapi-wanxiang-2027"
    host = "campus.51job.com"
    path = "/wxxz2027/about2.html"
    ctmid = "8019567"
    scope_description = "万向集团 2027 招聘计划 COAPI 无筛选目录、十条分页及岗位详情"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "万向招聘计划页不存在")
        assert session.page is not None
        document = BeautifulSoup(await session.page.content(), "html.parser")
        check(f"ctmid: '{self.ctmid}'" in str(document), "万向招聘计划页租户 ID 发生变化")
        cards = [str(item["jobid"]) for item in document.select(".tel_top[jobid]")]
        check(bool(cards) and len(cards) == len(set(cards)), "万向首屏岗位卡片缺失或重复")
        scope = Scope(name="wanxiang-2027-all-jobs")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        size = 10
        while True:
            session.consume_request()
            await asyncio.sleep(session.config.delay)
            response = await session.page.evaluate(
                LIST_JS,
                {
                    "ctmid": self.ctmid,
                    "functype": "",
                    "jobarea": "",
                    "poscode": "",
                    "pagenum": page,
                    "pagesize": size,
                },
            )
            check(
                isinstance(response, dict) and isinstance(response.get("resultbody"), dict),
                "万向岗位目录回调结构改变",
            )
            body = response["resultbody"]
            expected = int(body["totalnum"])
            check(0 < expected <= 5000, "万向岗位目录总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "万向翻页期间总数变化")
            rows = body["joblist"]
            check(
                isinstance(rows, list) and len(rows) == min(size, expected - (page - 1) * size),
                "万向目录分页行数不符",
            )
            if page == 1:
                check([str(row["jobid"]) for row in rows] == cards, "万向首屏与接口岗位不符")
            evidence = session.output / "coapi-pages" / f"{page:04}.json"
            write_json(evidence, response)
            session.last_evidence = str(evidence)
            fresh = self.add_page(scope, rows, seen, lambda row: str(row["jobid"]))
            for row in fresh:
                key = str(row["jobid"])
                try:
                    check(str(row["ctmid"]) == self.ctmid, "万向目录租户 ID 不符")
                    listing = self.listing_job(key, row, deadline=text(row.get("validDate")))
                    if select(listing, "all", self.as_of).reason == "expired":
                        listing.detail_mode = "listing_only"
                        self.result.jobs.append(listing)
                        scope.skipped_expired += 1
                        continue
                    resolved = self.before_detail(
                        f"job:{key}", row, scope, listing, evidence=str(evidence)
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    values, detail_evidence = await self.detail(key)
                    job = self.complete_job(key, row, values, detail_evidence, str(evidence))
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if scope.unique == expected:
                scope.terminal = True
                break
            page += 1
            check(page <= (expected + size - 1) // size, "万向目录超过声明页数")


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


class Cqrcb2027(Coapi):
    name = "coapi-cqrcb-2027"
    host = "campus.51job.com"
    path = "/CQRCB2027/job.html"
    ctmid = "9586513"
    scope_description = "重庆农商行 2027 校招全目录；排除驻行纪检监察组和子公司分支"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "重庆农商行招聘页不存在")
        assert session.page is not None
        nav = await session.page.evaluate(
            """() => JOB_NAV_DATA.flatMap(item => [item, ...(item.children || [])])
              .flatMap(item => String(item.poscode || '').split(',').filter(Boolean))"""
        )
        expected_codes = {
            "A",
            "B",
            "C",
            *(f"D{i}" for i in range(1, 7)),
            *(f"E{i:02}" for i in range(1, 43)),
            *(f"F{i}" for i in range(1, 5)),
        }
        check(isinstance(nav, list) and set(nav) == expected_codes, "重庆农商行页面导航编码变化")
        session.consume_request()
        response = await session.page.evaluate(
            LIST_JS,
            {
                "ctmid": self.ctmid,
                "pagesize": 2000,
                "poscode": "",
                "sort": "poscode",
                "sequence": 1,
            },
        )
        check(
            isinstance(response, dict) and isinstance(response.get("resultbody"), dict),
            "重庆农商行目录回调结构改变",
        )
        body = response["resultbody"]
        expected = int(body["totalnum"])
        rows = body["joblist"]
        check(
            0 < expected <= 2000 and isinstance(rows, list) and len(rows) == expected,
            "重庆农商行无筛选目录不完整",
        )
        check(
            {text(row.get("poscode")) for row in rows} == expected_codes,
            "重庆农商行目录编码与页面导航不符",
        )
        evidence = session.output / "coapi-list.json"
        write_json(evidence, response)
        session.last_evidence = str(evidence)
        scope = Scope(name="cqrcb-2027-all-codes", expected=expected)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        self.add_page(scope, rows, seen, lambda row: str(row["jobid"]))
        own_codes = expected_codes - {"A", "F1", "F2", "F3", "F4"}
        for row in rows:
            key = str(row["jobid"])
            try:
                check(str(row["ctmid"]) == self.ctmid, "重庆农商行目录租户 ID 不符")
                code = text(row.get("poscode"))
                if code not in own_codes:
                    scope.skipped_out_of_scope += 1
                    continue
                check(
                    text(row.get("coname")) == "重庆农村商业银行股份有限公司",
                    "重庆农商行目录用人主体变化",
                )
                check(text(row.get("term")) == "全职", "重庆农商行岗位类型不符")
                listing = self.listing_job(key, row)
                resolved = self.before_detail(
                    f"job:{key}", row, scope, listing, evidence=str(evidence)
                )
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                detail, detail_evidence = await self.detail(key)
                check(text(detail.get("poscode")) == code, "重庆农商行详情职位编码不符")
                check(
                    text(detail.get("coname")) == "重庆农村商业银行股份有限公司",
                    "重庆农商行详情用人主体变化",
                )
                job = self.complete_job(key, row, detail, detail_evidence, str(evidence))
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True


class Cimc2027(Coapi):
    name = "coapi-cimc-2027"
    host = "campus.51job.com"
    path = "/cimc/post.html"
    ctmid = "7973180"
    scope_description = "中集集团 2027 届官方专题全部业务板块、无筛选 COAPI 目录及逐岗详情"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "中集 2027 职位页不存在")
        assert session.page is not None
        await session.page.locator("#job-list tr[rel]").first.wait_for(timeout=20000)
        document = BeautifulSoup(await session.page.content(), "html.parser")
        cards = [str(item["rel"]) for item in document.select("#job-list tr[rel]")]
        check(len(cards) == 10 and len(set(cards)) == 10, "中集首屏十条岗位卡片不完整")
        inline = "\n".join(item.get_text() for item in document.select("script:not([src])"))
        match = re.search(r"var coid\s*=\s*(\{.*?\})\s*;", inline, re.DOTALL)
        check(match is not None, "中集页面单位映射缺失")
        assert match is not None
        units = dict(re.findall(r'"([A-Z][0-9]*)"\s*:\s*"([^"]+)"', match.group(1)))
        check(isinstance(units, dict) and units.get("Z") == "中集集团总部", "中集单位映射改变")
        session.consume_request()
        response = await session.page.evaluate(
            LIST_JS,
            {
                "ctmid": self.ctmid,
                "pagesize": 2000,
                "pagenum": 1,
                "poscode": "",
                "divid": "",
                "jobarea": "",
                "sort": "poscode",
                "sequence": 1,
            },
        )
        check(
            isinstance(response, dict) and isinstance(response.get("resultbody"), dict),
            "中集岗位目录回调结构改变",
        )
        body = response["resultbody"]
        expected = int(body["totalnum"])
        rows = body["joblist"]
        check(
            0 < expected <= 2000 and isinstance(rows, list) and len(rows) == expected,
            "中集无筛选目录不完整",
        )
        check([str(row["jobid"]) for row in rows[:10]] == cards, "中集首屏与目录 ID 不符")
        missing_unit_codes = {text(row.get("poscode")) for row in rows} - set(units) - {""}
        if missing_unit_codes:
            self.result.warnings.append(
                Issue(
                    code="unit_not_published",
                    source_id=self.source.source_id,
                    url=self.source.url,
                    message=f"页面单位映射缺少编码 {sorted(missing_unit_codes)}；对应岗位单位保留空值",
                )
            )
        evidence = session.output / "coapi-list.json"
        write_json(evidence, {"response": response, "units": units, "first_page_ids": cards})
        session.last_evidence = str(evidence)
        scope = Scope(name="cimc-2027-all-businesses", expected=expected)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        self.add_page(scope, rows, seen, lambda row: str(row["jobid"]))
        for row in rows:
            key = str(row["jobid"])
            try:
                check(str(row.get("ctmid")) == self.ctmid, "中集目录混入其他租户")
                check(text(row.get("term")) == "全职", "中集校招目录混入非全职岗位")
                code = text(row.get("poscode"))
                listing = self.listing_job(key, row)
                listing.unit = text(units.get(code)) if code else text(row.get("coname"))
                resolved = self.before_detail(
                    f"job:{key}", row, scope, listing, evidence=str(evidence)
                )
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                detail, detail_evidence = await self.detail(key)
                check(text(detail.get("term")) == "全职", "中集详情混入非全职岗位")
                check(text(detail.get("poscode")) == code, "中集详情单位编码与目录不符")
                if str(detail["jobinfo"]).startswith("岗位介绍"):
                    detail = dict(detail)
                    detail["jobinfo"] = str(detail["jobinfo"]).replace("岗位介绍", "岗位职责", 1)
                job = self.complete_job(key, row, detail, detail_evidence, str(evidence))
                job.unit = listing.unit
                job.field_sources["unit"] = (
                    "中集专题页面 coid 映射 + 列表 poscode"
                    if code in units
                    else "source_missing:页面单位编码未映射"
                    if code
                    else "列表 coname 原文；未给出具体岗位单位"
                )
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True


TENANTS = (Nbhx, Wanxiang, Cofco, Scg, Cqrcb2027, Cimc2027)
