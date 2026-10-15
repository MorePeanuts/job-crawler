"""Inovance's public, unfiltered campus position catalog."""

import json
import re
from typing import cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class InovanceCampus(Adapter):
    name = "inovance-campus"
    host = "recruit.inovance.com"
    path = "/#/campus/jobs"
    endpoint = "/prod-portal-api/position/ad/search"
    ready_endpoints = (endpoint,)
    scope_description = "汇川招聘官网 recruitTypes=[1] 无筛选校园招聘全目录"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        portal_id = observed.get("portal_id", "")
        check(
            isinstance(portal_id, str)
            and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", portal_id) is not None,
            "汇川缺少公开门户 ID",
        )
        payload = json.loads(observed["post_data"])
        check(
            payload.get("recruitTypes") == [1]
            and payload.get("keyword") == ""
            and payload.get("hotOnly") is False
            and payload.get("topOnly") is False
            and payload.get("longTermOnly") is False
            and payload.get("pageNum") == 1,
            "汇川入口不是无筛选校园目录",
        )
        check(
            set(payload)
            <= {
                "recruitTypes",
                "keyword",
                "hotOnly",
                "topOnly",
                "longTermOnly",
                "pageNum",
                "pageSize",
                "sortBy",
            },
            "汇川目录含未知筛选条件",
        )
        page_size = int(payload["pageSize"])
        check(0 < page_size <= 100, "汇川分页大小异常")
        scope = Scope(name="campus-recruit-type-1")
        session = cast(BrowserSession, self.session)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await session.request(
                observed["url"],
                payload={**payload, "pageNum": page},
                headers={"X-Portal-Id": portal_id},
            )
            check(response.get("code") == 200, "汇川列表业务失败")
            data = response["data"]
            expected = int(data["total"])
            check(expected >= 0, "汇川总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "汇川翻页期间总数变化")
            check(
                int(data["pageNum"]) == page
                and int(data["pageSize"]) == page_size
                and isinstance(data.get("hasMore"), bool),
                "汇川分页或末页状态异常",
            )
            rows = self.add_page(scope, data["records"], seen, lambda row: str(row["adId"]))
            check(len(rows) <= page_size, "汇川单页岗位超出分页大小")
            evidence = self.session.last_evidence
            for row in rows:
                check(str(row.get("recruitType")) == "1", "汇川列表混入非校招岗位")
                check(
                    bool(text(row.get("adJobName")))
                    and "jobDescription" in row
                    and "jobRequirement" in row,
                    "汇川岗位标题或正文缺失",
                )
                locations = row.get("workLocation") or []
                check(isinstance(locations, list), "汇川岗位地点结构变化")
                key = str(row["adId"])
                job = self.job(
                    key,
                    title=text(row["adJobName"]),
                    source_url=f"https://{self.host}/#/jobs/{key}",
                    work_type="校招",
                    unit=text(row.get("segment")),
                    education=text(row.get("degreeDesc")),
                    location="、".join(text(item.get("name")) for item in locations),
                    duties=text(row["jobDescription"]),
                    requirements=text(row["jobRequirement"]),
                    published=text(row.get("publishTime")),
                    field_sources={
                        "unit": "position/ad/search.records[].segment",
                        "education": "position/ad/search.records[].degreeDesc",
                        "location": "position/ad/search.records[].workLocation",
                        "duties": "position/ad/search.records[].jobDescription",
                        "requirements": "position/ad/search.records[].jobRequirement",
                        "published": "position/ad/search.records[].publishTime",
                        "deadline": "source_missing",
                    },
                )
                resolved = self.before_detail(f"ad:{key}", row, scope, job, evidence=evidence)
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"ad:{key}", row, [job])
            if not data["hasMore"]:
                check(scope.unique == expected, "汇川末页总数与唯一岗位数不符")
                scope.terminal = True
                break
            check(bool(rows) and scope.unique < expected, "汇川分页未闭合")
            page += 1
