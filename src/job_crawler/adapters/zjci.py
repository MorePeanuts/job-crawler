"""Zhejiang Construction Investment's public campus directory."""

import json
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class ZjciCampus(Adapter):
    name = "zjci-campus"
    host = "www.cnzgc.com"
    path = "/home/join"
    ready_endpoints = ("/cnzgc/con/recruitments/listPage?",)
    scope_description = "浙江建投集团官网 Category=2 校招全部成员单位 500 条容量目录"

    async def harvest(self) -> None:
        observed = await self.session.observed("pageSize=500&type=2&siteId=")
        params = parse_qs(urlsplit(observed["url"]).query)
        check(
            params
            == {
                "currentPage": ["1"],
                "pageSize": ["500"],
                "type": ["2"],
                "siteId": ["ST-20241124222158"],
            },
            "浙江建投目录存在未知筛选或站点 ID 变化",
        )
        payload = json.loads(observed["body"])
        check(payload.get("code") == 200, "浙江建投校招目录业务失败")
        data = payload["resData"]
        expected = int(data["total"])
        rows = data["result"]
        check(
            0 < expected <= 500
            and data.get("pages") == 1
            and data.get("currentPage") == 1
            and isinstance(rows, list)
            and len(rows) == expected,
            "浙江建投校招目录未完整返回",
        )
        list_evidence = self.session.last_evidence
        first = await self.session.observed("pageSize=10&type=2&positionName=")
        first_data = json.loads(first["body"])["resData"]
        check(
            first_data["total"] == expected
            and [str(item["id"]) for item in first_data["result"]]
            == [str(item["id"]) for item in rows[:10]],
            "浙江建投首屏与完整目录不一致",
        )
        scope = Scope(name="campus-category-2", expected=expected)
        self.result.scopes.append(scope)
        self.session.last_evidence = list_evidence
        seen: set[str] = set()
        fresh = self.add_page(scope, rows, seen, lambda row: str(row["id"]))
        for row in fresh:
            key = str(row["id"])
            try:
                check(
                    row.get("category") == 2 and row.get("processStatus") == 2,
                    "浙江建投校招目录混入其他类别或关闭岗位",
                )
                check(
                    bool(text(row.get("positionName")))
                    and bool(text(row.get("responsibilities")))
                    and bool(text(row.get("requirements")))
                    and bool(text(row.get("enterprise"))),
                    "浙江建投岗位关键正文或招聘单位缺失",
                )
                job = self.job(
                    key,
                    title=text(row["positionName"]),
                    source_url=self.source.url,
                    apply_url=self.source.url,
                    unit=text(row["enterprise"]),
                    location=text(row.get("area")),
                    duties=text(row["responsibilities"]),
                    requirements=text(row["requirements"]),
                    deadline=text(row.get("endTime")),
                    field_sources={
                        "unit": "listPage.resData.result[].enterprise",
                        "location": "listPage.resData.result[].area；区域级原文",
                        "duties": "listPage.resData.result[].responsibilities",
                        "requirements": "listPage.resData.result[].requirements",
                        "published": "source_missing:未提供发布时间；startTime 为申请开始时间",
                        "deadline": "listPage.resData.result[].endTime",
                    },
                )
                job.evidence = [list_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True
