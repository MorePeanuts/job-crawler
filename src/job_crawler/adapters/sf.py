"""SF Express's public campus list, including full visible job bodies."""

from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class SF(Adapter):
    name = "sf-campus"
    host = "campus.sf-express.com"
    path = "/#/positionList"
    ready_endpoints = ("/api/web/position/query?",)
    scope_description = "顺丰校招官网岗位投递页，公开无筛选全目录及列表完整正文"

    async def harvest(self) -> None:
        observed = await self.session.observed("/api/web/position/query?")
        params = parse_qs(urlsplit(observed["url"]).query)
        check(set(params) <= {"pageSize", "pageNum", "time"}, "顺丰目录含未知筛选")
        check(params.get("pageNum") == ["1"], "顺丰目录不是第一页")
        size = int(params["pageSize"][0])
        check(0 < size <= 100, "顺丰分页大小无效")
        scope = Scope(name="campus-current-season")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        season: int | None = None
        while True:
            response = await self.session.request(
                f"https://{self.host}/api/web/position/query?pageSize={size}&pageNum={page}"
            )
            expected = int(response["total"])
            pages = int(response["pages"])
            check(expected > 0 and pages == (expected + size - 1) // size, "顺丰总数或页数异常")
            check(int(response["pageNum"]) == page, "顺丰返回分页页码不一致")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "顺丰分页期间总数变化")
            rows = self.add_page(scope, response["list"], seen, lambda row: str(row["id"]))
            evidence = self.session.last_evidence
            for row in rows:
                key = str(row["id"])
                current_season = int(row["seasonId"])
                if season is None:
                    season = current_season
                check(current_season == season, "顺丰目录混入其他招聘季")
                check(
                    bool(row.get("positionName") and row.get("postDuty")), "顺丰岗位标题或正文缺失"
                )
                detail_url = f"https://{self.host}/#/postDetail/{key}"
                job = self.job(
                    key,
                    title=text(row["positionName"]),
                    source_url=detail_url,
                    apply_url=detail_url,
                    unit=text(row.get("orgSourceName")),
                    category_raw=text(row.get("positionTypeName")),
                    location=text(row.get("demandCity")),
                    education=text(row.get("educationName")),
                    duties=text(row["postDuty"]),
                    requirements=text(row.get("jobRequirement")),
                    published=text(row.get("createDate")),
                    field_sources={
                        "duties": "position/query.list[].postDuty",
                        "requirements": "position/query.list[].jobRequirement",
                        "published": "position/query.list[].createDate",
                        "deadline": "source_missing",
                    },
                )
                resolved = self.before_detail(f"job:{key}", row, scope, job, evidence=evidence)
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                detail = await self.session.request(
                    f"https://{self.host}/api/web/position/findById/{key}", detail=True
                )
                check(int(detail["id"]) == int(key), "顺丰详情与目录 ID 不一致")
                check(detail["positionName"] == row["positionName"], "顺丰详情标题与目录不一致")
                check(int(detail["seasonId"]) == season, "顺丰详情招聘季不一致")
                job.location = text(detail.get("demandCity"))
                job.duties = text(detail["postDuty"])
                job.requirements = text(detail.get("jobRequirement"))
                job.education = text(detail.get("educationName"))
                job.visible = detail.get("status") == 1
                job.evidence = [evidence, self.session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            if page >= pages:
                check(scope.unique == expected, "顺丰唯一岗位数与总数不符")
                scope.terminal = True
                break
            check(bool(rows) and response["hasNextPage"] is True, "顺丰目录提前结束")
            page += 1
