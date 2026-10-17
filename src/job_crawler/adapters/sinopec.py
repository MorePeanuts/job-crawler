"""Sinopec's public campus units and complete position catalogue."""

import json
from collections import Counter
from collections.abc import AsyncIterator, Awaitable
from typing import Any, Protocol, cast
from urllib.parse import urlencode

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Tab(Protocol):
    def click(self, *, timeout: int) -> Awaitable[None]: ...


class Page(Protocol):
    def get_by_text(self, value: str, *, exact: bool) -> Tab: ...


class PageSession(Protocol):
    page: Page


class SinopecCampus(Adapter):
    name = "sinopec-campus"
    host = "job.sinopec.com"
    path = "/#/school/recruitmentPositions"
    ready_endpoints = ("/homepage/selectYpList",)
    scope_description = (
        "中国石化当前校园招聘全部单位及岗位；单位数量交叉核对，发布时间及职责缺失留空"
    )

    async def pages(
        self, endpoint: str, scope: Scope, key: str
    ) -> AsyncIterator[list[dict[str, Any]]]:
        observed = await self.session.observed(endpoint)
        payload = json.loads(observed["post_data"])
        check(payload == {"page": 1, "limit": 20, "keyword": ""}, "石化目录残留筛选或契约变化")
        seen: set[str] = set()
        page = 1
        while True:
            result = await self.session.request(observed["url"], payload={**payload, "page": page})
            check(result.get("code") == "S000000", "石化目录业务失败")
            data = result["data"]
            count = int(data["total"])
            check(count >= 0, "石化目录总数无效")
            if scope.expected is None:
                scope.expected = count
            check(count == scope.expected, "石化目录总数变化")
            check(
                data["size"] == 20
                and data["current"] == page
                and data["pages"] == (count + 19) // 20,
                "石化分页元数据变化",
            )
            rows = self.add_page(scope, data["records"], seen, lambda row: str(row[key]))
            scope.evidence.append(self.session.last_evidence)
            yield rows
            if scope.unique == count:
                scope.terminal = True
                break
            check(bool(rows) and scope.unique < count, "石化目录提前为空或超出总数")
            page += 1

    async def harvest(self) -> None:
        unit_scope = Scope(name="campus-recruiting-units")
        self.result.scopes.append(unit_scope)
        units: dict[str, tuple[str, int]] = {}
        async for rows in self.pages("/homepage/selectYpList", unit_scope, "jobId"):
            for row in rows:
                identity = text(row["deptId"])
                name = text(row["deptName"])
                count = int(row["postNum"])
                check(
                    identity not in units and bool(identity) and bool(name) and count >= 0,
                    "石化招聘单位身份或岗位数异常",
                )
                units[identity] = (name, count)
                unit_scope.details += 1

        await (
            cast(PageSession, self.session)
            .page.get_by_text("招聘岗位", exact=True)
            .click(timeout=15000)
        )
        scope = Scope(name="campus-all-positions")
        self.result.scopes.append(scope)
        distribution: Counter[str] = Counter()
        async for rows in self.pages("/homepage/selectPositionList", scope, "id"):
            evidence = self.session.last_evidence
            for row in rows:
                identity = str(row["id"])
                try:
                    unit = text(row["deptCode"])
                    check(unit in units, "石化岗位所属单位未在完整单位目录中")
                    check(text(row["deptName"]) == units[unit][0], "石化岗位单位名称与目录不符")
                    check(bool(text(row["jobPosition"])), "石化岗位名称为空")
                    requirements = "\n".join(
                        f"{label}：{text(row[field])}"
                        for field, label in (
                            ("specialtyNorm", "专业要求"),
                            ("foreignNorm", "外语要求"),
                            ("otherNorm", "其他要求"),
                        )
                        if text(row[field])
                    )
                    job = self.job(
                        identity,
                        title=text(row["jobPosition"]),
                        source_url=f"https://{self.host}/#/school/recruitmentPositionsDetail?{urlencode({'postId': identity})}",
                        unit=text(row["deptName"]),
                        location=text(row["workAddr"]),
                        education=text(row["educationNorm"]),
                        category_raw=text(row["positionType"]),
                        requirements=requirements,
                        deadline=text(row["timeEnd"]),
                        field_sources={
                            "requirements": "selectPositionList: specialtyNorm/foreignNorm/otherNorm；与公开详情一致",
                            "published": "source_missing",
                            "duties": "source_missing",
                            "deadline": "selectPositionList.timeEnd",
                        },
                    )
                    job.evidence = [evidence]
                    self.result.jobs.append(job)
                    distribution[unit] += 1
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, identity)
        check(
            distribution == Counter({key: value[1] for key, value in units.items()}),
            "石化单位岗位数与完整岗位目录不闭合",
        )
