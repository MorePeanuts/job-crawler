"""Sunwoda's two official graduate catalogs, including its custom PhD category."""

import json

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.adapters.zhiye import date_text
from job_crawler.models import Scope


class SunwodaCampus(Adapter):
    name = "sunwoda-campus"
    host = "sunwodacampus.zhiye.com"
    path = "/custom/fb00a48c-8c6e-294f-b4c8-04a45422015c"
    ready_endpoints = ("/api/Jobad/GetJobAdPageList",)
    scope_description = (
        "欣旺达官网本硕 Category=2 定制全目录及应届博士 Category=1547436687；排除实习/校园大使"
    )

    async def harvest(self) -> None:
        all_keys: set[str] = set()
        for category, path in (("2", self.path), ("1547436687", "/1547436687/jobs")):
            if category != "2":
                await self.session.open(
                    f"https://{self.host}{path}", ready_endpoints=self.ready_endpoints
                )
            observed = await self.session.observed("/api/Jobad/GetJobAdPageList")
            payload = json.loads(observed["post_data"])
            check(
                [str(v) for v in payload.get("Category", [])] == [category],
                "欣旺达正式应届类别不符",
            )
            for key in (
                "KeyWords",
                "LocId",
                "OrgId",
                "ClassificationOne",
                "ClassificationTwo",
                "Classification3",
                "Classification4",
                "Classification6",
            ):
                check(not payload.get(key), f"欣旺达目录含局部筛选 {key}")
            if category != "2":
                check(not payload.get("Classification5"), "欣旺达博士目录含职位筛选")
            scope = Scope(name=f"sunwoda-category-{category}")
            self.result.scopes.append(scope)
            seen: set[str] = set()
            page = 0
            while True:
                response = await self.session.request(
                    observed["url"], payload={**payload, "PageIndex": page, "PageSize": 20}
                )
                check(response.get("Code") == 200, "欣旺达目录业务失败")
                count = int(response["Count"])
                if scope.expected is None:
                    scope.expected = count
                check(count == scope.expected, "欣旺达目录总数变化")
                rows = self.add_page(scope, response["Data"], seen, lambda r: str(r["Id"]))
                for row in rows:
                    key = str(row["Id"])
                    check(str(row["CategoryId"]) == category, "欣旺达目录混入其他类型")
                    check(key not in all_keys, "欣旺达两个正式目录重复岗位")
                    check(
                        bool(row.get("JobAdName")) and "Duty" in row and "Require" in row,
                        "欣旺达完整正文结构改变",
                    )
                    all_keys.add(key)
                    education = text(row.get("Degree"))
                    if not education and row.get("Category") == "应届博士招聘":
                        education = "博士"
                    self.result.jobs.append(
                        self.job(
                            key,
                            title=text(row["JobAdName"]),
                            unit=text(row.get("Org")),
                            source_url=f"https://{self.host}{path}",
                            education=education,
                            location=text(row.get("LocNames")),
                            address=text(row.get("DetailAddress")),
                            category_raw=text(
                                row.get("Classification4") or row.get("ClassificationOne")
                            ),
                            duties=text(row["Duty"]),
                            requirements=text(row["Require"]),
                            published=date_text(row.get("PostDate")),
                            deadline=date_text(row.get("EndTime")),
                            field_sources={
                                "duties": "GetJobAdPageList.Duty",
                                "requirements": "GetJobAdPageList.Require",
                                "education": "Degree / 明确的应届博士招聘类别",
                                "published": "PostDate",
                                "deadline": "EndTime",
                            },
                        )
                    )
                    scope.details += 1
                if scope.unique >= count:
                    scope.terminal = True
                    break
                check(bool(rows), "欣旺达分页提前为空")
                page += 1
