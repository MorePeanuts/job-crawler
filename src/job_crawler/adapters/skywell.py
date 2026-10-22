"""Skywell's explicit public campus job tab."""

import json

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class SkywellCampus(Adapter):
    name = "skywell-campus"
    host = "www.skywellcorp.com"
    path = "/website/skywellcorp/recruitment?tab=2"
    endpoint = "/api/recruit/list"
    ready_endpoints = (endpoint,)
    scope_description = "开沃集团官网校园招聘 type=2 公开全目录；更新日不作为发布日期"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {
                "pageNo": 1,
                "pageSize": 10,
                "langType": 1,
                "type": "2",
                "departIds": [],
                "cityCodes": [],
                "title": "",
                "total": 0,
            },
            "开沃校园目录入口带有未知筛选",
        )
        scope = Scope(name="skywell-campus-type-2")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                observed["url"], payload={**payload, "pageNo": page}
            )
            check(
                response.get("success") is True and response.get("code") == 200,
                "开沃校园职位接口失败",
            )
            data = response["result"]
            expected = int(data["total"])
            pages = int(data["pages"])
            check(expected > 0 and pages == (expected + 9) // 10, "开沃职位总数或页数无效")
            check(int(data["current"]) == page and int(data["size"]) == 10, "开沃职位页码不符")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "开沃职位总数在分页期间变化")
            rows = self.add_page(scope, data["records"], seen, lambda row: str(row["id"]))
            check(0 < len(rows) <= 10, "开沃职位页提前为空或超长")
            for row in rows:
                check(row.get("type") == 2 and row.get("langType") == 1, "开沃校园目录混入其他类型")
                if row.get("status") != 1:
                    scope.skipped_closed += 1
                    continue
                key = str(row["id"])
                title = text(row.get("title"))
                duties = text(row.get("description"))
                requirements = text(row.get("requirements"))
                check(bool(title and duties and requirements), "开沃校园职位标题或正文缺失")
                self.result.jobs.append(
                    self.job(
                        key,
                        title=title,
                        source_url=f"https://{self.host}{self.path}",
                        unit=text(row.get("departName")),
                        education=text(row.get("degree")),
                        location=text(row.get("workAddress")),
                        duties=duties,
                        requirements=requirements,
                        field_sources={
                            "duties": "recruit/list.result.records[].description",
                            "requirements": "recruit/list.result.records[].requirements",
                            "education": "recruit/list.result.records[].degree",
                            "location": "recruit/list.result.records[].workAddress",
                            "published": "source_missing:updateTime仅为更新日",
                            "deadline": "source_missing",
                        },
                    )
                )
                scope.details += 1
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(page < pages, "开沃校园目录末页前缺记录")
            page += 1
