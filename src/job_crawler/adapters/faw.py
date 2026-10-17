"""FAW's custom public GET catalog and standard Hotjob position details."""

import json
from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import query, text
from job_crawler.adapters.hotjob import Hotjob, location_paths
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class FawCampus(Hotjob):
    name = "hotjob-faw-campus"
    host = "faw-zhaopin.hotjob.cn"
    suite = "SU603374380dcad4635b836531"
    path = "/campusRecruitment"
    scope_description = "一汽官方应届生、博士生、双百及三地四个正式校园项目的全部单位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        document = BeautifulSoup(await session.page.content(), "html.parser")
        projects: dict[str, str] = {}
        for anchor in document.select('a[href*="positionList"]'):
            url = urljoin(f"https://{self.host}", str(anchor["href"]))
            parts = urlsplit(url)
            params = parse_qs(parts.query)
            check(parts.hostname == self.host, "一汽项目链接域名改变")
            kind = params.get("recruitType", [""])[0]
            check(kind in {"1", "12"}, "一汽校园项目出现未知类型")
            if kind == "1":
                key = params.get("projectId", [""])[0]
                check(key.isdigit() and key not in projects, "一汽项目 ID 缺失或重复")
                projects[key] = url
        check(set(projects) == {"205701", "205601", "205801", "203201"}, "一汽校园项目范围改变")
        for project, url in projects.items():
            try:
                await self.project(project, url)
            except Exception as exc:
                self.error(exc, project)

    async def project(self, project: str, url: str) -> None:
        session = cast(BrowserSession, self.session)
        scope = Scope(name=f"faw-project-{project}")
        self.result.scopes.append(scope)
        await session.open(url, ready_endpoints=("/positionInfo/listPosition/",))
        observed = await session.observed("/positionInfo/listPosition/")
        params = parse_qs(urlsplit(observed["url"]).query)
        check(
            f"/{self.suite}?" in observed["url"]
            and not observed.get("post_data")
            and params
            == {
                "recruitType": ["1"],
                "pageSize": ["10"],
                "currentPage": ["1"],
                "externalProjectStr": [project],
            },
            "一汽目录请求租户、项目或筛选发生变化",
        )
        terms_observed = await session.observed("/positionInfo/listSearchTerm/")
        check(f"/{self.suite}?" in terms_observed["url"], "一汽地点树租户错配")
        terms = json.loads(terms_observed["body"])
        check(terms.get("state") == "200", "一汽地点字典业务失败")
        locations = location_paths(terms["data"].get("provinceList", []))
        location_evidence = session.last_evidence
        seen: set[str] = set()
        page = 1
        detail_api = ""
        while True:
            response = await session.request(query(observed["url"], currentPage=page))
            check(response.get("state") == "200", "一汽目录业务失败")
            data = response["data"]["pageForm"]
            count = int(data["dataCount"])
            pages = int(data["totalPage"])
            check(count >= 0 and pages == (count + 9) // 10, "一汽总页数不一致")
            check(
                (count == 0 and not data["pageData"] and int(data["currentPage"]) in {0, 1})
                or (int(data["currentPage"]) == page and int(data["pageSize"]) == 10),
                "一汽返回页码或页大小异常",
            )
            if scope.expected is None:
                scope.expected = count
            check(scope.expected == count, "一汽分页过程中总数变化")
            rows = self.add_page(scope, data["pageData"], seen, lambda row: str(row["postId"]))
            evidence = session.last_evidence
            for row in rows:
                key = str(row["postId"])
                try:
                    check(
                        str(row["recruitType"]) == "1" and str(row["projectId"]) == project,
                        "一汽目录混入其他项目或类型",
                    )
                    listing = self._job(row, row, evidence, locations, location_evidence)
                    cached = self.before_detail(key, row, scope, listing, evidence=evidence)
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        continue
                    if not detail_api:
                        await session.open(
                            self.detail_page(key),
                            ready_endpoints=("/positionInfo/listPositionDetail/",),
                        )
                        detail_api = (await session.observed("/positionInfo/listPositionDetail/"))[
                            "url"
                        ]
                        check(f"/{self.suite}?" in detail_api, "一汽详情租户错配")
                    detail = await session.request(
                        detail_api, form={"postId": key, "recruitType": "1"}, detail=True
                    )
                    check(detail.get("state") == "200", "一汽详情业务失败")
                    item = detail["data"]
                    check(
                        str(item["postId"]) == key
                        and str(item["recruitType"]) == "1"
                        and str(item["projectId"]) == project
                        and text(item["postName"]) == text(row["postName"])
                        and bool(item.get("workContent")),
                        "一汽详情身份或正文不一致",
                    )
                    job = self._job(item, row, session.last_evidence, locations, location_evidence)
                    job.evidence.append(evidence)
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(key, row, [job])
                except Exception as exc:
                    self.error(exc, key)
            if page >= pages:
                scope.terminal = True
                break
            check(bool(rows), "一汽目录提前为空")
            page += 1
