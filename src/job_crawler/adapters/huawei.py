"""Huawei graduate advertisements and their explicitly published job intentions."""

import json
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession


class HuaweiGraduate(Adapter):
    name = "huawei-graduate-intentions"
    host = "career.huawei.com"
    path = "/cn/campus-recruitment-job-list?recruitmentType=FRESH_GRADUATE"
    ready_endpoints = ("/recruitmentPosition/pub/getJobPage",)
    scope_description = "华为官方应届生 CR/FRESH_GRADUATE 全目录及全部岗位意向；不含实习与社会招聘"

    def detail_page(self, advertisement: str) -> str:
        return f"https://{self.host}/cn/job-details?{urlencode({'advertisementId': advertisement})}"

    async def harvest(self) -> None:
        observed = await self.session.observed("/recruitmentPosition/pub/getJobPage")
        payload = json.loads(observed["post_data"])
        app_id = parse_qs(urlsplit(observed["url"]).query).get("X-HW-ID", [""])[0]
        check(
            app_id and observed.get("public_headers", {}).get("x-hw-id") == app_id,
            "华为公开应用标识与目录请求不符",
        )
        check(
            observed.get("public_headers", {}).get("x-jalor-tenantalias") == "hcm",
            "华为公开租户别名改变",
        )
        public_context = {
            "x-language": "zh_CN",
            "x-referer": "https://career.huawei.com/cn",
            "x-alb-gray": "prod",
        }
        check(
            all(observed["public_headers"].get(k) == v for k, v in public_context.items()),
            "华为公开语言或站点上下文变化",
        )
        headers = {
            "X-HW-ID": app_id,
            "X-Jalor-Tenantalias": "hcm",
            "X-Language": "zh_CN",
            "X-Referer": "https://career.huawei.com/cn",
            "X-ALB-Gray": "prod",
        }
        requester = cast(BrowserSession, self.session)
        check(
            payload
            == {
                "curPage": 1,
                "pageSize": 10,
                "jobType": "CR",
                "recruitmentType": ["FRESH_GRADUATE"],
            },
            "华为应届生目录类别或筛选改变",
        )
        scope = Scope(name="graduate-advertisements", unit="父岗位")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        detail_api = ""
        intent_api = ""
        page = 1
        while True:
            response = await requester.request(
                observed["url"], payload={**payload, "curPage": page}, headers=headers
            )
            check(response.get("status") == "SUCCESS", "华为目录业务失败")
            data = response["data"]
            check(
                isinstance(data, dict) and isinstance(data.get("pageVO"), dict),
                "华为未返回有效分页数据",
            )
            meta = data["pageVO"]
            count = int(meta["totalRows"])
            pages = int(meta["totalPages"])
            check(
                count >= 0
                and int(meta["curPage"]) == page
                and int(meta["pageSize"]) == 10
                and pages == (count + 9) // 10,
                "华为目录分页计数异常",
            )
            if scope.expected is None:
                scope.expected = count
            check(scope.expected == count, "华为分页期间总数变化")
            rows = self.add_page(scope, data["result"], seen, lambda r: str(r["advertisementId"]))
            list_evidence = self.session.last_evidence
            for row in rows:
                advertisement = str(row["advertisementId"])
                try:
                    check(row["scenarioName"] == "应届生", "华为目录混入其他招聘类型")
                    listing = self.job(
                        advertisement,
                        title=text(row["jobName"]),
                        source_url=self.detail_page(advertisement),
                        published=text(row.get("releaseDate")),
                    )
                    cached = self.before_detail(
                        advertisement, row, scope, listing, evidence=list_evidence
                    )
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        self.result.scopes.append(
                            Scope(
                                name=f"advertisement-{advertisement}-intentions",
                                expected=len(cached),
                                listed=len(cached),
                                unique=len(cached),
                                reused_details=len(cached),
                                terminal=True,
                                evidence=[list_evidence],
                            )
                        )
                        continue
                    if not detail_api:
                        await self.session.open(
                            self.detail_page(advertisement),
                            ready_endpoints=(
                                "/recruitmentPosition/pub/getRecruitmentPositionDetail",
                                "/recruitmentPosition/pub/getPositionIntentionList",
                            ),
                        )
                        detail_api = (
                            await self.session.observed(
                                "/recruitmentPosition/pub/getRecruitmentPositionDetail"
                            )
                        )["url"]
                        intent_api = (
                            await self.session.observed(
                                "/recruitmentPosition/pub/getPositionIntentionList"
                            )
                        )["url"]
                    detail_response = await requester.request(
                        detail_api,
                        payload={"advertisementId": advertisement},
                        headers=headers,
                        detail=True,
                    )
                    check(detail_response.get("status") == "SUCCESS", "华为详情业务失败")
                    detail = detail_response["data"]
                    check(
                        str(detail["advertisementId"]) == advertisement
                        and str(detail["jobId"]) == str(row["jobId"])
                        and text(detail["jobname"]) == text(row["jobName"]),
                        "华为详情身份错配",
                    )
                    check(
                        detail["recruitType"] == "CR" and detail["scenarioName"] == "应届生",
                        "华为详情不是应届生",
                    )
                    detail_evidence = self.session.last_evidence
                    intent_response = await requester.request(
                        intent_api, payload={"jobId": detail["jobId"]}, headers=headers, detail=True
                    )
                    check(intent_response.get("status") == "SUCCESS", "华为岗位意向业务失败")
                    intentions = intent_response["data"]
                    check(isinstance(intentions, list), "华为岗位意向不是完整数组")
                    intent_evidence = self.session.last_evidence
                    child = Scope(
                        name=f"advertisement-{advertisement}-intentions",
                        expected=len(intentions) or 1,
                        evidence=[list_evidence, detail_evidence, intent_evidence],
                    )
                    self.result.scopes.append(child)
                    child_seen: set[str] = set()
                    items = self.add_page(
                        child,
                        intentions or [detail],
                        child_seen,
                        lambda r: str(
                            r["positionIntentionId"]
                            if "positionIntentionId" in r
                            else r["advertisementId"]
                        ),
                    )
                    jobs: list[Job] = []
                    for item in items:
                        check(str(item["jobId"]) == str(row["jobId"]), "华为意向与父岗位错配")
                        job = self.parse_job(row, detail, item if intentions else None)
                        job.evidence = [list_evidence, detail_evidence, intent_evidence]
                        self.result.jobs.append(job)
                        jobs.append(job)
                        child.details += 1
                    child.terminal = True
                    scope.details += 1
                    self.remember(advertisement, row, jobs)
                except Exception as exc:
                    self.error(exc, advertisement)
            if page >= pages:
                check(scope.unique == count, "华为父岗位目录不完整")
                scope.terminal = True
                break
            check(len(rows) == 10, "华为目录提前结束")
            page += 1

    def parse_job(
        self, listed: dict[str, Any], detail: dict[str, Any], intention: dict[str, Any] | None
    ) -> Job:
        advertisement = str(listed["advertisementId"])
        body = intention if intention is not None else detail
        duties = text(body.get("jobResponsibilities" if intention else "mainBusiness"))
        requirements = text(body.get("jobDemand" if intention else "jobRequire"))
        check(
            bool(duties or requirements) and "请您详见岗位意向" not in duties + requirements,
            "华为岗位缺少真实正文，不能交付占位提示",
        )
        title = text(detail["jobname"])
        key = advertisement
        if intention is not None:
            check(bool(text(intention["positionIntention"])), "华为岗位意向名称为空")
            title += " - " + text(intention["positionIntention"])
            key += ":" + str(intention["positionIntentionId"])
        return self.job(
            key,
            title=title,
            source_url=self.detail_page(advertisement),
            unit=text(body.get("deptName")),
            location=text(body.get("jobPlaceName" if intention else "jobCity")),
            category_raw=text(detail.get("categoryName")),
            duties=duties,
            requirements=requirements,
            published=text(listed.get("releaseDate")),
            field_sources={
                "duties": "getPositionIntentionList.jobResponsibilities"
                if intention
                else "getRecruitmentPositionDetail.mainBusiness",
                "requirements": "getPositionIntentionList.jobDemand"
                if intention
                else "getRecruitmentPositionDetail.jobRequire",
                "published": "releaseDate；不使用 lastUpdateDate",
                "deadline": "source_missing",
            },
        )
