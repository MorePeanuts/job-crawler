"""Verified public catalogs whose list responses include complete job descriptions."""

import json

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class CndCampus(Adapter):
    name = "cnd-campus"
    host = "campus.chinacnd.com"
    path = "/extcampushr/graduates"
    endpoint = "/api/campushr/outApi/officialWebsite/queryJobBasebyyjs"
    ready_endpoints = (endpoint,)
    scope_description = "名录建发校招入口的建发股份应届生全目录；不含链习生"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        scope = Scope(name="cnd-graduates")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            data = (
                json.loads(observed["body"])
                if page == 1
                else await self.session.request(
                    query(observed["url"], pageNumber=page, pageSize=10)
                )
            )
            check(
                data.get("success") is True and str(data.get("code")) == "200", "建发目录业务失败"
            )
            body = data["result"]
            count = int(body["total"])
            check(int(body["current"]) == page and int(body["size"]) == 10, "建发页码或大小不符")
            check(int(body["pages"]) == (count + 9) // 10, "建发总页数不符")
            if scope.expected is None:
                scope.expected = count
            check(count == scope.expected, "建发目录总数变化")
            rows = self.add_page(scope, body["records"], seen, lambda r: str(r["id"]))
            for row in rows:
                check(row.get("jobState") == "12030004", "建发岗位公开状态改变")
                check(
                    bool(
                        row.get("externalAliase")
                        and row.get("jobDescribe")
                        and row.get("jobRequirement")
                    ),
                    "建发岗位正文缺失",
                )
                self.result.jobs.append(
                    self.job(
                        str(row["id"]),
                        title=text(row["externalAliase"]),
                        unit="建发股份",
                        source_url=f"https://{self.host}{self.path}",
                        education=text(row.get("education")),
                        location=text(row.get("workAddrName")),
                        duties=text(row["jobDescribe"]),
                        requirements=text(row["jobRequirement"]),
                        published=text(row.get("publishTime")),
                        batch=f"{text(row.get('recruitYear'))} {text(row.get('recruitmentProject'))}",
                        field_sources={
                            "duties": "queryJobBasebyyjs.jobDescribe",
                            "requirements": "queryJobBasebyyjs.jobRequirement",
                            "education": "education",
                            "location": "workAddrName（不是面试地点）",
                            "published": "publishTime",
                            "deadline": "source_missing",
                        },
                    )
                )
                scope.details += 1
            if scope.unique >= count:
                scope.terminal = True
                break
            check(bool(rows), "建发目录提前为空")
            page += 1


class MideaCampus(Adapter):
    name = "midea-campus"
    host = "careers.midea.com"
    path = "/schoolOut/post"
    list_endpoint = "/backend/school/position/common/position/list"
    project_endpoint = "/backend/school/position/common/project/list"
    ready_endpoints = (list_endpoint, project_endpoint)
    scope_description = "美的公开在招本硕及博士项目全目录；排除日常实习"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.list_endpoint)
        payload = json.loads(observed["post_data"])
        for key in ("keyword", "superiorIds", "recruitCategoryIds", "workPlaceCodes"):
            check(not payload.get(key), f"美的目录仍有筛选 {key}")
        projects_response = await self.session.observed(self.project_endpoint)
        projects = json.loads(projects_response["body"])
        check(str(projects.get("code")) == "0", "美的项目目录业务失败")
        active = [
            p
            for p in projects["data"]
            if p.get("status") == 1 and p.get("employementCategory") == 1
        ]
        check(bool(active), "美的未返回正式应届项目")
        check(len({p["projectRuleId"] for p in active}) == len(active), "美的项目重复")
        for project in active:
            project_id = project["projectRuleId"]
            scope = Scope(name=f"midea-project-{project_id}")
            self.result.scopes.append(scope)
            seen: set[str] = set()
            page = 1
            while True:
                response = await self.session.request(
                    observed["url"],
                    payload={
                        **payload,
                        "projectRuleId": project_id,
                        "pageIndex": page,
                        "pageSize": 10,
                    },
                )
                check(str(response.get("code")) == "0", "美的职位目录业务失败")
                data = response["data"]
                count = int(data["total"])
                check(int(data["info"]["pageIndex"]) == page, "美的页码不符")
                check(int(data["info"]["totalPage"]) == (count + 9) // 10, "美的总页数不符")
                if scope.expected is None:
                    scope.expected = count
                check(count == scope.expected, "美的目录总数变化")
                rows = self.add_page(scope, data["data"], seen, lambda r: str(r["positionId"]))
                for row in rows:
                    check(
                        row["projectRuleId"] == project_id and row["employementCategory"] == 1,
                        "美的职位项目或招聘类型不符",
                    )
                    detail = row["projectPositionDto"]
                    check(
                        detail["projectPositionId"] == row["projectPositionId"],
                        "美的正文岗位标识不符",
                    )
                    check(
                        bool(detail.get("jobResponsibility") and detail.get("jobRequirement")),
                        "美的职位正文缺失",
                    )
                    self.result.jobs.append(
                        self.job(
                            f"{project_id}:{row['positionId']}",
                            title=text(row["projectPositionName"]),
                            batch=text(project["projectRuleName"]),
                            source_url=f"https://{self.host}{self.path}",
                            location="、".join(
                                dict.fromkeys(
                                    text(v["workPlaceName"])
                                    for v in row.get("workplaceDtoList", [])
                                )
                            ),
                            category_raw=text(row.get("recruitCategoryName")),
                            duties=text(detail["jobResponsibility"]),
                            requirements=text(detail["jobRequirement"]),
                            field_sources={
                                "duties": "projectPositionDto.jobResponsibility",
                                "requirements": "projectPositionDto.jobRequirement",
                                "location": "workplaceDtoList.workPlaceName",
                                "published": "source_missing",
                                "deadline": "source_missing",
                            },
                        )
                    )
                    scope.details += 1
                if scope.unique >= count:
                    scope.terminal = True
                    break
                check(bool(rows), "美的分页提前为空")
                page += 1


class KuaishouCampus(Adapter):
    name = "kuaishou-campus"
    host = "campus.kuaishou.cn"
    project = "20271779425607"
    path = f"/#/campus/jobs?recruitSubProjectCodes={project}"
    endpoint = "/recruit/campus/e/api/v1/open/positions/simple"
    ready_endpoints = (endpoint,)
    scope_description = "快手官网应届招聘指向的 2027 应届项目全目录；不含留用实习"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        payload = json.loads(observed["post_data"])
        check(payload.get("recruitSubProjectCodes") == [self.project], "快手应届项目不符")
        check(
            set(payload) <= {"recruitSubProjectCodes", "pageSize", "pageNum"},
            "快手目录带有未知筛选",
        )
        dictionary = json.loads((await self.session.observed("/dictionary/batch?"))["body"])
        check(dictionary.get("code") == 0, "快手字典业务失败")
        values = dictionary["result"]
        project = next((r for r in values["recruitSubProject"] if r["code"] == self.project), None)
        check(project is not None and "应届生" in project["name"], "快手项目不是应届生")
        assert project is not None
        categories: dict[str, str] = {}
        pending = list(values.get("positionCategoryFlatten") or values["positionCategory"])
        while pending:
            category = pending.pop()
            categories[category["code"]] = category["name"]
            pending.extend(category.get("children") or [])
        scope = Scope(name=f"kuaishou-{self.project}")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                observed["url"], payload={**payload, "pageNum": page, "pageSize": 10}
            )
            check(response.get("code") == 0, "快手目录业务失败")
            data = response["result"]
            count = int(data["total"])
            check(
                int(data["pageNum"]) == page and int(data["pages"]) == (count + 9) // 10,
                "快手页码或总页数不符",
            )
            if scope.expected is None:
                scope.expected = count
            check(count == scope.expected, "快手目录总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda r: str(r["code"]))
            for row in rows:
                check(
                    row["recruitSubProjectCode"] == self.project
                    and row["recruitProjectCode"] == "schoolr",
                    "快手职位项目不符",
                )
                check(
                    row.get("positionStatusCode") == "Release"
                    and row.get("ifShowRecruitWebsite") is True,
                    "快手目录含非公开岗位",
                )
                check(
                    bool(row.get("description") and row.get("positionDemand")), "快手职位正文缺失"
                )
                self.result.jobs.append(
                    self.job(
                        str(row["code"]),
                        title=text(row["name"]),
                        source_url=f"https://{self.host}{self.path}",
                        work_type="校招"
                        if row.get("positionNatureCode") == "fulltime"
                        else text(row.get("positionNatureCode")),
                        batch=project["name"],
                        category_raw=categories.get(row.get("positionCategoryCode"), ""),
                        duties=text(row["description"]),
                        requirements=text(row["positionDemand"]),
                        location="、".join(
                            text(v["name"]) for v in row.get("workLocationDicts", [])
                        ),
                        published=text(row.get("releaseTime")),
                        field_sources={
                            "duties": "positions/simple.description",
                            "requirements": "positionDemand",
                            "published": "releaseTime（不使用 updateTime）",
                            "location": "workLocationDicts.name",
                            "deadline": "source_missing",
                        },
                    )
                )
                scope.details += 1
            terminal = scope.unique >= count
            check(bool(data["isLastPage"]) == terminal, "快手末页状态与数量不符")
            if terminal:
                scope.terminal = True
                break
            check(bool(rows), "快手分页提前为空")
            page += 1


TENANTS = (CndCampus, MideaCampus, KuaishouCampus)
