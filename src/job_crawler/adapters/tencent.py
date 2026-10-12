"""Tencent's public graduate positions with catalog/detail reconciliation."""

import json
from typing import Any

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


def graduate_mapping(payload: dict[str, Any]) -> dict[int, str]:
    check(payload.get("status") == 0, "腾讯招聘项目接口失败")
    projects: dict[int, str] = {}
    for group in payload["data"]:
        for item in group.get("subProjectList") or []:
            if item.get("recruitType") == 1 or (
                item.get("recruitType") == 999 and "应届" in str(item.get("projectName"))
            ):
                projects[int(item["mappingId"])] = text(item["projectName"])
    check(bool(projects), "腾讯没有公开应届招聘项目")
    return projects


class Tencent(Adapter):
    name = "tencent-campus"
    host = "join.qq.com"
    path = "/post.html"
    ready_endpoints = ("/api/v1/position/searchPosition",)
    scope_description = "腾讯官网应届及青云应届公开岗位；实习招聘项目不在范围内"

    async def harvest(self) -> None:
        mapped = await self.session.observed("/api/v1/position/getProjectMapping")
        projects = graduate_mapping(json.loads(mapped["body"]))
        mapping_evidence = self.session.last_evidence
        observed = await self.session.observed("/api/v1/position/searchPosition")
        payload = json.loads(observed["post_data"])
        check(payload.get("pageIndex") == 1, "腾讯目录不是第一页")
        check(
            set(payload)
            == {
                "projectIdList",
                "projectMappingIdList",
                "keyword",
                "bgList",
                "workCountryType",
                "workCityList",
                "recruitCityList",
                "positionFidList",
                "pageIndex",
                "pageSize",
            },
            "腾讯目录查询结构改变",
        )
        for key in (
            "projectIdList",
            "keyword",
            "bgList",
            "workCityList",
            "recruitCityList",
            "positionFidList",
        ):
            check(not payload[key], f"腾讯目录含筛选 {key}")
        check(payload["workCountryType"] == 0, "腾讯目录国家筛选改变")
        check(
            set(projects).issubset(set(payload["projectMappingIdList"])), "应届项目不在站点目录中"
        )
        size = int(payload["pageSize"])
        check(0 < size <= 100, "腾讯分页大小异常")
        scope = Scope(name="graduate-projects")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        request = {**payload, "projectMappingIdList": sorted(projects)}
        list_url = observed["url"]
        while True:
            response = await self.session.request(list_url, payload={**request, "pageIndex": page})
            check(response.get("status") == 0, "腾讯岗位目录业务失败")
            data = response["data"]
            expected = int(data["count"])
            check(expected >= 0, "腾讯目录总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "腾讯翻页时总数变化")
            rows = self.add_page(scope, data["positionList"], seen, lambda row: str(row["postId"]))
            list_evidence = self.session.last_evidence
            for row in rows:
                key = str(row["postId"])
                check(int(row["projectId"]) in projects, "腾讯应届目录混入非应届项目")
                check(bool(row.get("positionTitle")), "腾讯目录标题缺失")
                listing = self._job(key, row, None, list_evidence, projects)
                resolved = self.before_detail(
                    f"job:{key}", row, scope, listing, evidence=list_evidence
                )
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                detail_url = (
                    f"https://{self.host}/api/v1/jobDetails/getJobDetailsByPostId?postId={key}"
                )
                detail_response = await self.session.request(detail_url, detail=True)
                if (
                    detail_response.get("status") == 404
                    and detail_response.get("message") == "岗位已下架"
                ):
                    listing.visible = False
                    listing.detail_mode = "listing_only"
                    listing.evidence = [list_evidence, self.session.last_evidence]
                    self.result.jobs.append(listing)
                    scope.skipped_closed += 1
                    self.remember(f"job:{key}", row, [listing])
                    continue
                check(detail_response.get("status") == 0, "腾讯岗位详情业务失败")
                detail = detail_response["data"]
                check(str(detail["postId"]) == key, "腾讯详情与目录 ID 不一致")
                check(
                    text(detail.get("title")) == text(row["positionTitle"]),
                    "腾讯详情标题与目录不一致",
                )
                check(int(detail["projectId"]) == int(row["projectId"]), "腾讯详情招聘项目不一致")
                job = self._job(key, row, detail, self.session.last_evidence, projects)
                job.evidence = [list_evidence, job.evidence[0], mapping_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "腾讯目录提前空页")
            page += 1

    def _job(
        self,
        key: str,
        listed: dict[str, Any],
        detail: dict[str, Any] | None,
        evidence: str,
        projects: dict[int, str],
    ):
        row = detail or listed
        url = f"https://{self.host}/post_detail.html?postid={key}"
        job = self.job(
            key,
            title=text(row.get("title") or listed.get("positionTitle")),
            source_url=url,
            apply_url=url,
            batch=projects[int(listed["projectId"])],
            unit=text(listed.get("bgs")),
            category_raw=text(row.get("tidName")),
            location=(
                "、".join(text(city) for city in detail["workCityList"])
                if detail and isinstance(detail.get("workCityList"), list)
                else text(listed.get("workCities"))
            ),
            duties=text(row.get("desc")),
            requirements=text(row.get("request")),
            field_sources={
                "duties": "getJobDetailsByPostId.data.desc" if detail else "source_missing",
                "requirements": "getJobDetailsByPostId.data.request"
                if detail
                else "source_missing",
                "published": "source_missing",
                "deadline": "source_missing",
            },
        )
        job.evidence = [evidence]
        return job
