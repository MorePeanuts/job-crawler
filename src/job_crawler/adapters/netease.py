"""NetEase's explicitly linked graduate projects, including campaign aliases."""

import json
import re
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope


class HtmlPage(Protocol):
    async def content(self) -> str: ...


class HtmlSession(Protocol):
    page: HtmlPage


PROJECTS = {
    102: ("网易互娱2027届校园招聘", "campus.game.163.com"),
    103: ("网易互联网2027届校园招聘", "campus.163.com"),
    77: ("网易游戏雷火2027届校园招聘", "leihuo.163.com"),
}


class NeteaseCampus(Adapter):
    name = "netease-campus-projects"
    host = "campus.163.com"
    path = "/app/index"
    ready_endpoints = ("/api/campuspc/project/navigation/list",)
    scope_description = (
        "网易应届生四入口：互娱102、互联网103、雷火77；星火归并103，雷火不完整截止日期待核验"
    )

    async def html(self) -> str:
        return await cast(HtmlSession, self.session).page.content()

    async def harvest(self) -> None:
        observed = await self.session.observed("/api/campuspc/project/navigation/list")
        data = json.loads(observed["body"])
        check(data.get("code") == 200, "网易项目导航业务失败")
        roots = [row for row in data["data"] if row["title"] == "应届生"]
        check(len(roots) == 1, "网易应届生导航缺失或重复")
        children = roots[0]["children"]
        names = [row["title"] for row in children]
        expected_names = {value[0] for value in PROJECTS.values()} | {
            "星火计划2027届人力资源培训生"
        }
        check(len(names) == 4 and set(names) == expected_names, "网易应届生项目集合变化")
        links = {row["title"]: row["link"] for row in children}
        navigation_evidence = self.session.last_evidence
        star = links["星火计划2027届人力资源培训生"]
        check(star == "https://campus.163.com/app/talents/stars", "网易星火入口变化")
        await self.session.open(star)
        soup = BeautifulSoup(await self.html(), "html.parser")
        alias_links = [a.get("href") for a in soup.select('a[href*="/app/detail/index?"]')]
        check(len(alias_links) == 1, "网易星火不再是单岗位别名")
        alias = urlsplit(str(alias_links[0]))
        alias_query = parse_qs(alias.query)
        check(
            alias.hostname == self.host and alias_query.get("projectId") == ["103"],
            "网易星火所属项目变化",
        )
        star_id = alias_query["id"][0]
        star_evidence = self.session.last_evidence
        for project_id, (name, host) in PROJECTS.items():
            try:
                entry = links[name]
                check(urlsplit(entry).hostname == host, "网易项目域名变化")
                if project_id != 77:
                    check(
                        parse_qs(urlsplit(entry).query) == {"id": [str(project_id)]},
                        "网易项目列表 ID 变化",
                    )
                await self.collect_project(project_id, entry, navigation_evidence)
            except Exception as exc:
                self.error(exc, f"project:{project_id}")
        check(
            any(job.source_key == f"103:{star_id}" for job in self.result.jobs),
            "网易星火别名未包含于完整互联网项目",
        )
        for job in self.result.jobs:
            if job.source_key == f"103:{star_id}":
                job.evidence.append(star_evidence)

    async def collect_project(self, project_id: int, entry: str, navigation_evidence: str) -> None:
        leihuo = project_id == 77
        endpoint = "/api/apply/job/list/show" if leihuo else "/api/campuspc/position/getJobList"
        await self.session.open(entry, ready_endpoints=(endpoint,))
        deadline = ""
        campaign_evidence = self.session.last_evidence
        if leihuo:
            content = BeautifulSoup(await self.html(), "html.parser").get_text("", strip=True)
            match = re.search(r"((?:\d{4}年)?\d{1,2}月\d{1,2}日)网申截止", content)
            check(match is not None, "雷火页面截止说明改变，需复核日期语义")
            assert match is not None
            deadline = match[1]
        else:
            banner = await self.session.observed("/api/campuspc/project/banner")
            metadata = json.loads(banner["body"])
            check(
                metadata.get("code") == 200
                and metadata["data"]["projectStatus"] == 1
                and metadata["data"]["projectName"] == PROJECTS[project_id][0],
                "网易项目已关闭或项目名称变化",
            )
            campaign_evidence = self.session.last_evidence
        observed = await self.session.observed(endpoint)
        params = parse_qs(urlsplit(observed["url"]).query, keep_blank_values=True)
        expected = (
            {"project_id": ["77"], "page_size": ["10"], "page_number": ["1"], "job_name": [""]}
            if leihuo
            else {"projectId": [str(project_id)], "pageSize": ["10"], "currentPage": ["1"]}
        )
        check(
            {key: value for key, value in params.items() if key != "timeStamp"} == expected,
            "网易项目目录带筛选或分页契约变化",
        )
        scope = Scope(
            name=f"graduate-project-{project_id}", evidence=[navigation_evidence, campaign_evidence]
        )
        self.result.scopes.append(scope)
        page = 1
        seen: set[str] = set()
        detail_api = ""
        while True:
            if leihuo and page > 1:
                # The detail portal and Leihuo list API allow different origins.
                await self.session.open(entry, ready_endpoints=(endpoint,))
                detail_api = ""
            url = query(
                observed["url"], **({"page_number": page} if leihuo else {"currentPage": page})
            )
            response = await self.session.request(url)
            check(response.get("status" if leihuo else "code") == 200, "网易岗位列表业务失败")
            data = response["data"]
            total = int(data["count_number" if leihuo else "total"])
            pages = int(data["pages_count" if leihuo else "pages"])
            check(total >= 0 and pages == (total + 9) // 10, "网易分页总数与页数不符")
            if scope.expected is None:
                scope.expected = total
            check(scope.expected == total, "网易分页期间岗位数变化")
            rows = self.add_page(
                scope,
                data["apply_job_list" if leihuo else "list"],
                seen,
                lambda row: str(row["ehr_job_id" if leihuo else "id"]),
            )
            list_evidence = self.session.last_evidence
            for row in rows:
                identity = str(row["ehr_job_id" if leihuo else "id"])
                key = f"{project_id}:{identity}"
                try:
                    check(
                        str(row["ehr_project_id" if leihuo else "projectId"]) == str(project_id),
                        "网易列表岗位项目错配",
                    )
                    title = text(row["job_name" if leihuo else "positionName"])
                    if leihuo:
                        check(
                            str(row["ehr_job_type"]) == "1"
                            and row["type_name"] == "全职"
                            and row["target"] == "2027届应届毕业生",
                            "雷火目录混入非应届全职岗位",
                        )
                    host = "campus.163.com" if leihuo else PROJECTS[project_id][1]
                    detail_page = f"https://{host}/app/detail/index?{urlencode({'id': identity, 'projectId': project_id})}"
                    if leihuo:
                        check(row["job_detail_url"] == detail_page, "雷火详情关联变化")
                    listing = self.job(key, title=title, source_url=detail_page, deadline=deadline)
                    listing.evidence = [list_evidence, campaign_evidence]
                    identity_record = {"row": row, "campaign_deadline": deadline}
                    cached = self.before_detail(
                        key, identity_record, scope, listing, evidence=list_evidence
                    )
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        continue
                    if not detail_api:
                        await self.session.open(
                            detail_page, ready_endpoints=("/api/campuspc/position/getJobDetails",)
                        )
                        detail_api = (
                            await self.session.observed("/api/campuspc/position/getJobDetails")
                        )["url"]
                    detail_response = await self.session.request(
                        query(detail_api, id=identity, projectId=project_id), detail=True
                    )
                    check(detail_response.get("code") == 200, "网易详情业务失败")
                    detail = detail_response["data"]
                    check(
                        str(detail["id"]) == identity
                        and int(detail["projectId"]) == project_id
                        and text(detail["positionName"]) == title,
                        "网易详情身份或标题错配",
                    )
                    job = self.detail_job(key, detail, detail_page, deadline)
                    job.evidence.extend([list_evidence, campaign_evidence, navigation_evidence])
                    self.result.jobs.append(job)
                    self.remember(key, identity_record, [job])
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, key)
            terminal = page >= pages
            if leihuo:
                check(data["last_page"] is terminal, "雷火末页标记不符")
            if terminal:
                check(scope.unique == total, "网易末页与唯一岗位数不符")
                scope.terminal = True
                break
            check(len(rows) == 10, "网易分页提前结束")
            page += 1

    def detail_job(self, key: str, row: dict[str, Any], source_url: str, deadline: str) -> Job:
        return self.job(
            key,
            title=text(row["positionName"]),
            source_url=source_url,
            batch=text(row["projectName"]),
            location=text(row["workPlaceName"]),
            category_raw=text(row["positionTypeName"]),
            duties=text(row["positionDescription"]),
            requirements=text(row["positionRequirement"]),
            published=text(row["publishTime"]),
            deadline=deadline,
            field_sources={
                "published": "getJobDetails.publishTime；不使用列表 updateTime",
                "duties": "getJobDetails.positionDescription",
                "requirements": "getJobDetails.positionRequirement",
                "deadline": "项目页面原文；缺年份保留待核验" if deadline else "source_missing",
            },
        )
