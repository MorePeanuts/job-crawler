"""OPPO's public 2027 graduate and doctoral campus projects."""

import json

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Oppo2027(Adapter):
    name = "oppo-2027"
    host = "careers.oppo.com"
    path = "/university/oppo/campus/post"
    project_endpoint = "/openapi/position/project/list"
    list_endpoint = "/openapi/position/pageNew"
    ready_endpoints = (project_endpoint, list_endpoint)
    scope_description = "OPPO 官网 2027 应届和博士正式校招全目录；排除寻梦实习"

    async def harvest(self) -> None:
        projects_observed = await self.session.observed(self.project_endpoint)
        projects = json.loads(projects_observed["body"])
        check(projects.get("code") == 0, "OPPO 招聘项目接口失败")
        project_map = {int(item["idRecruitProject"]): item for item in projects["data"]}
        check(
            {29, 30, 31} <= project_map.keys()
            and project_map[29]["recruitmentType"] == "Intern"
            and project_map[30]["recruitmentType"] == "Graduate"
            and project_map[31]["recruitmentType"] == "doctor",
            "OPPO 2027 校招及实习项目配置改变",
        )
        observed = await self.session.observed(self.list_endpoint)
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {
                "pageNum": 1,
                "pageSize": 10,
                "positionName": "",
                "projectList": [],
                "positionTypeList": [],
                "workCityCodeList": [],
                "shareId": "",
            },
            "OPPO 校招目录入口带有未知筛选",
        )
        scope = Scope(name="oppo-campus-all-projects")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                observed["url"], payload={**payload, "pageNum": page}
            )
            check(response.get("code") == 0, "OPPO 职位列表接口失败")
            data = response["data"]
            count = int(data["total"])
            pages = int(data["pages"])
            check(count > 0 and pages == (count + 9) // 10, "OPPO 校招总数或总页数无效")
            check(int(data["current"]) == page and int(data["size"]) == 10, "OPPO 职位页码不符")
            if scope.expected is None:
                scope.expected = count
            check(count == scope.expected, "OPPO 校招总数在分页期间变化")
            rows = self.add_page(
                scope, data["records"], seen, lambda row: str(row["idRecruitPosition"])
            )
            check(0 < len(rows) <= 10, "OPPO 职位页提前为空或超长")
            for row in rows:
                project_id = int(row["projectId"])
                check(project_id in {29, 30, 31}, "OPPO 目录混入未知项目")
                check(
                    row.get("projectName") == project_map[project_id]["projectName"]
                    and row.get("recruitmentType") == project_map[project_id]["recruitmentType"],
                    "OPPO 岗位项目与公开项目表不一致",
                )
                if project_id == 29:
                    scope.skipped_out_of_scope += 1
                    continue
                if row.get("positionStatus") != 0:
                    scope.skipped_closed += 1
                    continue
                key = str(row["idRecruitPosition"])
                title = text(row.get("positionName"))
                duties = text(row.get("positionDesc") or row.get("projectPositionDesc"))
                requirements = text(
                    row.get("positionRequire")
                    or row.get("projectPositionRequire")
                    or row.get("knowledgeSkill")
                )
                check(bool(title and duties), "OPPO 正式校招岗位标题或职责缺失")
                self.result.jobs.append(
                    self.job(
                        key,
                        title=title,
                        source_url=f"https://{self.host}{self.path}/{key}?recruitType=Graduate",
                        location=text(row.get("workCityName")),
                        category_raw=text(row.get("positionTypeName")),
                        batch=text(row["projectName"]),
                        duties=duties,
                        requirements=requirements,
                        published=text(row.get("releaseTime")),
                        field_sources={
                            "duties": "pageNew.data.records[].positionDesc",
                            "requirements": (
                                "pageNew.data.records[].positionRequire/projectPositionRequire/knowledgeSkill"
                                if requirements
                                else "source_missing"
                            ),
                            "published": "pageNew.data.records[].releaseTime",
                            "location": "pageNew.data.records[].workCityName",
                            "deadline": "source_missing",
                        },
                    )
                )
                scope.details += 1
            if scope.unique >= count:
                scope.terminal = True
                break
            check(page < pages, "OPPO 末页前缺记录")
            page += 1
