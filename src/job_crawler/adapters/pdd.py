"""PDD's public graduate catalog and detail API."""

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError

LIST_PATH = "/api/careers/api/recruit/position/list"
DETAIL_PATH = "/api/careers/api/recruit/position/detail"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def published_at(value: object) -> str:
    if not isinstance(value, int) or value <= 0:
        raise CrawlError("schema_changed", "拼多多发布时间不是毫秒时间戳")
    return datetime.fromtimestamp(value / 1000, UTC).astimezone(SHANGHAI).isoformat()


class PddCampus(Adapter):
    name = "pdd-campus"
    host = "careers.pddglobalhr.com"
    path = "/campus/grad"
    ready_endpoints = (LIST_PATH,)
    scope_description = "拼多多官方应届生招聘公开全目录；不含独立的实习生招聘目录"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/campus/grad/detail?" + urlencode({"positionId": job_id})

    async def harvest(self) -> None:
        observed = await self.session.observed(LIST_PATH)
        payload = json.loads(observed["post_data"])
        check(
            payload == {"page": 1, "pageSize": 10, "t": None},
            "拼多多应届生目录初始请求含未知筛选或分页规则改变",
        )
        scope = Scope(name="graduate-catalog")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        detail_url = ""
        first_detail: dict[str, Any] | None = None
        first_detail_id = ""

        while True:
            response = await self.session.request(
                observed["url"], payload={**payload, "page": page}
            )
            check(response.get("success") is True, "拼多多列表业务失败")
            data = response["result"]
            expected = int(data["total"])
            check(expected >= 0, "拼多多目录总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "拼多多目录总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["id"]))
            list_evidence = self.session.last_evidence
            check(len(rows) <= 10, "拼多多单页超出已观察页容量")
            if expected == 0:
                check(not rows, "拼多多空目录仍包含岗位")
                scope.terminal = True
                break

            for row in rows:
                job_id = str(row["id"])
                try:
                    check(bool(row.get("name")), "拼多多岗位名称为空")
                    check(bool(row.get("graduationYear")), "拼多多应届目录缺少届别")
                    listing = self.job(
                        job_id,
                        title=text(row["name"]),
                        source_url=self.detail_page(job_id),
                        location=text(row.get("workLocationName")),
                        category_raw=text(row.get("jobName")),
                        published=published_at(row.get("releaseTime")),
                    )
                    listing.evidence = [list_evidence] if list_evidence else []
                    reused = self.before_detail(
                        f"job:{job_id}", row, scope, listing, evidence=list_evidence
                    )
                    if reused is not None:
                        self.result.jobs.extend(reused)
                        continue
                    if not detail_url:
                        await self.session.open(
                            self.detail_page(job_id), ready_endpoints=(DETAIL_PATH,)
                        )
                        observed_detail = await self.session.observed(DETAIL_PATH)
                        check(
                            json.loads(observed_detail["post_data"]) == {"id": job_id, "t": None},
                            "拼多多详情请求与列表岗位不对应",
                        )
                        detail_url = observed_detail["url"]
                        first_detail = json.loads(observed_detail["body"])
                        first_detail_id = job_id
                        detail_evidence = self.session.last_evidence
                    else:
                        first_detail = None
                        detail_evidence = ""
                    response_detail = (
                        first_detail
                        if first_detail is not None and first_detail_id == job_id
                        else await self.session.request(
                            detail_url, payload={"id": job_id, "t": None}, detail=True
                        )
                    )
                    check(response_detail.get("success") is True, "拼多多详情业务失败")
                    detail = response_detail["result"]
                    check(str(detail["id"]) == job_id, "拼多多详情与列表 ID 不一致")
                    check(bool(detail.get("normal")), "拼多多岗位详情不再处于普通可见状态")
                    check(
                        str(detail.get("graduationYear")) == str(row["graduationYear"]),
                        "拼多多岗位届别不一致",
                    )
                    check(
                        detail.get("jobDuty") is not None
                        and detail.get("serveRequirement") is not None,
                        "拼多多详情缺少职责或要求字段",
                    )
                    job = self.job(
                        job_id,
                        title=text(detail["name"]),
                        source_url=self.detail_page(job_id),
                        location=text(detail.get("workLocationName")),
                        category_raw=text(detail.get("jobName")),
                        batch=f"{text(detail.get('graduationYear'))}届",
                        duties=text(detail["jobDuty"]),
                        requirements=text(detail["serveRequirement"]),
                        published=published_at(detail.get("releaseTime")),
                        field_sources={
                            "duties": "position/detail.result.jobDuty",
                            "requirements": "position/detail.result.serveRequirement",
                            "published": "position/detail.result.releaseTime（Unix 毫秒）",
                            "location": "position/detail.result.workLocationName",
                        },
                    )
                    job.evidence = [
                        e
                        for e in (list_evidence, detail_evidence or self.session.last_evidence)
                        if e
                    ]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{job_id}", row, [job])
                except Exception as exc:
                    self.error(exc, job_id)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if scope.unique == expected:
                scope.terminal = True
                break
            check(scope.unique < expected and bool(rows), "拼多多分页提前结束或超过总数")
            page += 1
