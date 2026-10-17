"""ZTO's public annual campus projects and complete vacancy details."""

import json
import re
from math import ceil
from typing import Any

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

API = "https://recruiting.gw.zt-express.com"
LIST = "/website/post/getPostInfoPageList"
DETAIL = "/website/post/getPostInfoDetail"


def result(response: dict[str, Any]) -> Any:
    check(response.get("status") is True and response.get("statusCode") == "SYS000", "中通业务失败")
    return response.get("result")


class ZtoCampus(Adapter):
    name = "zto-campus"
    host = "hr.zto.com"
    path = "/campus"
    ready_endpoints = ("/dictionary/getDictionaryCascade", "/website/activity/getRecruitmentNews")
    scope_description = "中通快递当届全部校园项目的应届岗位；总部及省区，不含实习与社招"

    async def harvest(self) -> None:
        observed = await self.session.observed("/dictionary/getDictionaryCascade")
        params = json.loads(observed["post_data"])
        check(params == {"groupName": "school_project", "status": 1}, "中通校园项目字典变化")
        projects = result(json.loads(observed["body"]))
        check(isinstance(projects, list) and bool(projects), "中通校园项目缺失")
        self.context_evidence = [self.session.last_evidence]
        years: set[str] = set()
        ids: set[str] = set()
        for project in projects:
            key = text(project.get("key"))
            check(
                key.isdigit() and key not in ids and not project.get("list"),
                "中通项目重复或新增层级",
            )
            ids.add(key)
            match = re.fullmatch(r"(20\d{2})校招-.+", text(project.get("value")))
            check(match is not None, "中通项目年度未知")
            assert match is not None
            years.add(match[1])
        check(len(years) == 1, "中通项目混合年度")
        self.year = next(iter(years))
        news = await self.session.observed("/website/activity/getRecruitmentNews")
        self.context_evidence.append(self.session.last_evidence)
        data = result(json.loads(news["body"]))
        check(
            isinstance(data, dict) and isinstance(data.get("schoolAnnouncements"), list),
            "中通公告缺失",
        )
        notices = [
            row for row in data["schoolAnnouncements"] if self.year + "届" in text(row.get("name"))
        ]
        check(len(notices) == 1, "中通当届公告不唯一")
        notice = notices[0]
        check(
            notice.get("status") == 1 and notice.get("recruitingType") == 2,
            "中通公告类型或状态变化",
        )
        body = text(notice.get("remark"))
        dates = re.findall(r"简历投递的起止时间\s*即日起至(20\d{2})年(\d{1,2})月(\d{1,2})日", body)
        check(len(dates) == 1, "中通明确截止日期缺失或重复")
        y, m, d = dates[0]
        self.deadline = f"{y}-{int(m):02d}-{int(d):02d}"
        self.seen: set[str] = set()
        for project in projects:
            try:
                await self.project(project)
            except Exception as exc:
                self.error(exc, text(project["key"]))

    async def project(self, project: dict[str, Any]) -> None:
        key = text(project["key"])
        scope = Scope(name=f"campus-project-{key}", evidence=list(self.context_evidence))
        self.result.scopes.append(scope)
        await self.session.open(
            f"https://{self.host}/campus-position?object=1&projectId={key}", ready_endpoints=(LIST,)
        )
        observed = await self.session.observed(LIST)
        params = json.loads(observed["post_data"])
        check(
            params.get("schoolObject") == ["1"]
            and params.get("postType") == 2
            and str(params.get("projectId")) == key,
            "中通项目或应届筛选错配",
        )
        for field in (
            "queryString",
            "queryPostNameString",
            "workPlaceIds",
            "workPlaceFlag",
            "positionTypeIds",
            "schoolPositionTypeIds",
        ):
            check(not params.get(field), "中通目录仍有局部筛选")
        check(params.get("pageSize") == 20 and params.get("pageNum") == 1, "中通初始分页变化")
        page = 1
        local: set[str] = set()
        while True:
            response = await self.session.request(API + LIST, payload={**params, "pageNum": page})
            data = result(response)
            check(isinstance(data, dict), "中通目录非对象")
            total = data.get("total")
            check(type(total) is int and total >= 0, "中通总数非法")
            if scope.expected is None:
                scope.expected = total
            pages = ceil(total / 20)
            check(
                total == scope.expected
                and data.get("pageNum") == page
                and data.get("pages") == pages,
                "中通分页计数变化",
            )
            rows = data.get("list")
            check(
                isinstance(rows, list) and len(rows) == min(20, max(0, total - (page - 1) * 20)),
                "中通当页岗位缺失",
            )
            check(data.get("hasNextPage") is (page < pages), "中通末页状态变化")
            evidence = self.session.last_evidence
            for row in self.add_page(scope, rows, local, lambda r: text(r.get("id"))):
                rid = text(row["id"])
                try:
                    check(rid not in self.seen, "中通跨项目岗位重复")
                    self.seen.add(rid)
                    check(
                        row.get("status") == 2
                        and text(row.get("deptNameStr")).startswith("中通快递"),
                        "中通单位范围或状态变化",
                    )
                    listing = self.job(
                        rid,
                        title=text(row.get("postNameOut")),
                        source_url=f"https://{self.host}/position-detail?id={rid}",
                        deadline=self.deadline,
                    )
                    cached = self.before_detail(
                        f"job:{rid}",
                        {"row": row, "deadline": self.deadline},
                        scope,
                        listing,
                        evidence=evidence,
                    )
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        continue
                    detail = result(
                        await self.session.request(API + DETAIL, payload={"id": rid}, detail=True)
                    )
                    check(isinstance(detail, dict), "中通详情缺失")
                    for field in (
                        "id",
                        "postNameOut",
                        "controlCenterName",
                        "workPlaceNameStr",
                        "workPlaceDetail",
                        "educationName",
                        "status",
                    ):
                        check(detail.get(field) == row.get(field), f"中通详情{field}错配")
                    check(
                        text(detail.get("deptNameStr")).startswith("中通快递"),
                        "中通详情不属于快递板块",
                    )
                    check(
                        bool(text(detail.get("duties")))
                        and bool(text(detail.get("qualification"))),
                        "中通完整正文缺失",
                    )
                    job = self.job(
                        rid,
                        title=text(detail["postNameOut"]),
                        source_url=listing.source_url,
                        unit=text(detail.get("controlCenterName")),
                        batch=text(project["value"]),
                        location=text(detail.get("workPlaceNameStr")),
                        address=text(detail.get("workPlaceDetail")),
                        education=text(detail.get("educationName")),
                        category_raw=text(detail.get("positionTypeName")),
                        duties=text(detail["duties"]),
                        requirements=text(detail["qualification"]),
                        deadline=self.deadline,
                        field_sources={
                            "published": "source_missing:gmtModified为修改时间",
                            "deadline": "当届官网校园公告明确简历投递截止",
                            "requirements": "getPostInfoDetail.qualification",
                        },
                    )
                    job.evidence.extend([evidence, *self.context_evidence])
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{rid}", {"row": row, "deadline": self.deadline}, [job])
                except Exception as exc:
                    self.error(exc, rid)
            if page >= pages:
                scope.terminal = True
                break
            page += 1
