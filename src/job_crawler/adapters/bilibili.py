"""Bilibili's public full-time graduate position list."""

import json
import re
from typing import Any, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession


def sections(raw: str) -> tuple[str, str]:
    body = text(raw)
    match = re.search(r"(?:工作要求|岗位要求|任职要求|任职资格)\s*[:：]", body)
    if not match:
        return body, ""
    duties = re.sub(
        r"^(?:工作职责|岗位职责|职位描述)\s*[:：]\s*", "", body[: match.start()]
    ).strip()
    return duties, body[match.end() :].strip()


class Bilibili(Adapter):
    name = "bilibili-campus"
    host = "jobs.bilibili.com"
    path = "/campus/positions?type=3"
    ready_endpoints = ("/api/campus/position/positionList",)
    scope_description = "哔哩哔哩应届生招聘页全职公开岗位无额外筛选目录"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        observed = await session.observed("/api/campus/position/positionList")
        payload = json.loads(observed["post_data"])
        check(payload.get("pageNum") == 1, "哔哩哔哩目录不是第一页")
        check(
            payload.get("workTypeList") == ["3"] and payload.get("positionTypeList") == ["3"],
            "哔哩哔哩目录不是全职应届",
        )
        for key in (
            "positionName",
            "postCode",
            "postCodeList",
            "workLocationList",
            "deptCodeList",
            "practiceTypes",
        ):
            check(not payload.get(key), f"哔哩哔哩目录带有筛选 {key}")
        check(
            payload.get("onlyHotRecruit") == 0 and payload.get("recruitType") is None,
            "哔哩哔哩目录含热招或其他筛选",
        )
        size = int(payload["pageSize"])
        check(0 < size <= 100, "哔哩哔哩分页大小无效")
        scope = Scope(name="graduate-fulltime")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            if page == 1:
                response: dict[str, Any] = json.loads(observed["body"])
                evidence = session.last_evidence
            else:
                check(session.page is not None, "哔哩哔哩浏览器页面丢失")
                assert session.page is not None
                session.consume_request()
                async with session.page.expect_response(
                    lambda item: "/api/campus/position/positionList" in item.url,
                    timeout=int(session.config.timeout * 1000),
                ) as waiting:
                    await session.page.locator(".ant-pagination-next").click()
                browser_response = await waiting.value
                check(browser_response.status == 200, "哔哩哔哩翻页请求失败")
                request_data = json.loads(browser_response.request.post_data)
                check(int(request_data["pageNum"]) == page, "哔哩哔哩翻页请求页码错误")
                response = await browser_response.json()
                evidence_path = session.output / f"ui-page-{page:05}.json"
                write_json(evidence_path, {"url": browser_response.url, "data": response})
                evidence = str(evidence_path)
                session.last_evidence = evidence
            check(response.get("code") == 0, "哔哩哔哩目录业务失败")
            data = response["data"]
            expected = int(data["total"])
            pages = int(data["pages"])
            check(
                expected >= 0 and pages == (expected + size - 1) // size, "哔哩哔哩总数或页数异常"
            )
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "哔哩哔哩翻页期间总数变化")
            session.last_evidence = evidence
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["id"]))
            for row in rows:
                key = str(row["id"])
                check(
                    row.get("recruitType") == 1 and row.get("positionTypeName") == "全职",
                    "哔哩哔哩目录混入非应届全职",
                )
                check(
                    bool(row.get("positionName") and row.get("positionDescription")),
                    "哔哩哔哩岗位标题或正文缺失",
                )
                duties, requirements = sections(row["positionDescription"])
                url = f"https://{self.host}/campus/positions/{key}"
                job = self.job(
                    key,
                    title=text(row["positionName"]),
                    source_url=url,
                    apply_url=url,
                    category_raw=text(row.get("postCodeName")),
                    location=text(row.get("workLocation")),
                    duties=duties,
                    requirements=requirements,
                    published=text(row.get("pushTime")),
                    field_sources={
                        "duties": "positionList.data.list[].positionDescription:工作职责",
                        "requirements": "positionList.data.list[].positionDescription:工作要求"
                        if requirements
                        else "source_missing",
                        "published": "positionList.data.list[].pushTime",
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
                check(scope.unique == expected, "哔哩哔哩唯一岗位数与总数不符")
                scope.terminal = True
                break
            check(bool(rows), "哔哩哔哩目录提前为空")
            page += 1
