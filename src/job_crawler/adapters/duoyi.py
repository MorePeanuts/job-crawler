"""Duoyi's public school job catalog with explicit regular/intern type."""

from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Issue, Scope


class DuoyiCampus(Adapter):
    name = "duoyi-campus"
    host = "sz.duoyi.com"
    path = "/v40/#/positions?recruit=10"
    endpoint = "/v40/api/index/positions/jds/page"
    ready_endpoints = (endpoint,)
    scope_description = "多益网络公开校园招聘 recruit=10 全目录；只纳入 outerNature=正式"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        values = parse_qs(urlsplit(observed["url"]).query)
        check(
            values == {"pageIndex": ["1"], "pageSize": ["15"], "recruit": ["10"]},
            "多益校招目录入口带有未知筛选",
        )
        scope = Scope(name="duoyi-school-recruit-10")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(query(observed["url"], pageIndex=page))
            check(response.get("code") == 0, "多益校招目录业务失败")
            data = response["data"]
            expected = int(data["total"])
            check(expected > 0, "多益校招目录为空")
            check(int(data["pageIndex"]) == page and int(data["pageSize"]) == 15, "多益页码错配")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "多益目录总数在分页期间变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["id"]))
            check(0 < len(rows) <= 15, "多益校园职位页提前为空或超长")
            for row in rows:
                check(row.get("category") == "SCHOOL", "多益校园目录混入非校园岗位")
                nature = row.get("outerNature") or []
                check(nature in (["正式"], ["实习"]), "多益岗位性质改变")
                if nature == ["实习"]:
                    scope.skipped_out_of_scope += 1
                    continue
                key = str(row["id"])
                title = text(row.get("name"))
                duties = text(row.get("jobResponsibility"))
                requirements = text(row.get("jobRequirements"))
                check(bool(title), "多益正式校招岗位标题缺失")
                if not duties or not requirements:
                    self.result.warnings.append(
                        Issue(
                            code="field_missing",
                            message="源列表缺少岗位职责或任职要求，保留待补全",
                            source_id=self.source.source_id,
                            job_key=key,
                            url=self.source.url,
                        )
                    )
                places = row.get("workPlaces") or []
                check(isinstance(places, list), "多益职位地点结构改变")
                self.result.jobs.append(
                    self.job(
                        key,
                        title=title,
                        source_url=f"https://{self.host}{self.path}",
                        location="、".join(text(place) for place in places),
                        category_raw=text(row.get("outerType")),
                        duties=duties,
                        requirements=requirements,
                        published=text(row.get("publishDate")),
                        field_sources={
                            "duties": (
                                "positions/jds/page.data.list[].jobResponsibility"
                                if duties
                                else "source_missing"
                            ),
                            "requirements": (
                                "positions/jds/page.data.list[].jobRequirements"
                                if requirements
                                else "source_missing"
                            ),
                            "published": "positions/jds/page.data.list[].publishDate",
                            "location": "positions/jds/page.data.list[].workPlaces",
                            "deadline": "source_missing",
                        },
                    )
                )
                scope.details += 1
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(page < (expected + 14) // 15, "多益校园目录末页前缺记录")
            page += 1
