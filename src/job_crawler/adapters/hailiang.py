"""Hailiang's verified education and stock-company campus portals."""

from typing import cast

from pydantic import BaseModel

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.feishu import LIST_PATH, Desaysv
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession

DEGREES = {6: "本科及以上", 7: "硕士及以上", 8: "博士及以上"}


class TypeParent(BaseModel):
    id: str
    name: str


class RecruitType(TypeParent):
    parent: TypeParent


class Address(BaseModel):
    name: str


class PostInfo(BaseModel):
    required_degree: int | None = None
    address_list: list[Address] | None = None


class Record(BaseModel):
    id: str
    recruit_type: RecruitType
    job_post_info: PostInfo


class Portal(Desaysv):
    host = "hailiang.jobs.feishu.cn"
    portal = ""
    identity = ""
    unit = ""
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(self.identity in await session.page.content(), "海亮校园门户主体变化")
        await super().harvest()

    def before_detail(
        self,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job] | None:
        row = Record.model_validate(listing)
        kind = row.recruit_type
        check((kind.parent.id, kind.parent.name) == ("2", "校招"), "海亮岗位不是校园类型")
        check((kind.id, kind.name) in {("201", "正式"), ("202", "实习")}, "海亮招聘类型变化")
        check(listing_job is not None and listing_job.source_key == row.id, "海亮岗位身份不符")
        assert listing_job is not None
        listing_job.unit = self.unit
        degree = row.job_post_info.required_degree
        check(degree is None or degree in DEGREES, "海亮学历枚举变化")
        listing_job.education = DEGREES[degree] if degree is not None else ""
        listing_job.address = "；".join(
            dict.fromkeys(a.name for a in row.job_post_info.address_list or [] if a.name)
        )
        listing_job.field_sources.update(
            unit=f"公开校园门户主体：{self.portal}",
            education="job_post_info.required_degree与页面学历对照；缺失不猜测",
            address="job_post_info.address_list[].name",
        )
        return super().before_detail(
            entity,
            {"portal": self.portal, "record": listing},
            scope,
            listing_job,
            evidence=evidence,
        )

    def remember(self, entity: str, listing: object, jobs: list[Job]) -> None:
        super().remember(entity, {"portal": self.portal, "record": listing}, jobs)


class Education(Portal):
    portal = "583086"
    path = "/583086/position/list"
    detail_prefix = "/583086/position"
    identity = "海亮教育管理集团校招官网"
    unit = "海亮教育科技服务集团"


class Stock(Portal):
    portal = "campus"
    path = "/campus/position/list"
    identity = "浙江海亮股份招聘官网"
    unit = "浙江海亮股份有限公司"


class HailiangCampus(Adapter):
    name = "hailiang-campus-portals"
    host = Portal.host
    path = Education.path
    ready_endpoints = Portal.ready_endpoints
    scope_description = "海亮教育583086与股份campus两个现行公开校园门户全目录；排除实习"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        output = session.output
        seen: set[str] = set()
        for portal in (Education, Stock):
            try:
                session.output = output / portal.portal
                session.output.mkdir(parents=True, exist_ok=True)
                source = self.source.model_copy(update={"url": f"https://{self.host}{portal.path}"})
                result = await portal(
                    source, session, self.collected_at, self.as_of, incremental=self.incremental
                ).collect()
                for scope in result.scopes:
                    scope.name = f"{portal.portal}-{scope.name}"
                self.result.scopes.extend(result.scopes)
                self.result.issues.extend(result.issues)
                self.result.warnings.extend(result.warnings)
                for job in result.jobs:
                    if job.source_key in seen:
                        self.error(ValueError("海亮跨门户岗位ID重复，须核验归属"), job.source_key)
                        continue
                    seen.add(job.source_key)
                    self.result.jobs.append(job)
            except Exception as exc:
                self.error(exc, portal.portal)
            finally:
                session.output = output
