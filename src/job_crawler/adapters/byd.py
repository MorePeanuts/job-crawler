"""BYD public 2027 campus catalog and position variants."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol, cast
from urllib.parse import urlencode, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError

LIST_PATH = "/portal/api/portal-api/schoolPortal/queryPositionList"
DETAIL_PATH = "/portal/api/portal-api/schoolPortal/queryPosition"


class Locator(Protocol):
    @property
    def first(self) -> Locator: ...

    async def click(self, *, timeout: int) -> None:  # noqa: ASYNC109
        ...


class Page(Protocol):
    def get_by_text(self, text: str, *, exact: bool = False) -> Locator: ...


class PageSession(Protocol):
    page: Page


class BYDRequester(Protocol):
    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]: ...


def requirement_education(value: str) -> str:
    match = re.search(r"(?:学历要求|学历)[：:]\s*(博士后|博士|硕士|本科|大专|专科|中专)", value)
    return match.group(1) if match else ""


class BYDCampus(Adapter):
    name = "byd-campus"
    host = "job.byd.com"
    path = "/portal/pc/#/school/home"
    scope_description = (
        "比亚迪 2027 应届生全目录，详情展开每个公开岗位的部门/学历方向；不含实习生和社会招聘"
    )

    async def harvest(self) -> None:
        page = cast(PageSession, self.session).page
        try:
            await page.get_by_text("应届生", exact=True).first.click(timeout=15_000)
        except Exception as exc:
            raise CrawlError("campus_entry_missing", "比亚迪招聘页未找到应届生岗位入口") from exc
        observed = await self.session.observed(LIST_PATH)
        parsed = urlsplit(observed["url"])
        check(parsed.hostname == self.host and parsed.path == LIST_PATH, "比亚迪岗位列表接口变化")
        payload = json.loads(observed.get("post_data") or "{}")
        check(
            isinstance(payload, dict)
            and payload.get("batch") == "2027"
            and payload.get("campusNature") == "008501"
            and payload.get("abroad") == ""
            and payload.get("degree") == ""
            and payload.get("jobType") == []
            and payload.get("researchDirection") == []
            and payload.get("workPlace") == []
            and payload.get("keywords") == "",
            "比亚迪目录带有岗位/地区筛选或不再是应届生入口",
        )
        observed_page_size = int(payload["pageSize"])
        check(0 < observed_page_size <= 100, "比亚迪分页大小异常")
        page_size = 500
        scope = Scope(name="byd-2027-fresh-graduate")
        self.result.scopes.append(scope)
        requester = cast(BYDRequester, self.session)
        seen: set[str] = set()
        page_index = 1
        endpoint = observed["url"]
        page_payload = {**payload, "pageSize": page_size, "pageIndex": 1}
        list_evidence = self.session.last_evidence
        while True:
            response = await requester.request(endpoint, payload=page_payload)
            check(
                response.get("code") == 0 and isinstance(response.get("data"), list),
                "比亚迪岗位列表业务失败",
            )
            page_info = response.get("page")
            check(isinstance(page_info, dict), "比亚迪岗位分页信息缺失")
            assert isinstance(page_info, dict)
            expected = int(page_info["totalCount"])
            pages = int(page_info["totalPage"])
            check(int(page_info["pageIndex"]) == page_index, "比亚迪返回了错误分页")
            check(int(page_info["pageSize"]) == page_size, "比亚迪岗位分页大小不符合请求")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "比亚迪分页期间岗位总数变化")
            rows = response["data"]
            list_evidence = self.session.last_evidence
            if list_evidence not in scope.evidence:
                scope.evidence.append(list_evidence)
            for row in rows:
                check(
                    str(row.get("batch")) == "2027" and row.get("campusNature") == "008501",
                    "比亚迪岗位列表混入非 2027 应届生岗位",
                )
                key = str(row.get("id", ""))
                check(bool(key and row.get("jobName")), "比亚迪岗位 ID 或名称缺失")
                scope.listed += 1
                if key in seen:
                    continue
                seen.add(key)
                scope.unique += 1
                detail_url = f"https://{self.host}{DETAIL_PATH}?{urlencode({'id': key, 'abroad': '', 'degree': ''})}"
                try:
                    detail = await requester.request(detail_url, detail=True)
                    check(detail.get("code") == 0, "比亚迪岗位详情业务失败")
                    data = detail.get("data")
                    check(
                        isinstance(data, dict) and str(data.get("id")) == key,
                        "比亚迪详情与列表岗位 ID 不一致",
                    )
                    assert isinstance(data, dict)
                    variants = data.get("positionInfoList")
                    check(
                        isinstance(variants, list) and bool(variants),
                        "比亚迪岗位缺少可投递部门/学历方向",
                    )
                    for variant in variants:
                        check(
                            isinstance(variant, dict) and variant.get("id"),
                            "比亚迪岗位方向缺少唯一 ID",
                        )
                        check(bool(variant.get("jobType")), "比亚迪岗位方向缺少岗位类别")
                        duties = text(variant.get("jobDuty"))
                        requirements = text(variant.get("jobRequirements"))
                        check(bool(duties and requirements), "比亚迪岗位详情缺少职责或要求")
                        variant_id = str(variant["id"])
                        job = self.job(
                            f"{key}:{variant_id}",
                            title=text(data.get("jobName")),
                            unit=text(variant.get("division")),
                            location=text(variant.get("workPlace")),
                            education=requirement_education(requirements),
                            category_raw=text(variant.get("jobType")),
                            batch="2027届",
                            duties=duties,
                            requirements=requirements,
                            source_url=self.source.url,
                            field_sources={
                                "title": "schoolPortal/queryPosition.data.jobName",
                                "unit": "schoolPortal/queryPosition.data.positionInfoList[].division",
                                "education": "schoolPortal/queryPosition.data.positionInfoList[].jobRequirements:学历要求",
                                "location": "schoolPortal/queryPosition.data.positionInfoList[].workPlace",
                                "duties": "schoolPortal/queryPosition.data.positionInfoList[].jobDuty",
                                "requirements": "schoolPortal/queryPosition.data.positionInfoList[].jobRequirements",
                                "published": "source_missing:updateTime 仅作更新信息",
                                "deadline": "source_missing",
                            },
                        )
                        job.evidence = [list_evidence, self.session.last_evidence]
                        self.result.jobs.append(job)
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, key)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if page_index >= pages:
                check(scope.unique == expected, "比亚迪校招岗位唯一数与总数不符")
                scope.terminal = True
                break
            check(bool(rows), "比亚迪岗位目录提前结束")
            page_index += 1
            page_payload = {**payload, "pageSize": page_size, "pageIndex": page_index}
        if scope.expected == 0:
            scope.terminal = True
