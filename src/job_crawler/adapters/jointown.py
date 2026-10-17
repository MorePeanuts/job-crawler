"""Jointown's two official campus projects with global job-ID deduplication."""

from typing import cast
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.moka import Moka
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession

PROJECTS = {145419: "星辰校招生", 141506: "星九管培生"}


def validate_projects(html: str) -> None:
    doc = BeautifulSoup(html, "html.parser")
    check("九州通医药集团股份有限公司" in doc.get_text(), "九州通门户法人变化")
    found = {}
    for anchor in doc.select("a[title][href]"):
        parts = urlsplit(str(anchor["href"]))
        if "campus-recruitment" not in parts.path:
            continue
        check(
            parts.hostname == "app.mokahr.com"
            and parts.path.startswith("/campus-recruitment/jointown/"),
            "九州通校园导航组织/域名变化",
        )
        suffix = parts.path.rstrip("/").rsplit("/", 1)[-1]
        check(suffix.isdigit(), "九州通校园项目标识缺失")
        site = int(suffix)
        label = str(anchor["title"])
        check(site not in found or found[site] == label, "九州通项目名称冲突")
        found[site] = label
    check(found == PROJECTS, "九州通校园项目新增或缺失")


def merge_job(existing: Job, incoming: Job) -> None:
    excluded = {
        "source_url",
        "apply_url",
        "batch",
        "evidence",
        "field_sources",
        "collected_at",
        "first_seen_at",
        "detail_mode",
        "discovery_eligible",
    }
    check(
        existing.model_dump(exclude=excluded) == incoming.model_dump(exclude=excluded),
        "九州通跨项目同ID业务字段冲突",
    )
    existing.batch = "、".join(dict.fromkeys([*existing.batch.split("、"), incoming.batch]))
    existing.evidence = list(dict.fromkeys([*existing.evidence, *incoming.evidence]))


class Project(Moka):
    org = "jointown"

    def before_detail(
        self,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job] | None:
        return super().before_detail(
            entity,
            {"site_id": self.site_id, "record": listing},
            scope,
            listing_job,
            evidence=evidence,
        )

    def remember(self, entity: str, listing: object, jobs: list[Job]) -> None:
        for job in jobs:
            job.batch = PROJECTS[self.site_id]
        super().remember(entity, {"site_id": self.site_id, "record": listing}, jobs)


class Campus(Project):
    site_id = 145419
    path = "/campus-recruitment/jointown/145419#/jobs"


class Trainee(Project):
    site_id = 141506
    path = "/campus-recruitment/jointown/141506#/jobs"


class JointownCampus(Adapter):
    name = "jointown-campus-projects"
    host = "app.mokahr.com"
    path = "/campus-recruitment/jointown/145419"
    scope_description = "九州通星辰145419、星九141506双校园完整目录，按同租户源UUID核对跨项目去重"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        validate_projects(await session.page.content())
        nav_evidence = session.last_evidence
        output = session.output
        seen: dict[str, Job] = {}
        for project in (Campus, Trainee):
            try:
                session.output = output / str(project.site_id)
                session.output.mkdir(parents=True, exist_ok=True)
                source = self.source.model_copy(
                    update={"url": f"https://{project.host}{project.path}"}
                )
                result = await project(
                    source, session, self.collected_at, self.as_of, incremental=self.incremental
                ).collect()
                for scope in result.scopes:
                    scope.evidence.append(nav_evidence)
                self.result.scopes.extend(result.scopes)
                self.result.issues.extend(result.issues)
                self.result.warnings.extend(result.warnings)
                for job in result.jobs:
                    job.batch = PROJECTS[project.site_id]
                    job.evidence.append(nav_evidence)
                    previous = seen.get(job.source_key)
                    if previous is None:
                        seen[job.source_key] = job
                        self.result.jobs.append(job)
                    else:
                        merge_job(previous, job)
            except Exception as exc:
                self.error(exc, str(project.site_id))
            finally:
                session.output = output
