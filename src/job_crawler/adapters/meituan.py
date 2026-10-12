"""Meituan public graduate list with full job text in each page."""

import json
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class Meituan(Adapter):
    name = "meituan-campus"
    host = "zhaopin.meituan.com"
    path = "/web/position?hiringType=4_1"
    ready_endpoints = ("/api/official/job/getJobList",)
    scope_description = "美团应届校招页面 jobType=4_1 且 typeCode=1 的公开岗位全目录"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        observed = await session.observed("/api/official/job/getJobList")
        candidates = [
            item
            for item in session.responses
            if "/api/official/job/getJobList" in item["url"]
            and item.get("post_data")
            and json.loads(item["post_data"]).get("jobType") == [{"code": "4", "subCode": ["1"]}]
        ]
        if candidates:
            observed = candidates[-1]
        payload = json.loads(observed["post_data"])
        check(payload["jobType"] == [{"code": "4", "subCode": ["1"]}], "美团目录不是应届校招")
        check(payload["typeCode"] == ["1"], "美团目录招聘类型改变")
        for key in ("keywords", "cityList", "department", "jfJgList", "specialCode"):
            check(not payload[key], f"美团目录带有筛选 {key}")
        check(payload["page"]["pageNo"] == 1, "美团目录不是第一页")
        observed_size = int(payload["page"]["pageSize"])
        check(0 < observed_size <= 100, "美团分页大小无效")
        # The default ranking changed between page requests during validation.
        # The public endpoint accepted 200 rows in one request (196 returned).
        size = 200
        scope = Scope(name="graduate-hiringType-4_1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                observed["url"], payload={**payload, "page": {"pageNo": page, "pageSize": size}}
            )
            check(response.get("status") == 1, "美团目录业务失败")
            data = response["data"]
            meta = data["page"]
            expected = int(meta["totalCount"])
            pages = int(meta["totalPage"])
            check(expected >= 0 and pages == (expected + size - 1) // size, "美团总数或页数异常")
            check(int(meta["pageNo"]) == page, "美团返回分页页码不一致")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "美团翻页期间总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["jobUnionId"]))
            evidence = self.session.last_evidence
            for row in rows:
                check(str(row["jobType"]) == "1", "美团应届目录混入其他岗位类型")
                key = str(row["jobUnionId"])
                check(bool(row.get("name") and row.get("jobDuty")), "美团岗位标题或职责缺失")
                url = (
                    f"https://{self.host}/web/position/detail?jobUnionId={key}&highlightType=campus"
                )
                published = ""
                if row.get("firstPostTime"):
                    published = datetime.fromtimestamp(
                        int(row["firstPostTime"]) / 1000, ZoneInfo("Asia/Shanghai")
                    ).strftime("%Y-%m-%d")
                cities = row.get("cityList") or []
                check(isinstance(cities, list), "美团工作城市结构改变")
                job = self.job(
                    key,
                    title=text(row["name"]),
                    source_url=url,
                    apply_url=url,
                    category_raw=text(row.get("jobFamily")),
                    location="、".join(dict.fromkeys(text(city["name"]) for city in cities)),
                    duties=text(row["jobDuty"]),
                    requirements=text(row.get("jobRequirement")),
                    published=published,
                    visible=row.get("jobStatus") == "000",
                    field_sources={
                        "duties": "getJobList.data.list[].jobDuty",
                        "requirements": "getJobList.data.list[].jobRequirement",
                        "published": "getJobList.data.list[].firstPostTime"
                        if published
                        else "source_missing",
                        "deadline": "source_missing",
                    },
                )
                job.evidence = [evidence]
                resolved = self.before_detail(f"job:{key}", row, scope, job, evidence=evidence)
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            if page >= pages:
                check(scope.unique == expected, "美团唯一岗位数与总数不符")
                scope.terminal = True
                break
            check(bool(rows), "美团目录提前为空")
            page += 1
