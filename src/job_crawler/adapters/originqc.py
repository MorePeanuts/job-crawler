"""Origin Quantum's public campus category and rendered job details."""

import json
from datetime import datetime
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError


class Page(Protocol):
    async def evaluate(self, script: str) -> Any: ...


class PageSession(Protocol):
    page: Page


class OriginQCCampus(Adapter):
    name = "originqc-campus"
    host = "originqc.com.cn"
    path = "/zh/recruit?type=1"
    ready_endpoints = ("/api/recruit/recruitList",)
    scope_description = "本源量子官网 categoryId=1 校园招聘全目录和逐岗公开详情"

    async def harvest(self) -> None:
        observed = await self.session.observed("/api/recruit/recruitList")
        payload = json.loads(observed["post_data"])
        check(payload.get("categoryId") == 1, "本源量子入口不是校园类别")
        check(not payload.get("positionId") and not payload.get("addressId"), "岗位目录仍有筛选")
        check(payload.get("pageNum") == 1 and payload.get("pageSize") == 10, "岗位分页入口异常")
        api = observed["url"]
        scope = Scope(name="campus-category-1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page_num = 1
        while True:
            response = await self.session.request(api, payload={**payload, "pageNum": page_num})
            check(response.get("success") is True and response.get("code") == 1, "职位接口失败")
            data = response["obj"]
            expected = int(data["totalRecords"])
            pages = int(data["totalPages"])
            check(expected > 0 and pages > 0, "校园职位总数无效")
            check(int(data["pageNum"]) == page_num, "职位页码错配")
            check(pages == (expected + 9) // 10, "职位页数与总数不符")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "岗位总数在分页期间变化")
            rows = self.add_page(scope, data["entityList"], seen, lambda row: str(row["id"]))
            list_evidence = self.session.last_evidence
            check(bool(rows) and len(rows) <= 10, "职位页提前为空或超出页长")
            for row in rows:
                key = str(row["id"])
                try:
                    check(row.get("categoryName") == "校园招聘", "校园类别混入其他招聘")
                    title = text(row.get("positionname"))
                    check(bool(title), "岗位标题为空")
                    detail_url = f"https://{self.host}/zh/job_details?jobId={key}"
                    listed = self.job(
                        key,
                        title=title,
                        work_type="实习" if "实习" in title else "校招",
                        source_url=detail_url,
                        location=text(row.get("cityName")),
                        category_raw=text(row.get("positionCategoryName")),
                        published=self._date(row.get("publishTime")),
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
                        "() => ({url: location.href, text: document.body.innerText})"
                    )
                    parsed_url = urlsplit(detail["url"])
                    check(parse_qs(parsed_url.query).get("jobId") == [key], "岗位详情 ID 错配")
                    body = str(detail["text"])
                    check(
                        "".join(title.split()) in "".join(body.split()),
                        "岗位详情标题与列表不一致",
                    )
                    check("岗位职责：" in body and "任职资格：" in body, "岗位详情结构改变")
                    duties = body.split("岗位职责：", 1)[1].split("任职资格：", 1)[0].strip()
                    requirements = body.split("任职资格：", 1)[1].split("投递简历", 1)[0].strip()
                    check(bool(duties) and bool(requirements), "岗位正文为空")
                    job = self.job(
                        key,
                        title=title,
                        work_type="实习" if "实习" in title else "校招",
                        source_url=detail_url,
                        location=text(row.get("cityName")),
                        category_raw=text(row.get("positionCategoryName")),
                        duties=duties,
                        requirements=requirements,
                        published=self._date(row.get("publishTime")),
                        field_sources={
                            "duties": "job_details 正文岗位职责",
                            "requirements": "job_details 正文任职资格",
                            "published": "recruitList.obj.entityList[].publishTime",
                            "location": "recruitList.obj.entityList[].cityName",
                        },
                    )
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
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(page_num < pages, "校园职位末页前缺记录")
            page_num += 1

    @staticmethod
    def _date(value: object) -> str:
        check(isinstance(value, int) and value > 0, "源发布日期无效")
        assert isinstance(value, int)
        return datetime.fromtimestamp(value / 1000, ZoneInfo("Asia/Shanghai")).isoformat()
