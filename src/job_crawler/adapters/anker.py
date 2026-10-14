"""Anker's public campus catalog and linked full job descriptions."""

import json
from typing import Any, cast

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class AnkerCampus(Adapter):
    name = "anker-campus"
    host = "career.anker.com.cn"
    path = "/universities/recruitment/jobPosts/"
    website = "6962795203808217351"
    endpoint = "/service/lark/openapi/getJobPosts/"
    ready_endpoints = (f"https://open.anker-in.com{endpoint}{website}",)
    scope_description = (
        "安克校园website公开全目录及逐条详情；正式校招，排除实习，不将修改时间用作发布时间"
    )

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        check(observed["url"].split("?")[0].endswith("/" + self.website), "安克校园站点不符")
        payload = json.loads(observed["post_data"])
        check(all(not v for v in payload.values()), "安克目录带筛选")
        scope = Scope(name="anker-campus-website")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await cast(BrowserSession, self.session).request(
                query(observed["url"], page=page, size=10), payload=payload, credentials="omit"
            )
            check(response.get("code") == 200, "安克目录业务失败")
            count = int(response["total"])
            if scope.expected is None:
                scope.expected = count
            check(count == scope.expected, "安克目录总数变化")
            rows = self.add_page(scope, response["data"], seen, lambda r: str(r["id"]))
            check(len(rows) == min(10, max(0, count - (page - 1) * 10)), "安克返回错误页大小")
            for row in rows:
                composite = str(row["id"])
                check(composite.endswith(self.website), "安克列表身份不包含本站ID")
                key = composite.removesuffix(self.website)
                check(key.isdigit() and row["jobProcessType"] == 2, "安克岗位身份或校园类别不符")
                url = f"https://{self.host}/jobDetail/?websiteId={self.website}&jobId={key}"
                listing = self.job(key, title=text(row["title"]), source_url=url)
                resolved = self.before_detail(f"job:{key}", row, scope, listing)
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                try:
                    result = await cast(BrowserSession, self.session).request(
                        f"https://open.anker-in.com/service/openapi/getJobPostDetail/{self.website}?jobPostId={key}",
                        detail=True,
                        credentials="omit",
                    )
                    check(result.get("code") == 200, "安克详情业务失败")
                    detail = result["data"]
                    check(
                        str(detail["id"]) == key and detail["title"] == row["title"],
                        "安克详情身份不一致",
                    )
                    check(detail["job_process_type"] == 2, "安克详情非校园类别")
                    job = self.from_detail(detail, url)
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if scope.unique >= count:
                scope.terminal = True
                break
            page += 1

    def from_detail(self, row: dict[str, Any], url: str):
        places = row.get("address_list") or ([row["address"]] if row.get("address") else [])
        locations = []
        addresses = []
        for place in places:
            components = [
                text((place.get(k) or {}).get("name", {}).get("zh_cn"))
                for k in ("state", "city", "district")
            ]
            locations.append("".join(dict.fromkeys(c for c in components if c)))
            street = text((place.get("name") or {}).get("zh_cn"))
            if street:
                addresses.append(locations[-1] + street)
        kind = text((row.get("job_recruitment_type") or {}).get("name", {}).get("zh_cn"))
        return self.job(
            str(row["id"]),
            title=text(row["title"]),
            source_url=url,
            unit=text((row.get("job_department") or {}).get("name", {}).get("zh_cn")),
            work_type="校招" if kind == "正式" and "实习" not in row["title"] else kind or "未知",
            visible=row["job_active_status"] == 1,
            closed=row["job_active_status"] != 1,
            duties=text(row["description"]),
            requirements=text(row["requirement"]),
            location="、".join(dict.fromkeys(locations)),
            address="、".join(dict.fromkeys(addresses)),
            category_raw=text((row.get("job_function") or {}).get("name", {}).get("zh_cn")),
            batch=text((row.get("subject") or {}).get("name", {}).get("zh_cn")),
            field_sources={
                "duties": "getJobPostDetail.description",
                "requirements": "getJobPostDetail.requirement",
                "address": "address_list.name.zh_cn",
                "published": "source_missing（create_time/modify_time非发布时间）",
                "deadline": "source_missing",
            },
        )
