"""Mihoyo's public 2027 graduate project and rendered job details."""

import json
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError


class Page(Protocol):
    async def evaluate(self, script: str) -> Any: ...


class PageSession(Protocol):
    page: Page


class Mihoyo2027(Adapter):
    name = "mihoyo-2027"
    host = "jobs.mihoyo.com"
    path = "/#/campus/position?jobName=&projectIds%5B0%5D=13"
    endpoint = "/ats-portal/v1/job/list"
    ready_endpoints = (endpoint,)
    scope_description = "米哈游官网 2027 届秋招项目 13 正式岗位全目录和逐岗公开详情"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {
                "jobName": "",
                "projectIds": ["13"],
                "pageNo": 1,
                "pageSize": 10,
                "channelDetailIds": [1],
                "hireType": 1,
            },
            "米哈游 2027 届校招项目筛选改变",
        )
        scope = Scope(name="project-13-graduates")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        rows_with_evidence: list[tuple[dict[str, Any], str]] = []
        while True:
            response = await self.session.request(
                observed["url"], payload={**payload, "pageNo": page}
            )
            check(
                response.get("code") == 0 and response.get("success") is True, "米哈游职位接口失败"
            )
            data = response["data"]
            expected = int(data["total"])
            check(expected > 0, "米哈游 2027 项目没有公开岗位")
            check(int(data["pageNo"]) == page and int(data["pageSize"]) == 10, "米哈游页码错配")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "米哈游职位总数在分页期间变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["id"]))
            check(0 < len(rows) <= 10, "米哈游职位页提前为空或超长")
            for row in rows:
                check(row.get("projectName") == "2027届秋招", "米哈游项目 13 混入其他招聘")
                check(
                    row.get("jobNature") == "全职" and row.get("jobNatureId") == 1,
                    "米哈游项目混入非正式岗位",
                )
                if row.get("objectName"):
                    check("2027届" in text(row["objectName"]), "米哈游岗位面向对象改变")
                rows_with_evidence.append((row, self.session.last_evidence))
            if scope.unique >= expected:
                break
            check(page < (expected + 9) // 10, "米哈游末页前缺记录")
            page += 1
        for row, list_evidence in rows_with_evidence:
            key = str(row["id"])
            detail_url = f"https://{self.host}/#/campus/position/{key}"
            try:
                listed = self.job(
                    key,
                    title=text(row["title"]),
                    source_url=detail_url,
                    location="、".join(
                        dict.fromkeys(
                            text(place.get("addressDetail")) for place in row["addressDetailList"]
                        )
                    ),
                    category_raw=text(row.get("competencyType")),
                    batch="2027届秋招",
                    field_sources={"published": "source_missing", "deadline": "source_missing"},
                )
                listed.evidence = [list_evidence]
                reused = self.before_detail(
                    f"job:{key}", row, scope, listed, evidence=list_evidence
                )
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                await self.session.open(detail_url)
                detail = await cast(PageSession, self.session).page.evaluate(
                    """() => ({
                        url: location.href,
                        title: document.title,
                        sections: [...document.querySelectorAll('div[class*="blockContent"]')]
                          .map(el => ({heading: el.previousElementSibling?.innerText || '', body: el.innerText || ''}))
                    })"""
                )
                check(
                    urlsplit(str(detail["url"])).fragment == f"/campus/position/{key}",
                    "米哈游详情与列表 ID 不符",
                )
                check(text(detail["title"]) == listed.title, "米哈游详情标题与列表不符")
                sections = {
                    text(item["heading"]): text(item["body"]) for item in detail["sections"]
                }
                duties = sections.get("工作职责", "")
                requirements = sections.get("任职要求", "")
                check(bool(duties and requirements), "米哈游公开详情缺少职责或要求")
                if row.get("objectName"):
                    check(
                        text(row["objectName"]) == sections.get("面向对象"),
                        "米哈游详情面向对象与列表不符",
                    )
                job = self.job(
                    key,
                    title=listed.title,
                    source_url=detail_url,
                    location=listed.location,
                    category_raw=listed.category_raw,
                    batch=listed.batch,
                    duties=duties,
                    requirements=requirements,
                    field_sources={
                        "duties": "公开职位详情:工作职责",
                        "requirements": "公开职位详情:任职要求",
                        "published": "source_missing",
                        "deadline": "source_missing",
                    },
                )
                job.evidence = [list_evidence, self.session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            except Exception as exc:
                self.error(exc, key)
                if isinstance(exc, CrawlError) and exc.code in {
                    "access_denied",
                    "request_budget",
                    "time_budget",
                }:
                    raise
        scope.terminal = not self.result.issues
