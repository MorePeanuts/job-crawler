"""BlueFocus's current campus portal, separate from its mixed root catalog."""

from typing import cast

from pydantic import BaseModel

from job_crawler.adapters.feishu import LIST_PATH, Desaysv
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession


class Kind(BaseModel):
    id: str
    name: str


class RecruitType(Kind):
    parent: Kind


class Address(BaseModel):
    name: str


class PostInfo(BaseModel):
    address_list: list[Address] | None = None


class Record(BaseModel):
    id: str
    recruit_type: RecruitType
    job_post_info: PostInfo


class BlueFocus(Desaysv):
    name = "feishu-bluefocus-campus"
    host = "bluefocus.jobs.feishu.cn"
    path = "/066083/position/list"
    detail_prefix = "/066083/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "蓝色光标官网指向的066083正式校园门户全目录；排除实习及根目录社招"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check("加入蓝色光标集团" in await session.page.content(), "蓝色光标校园门户身份变化")
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
        check((kind.parent.id, kind.parent.name) == ("2", "校招"), "蓝色光标岗位不是校园类型")
        check((kind.id, kind.name) in {("201", "正式"), ("202", "实习")}, "招聘子类型变化")
        check(listing_job is not None and listing_job.source_key == row.id, "蓝色光标岗位身份不符")
        assert listing_job is not None
        listing_job.address = "；".join(
            dict.fromkeys(a.name for a in row.job_post_info.address_list or [] if a.name)
        )
        listing_job.field_sources["address"] = "job_post_info.address_list[].name"
        return super().before_detail(entity, listing, scope, listing_job, evidence=evidence)
