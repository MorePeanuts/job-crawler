"""Source-scoped daily detail reuse; a complete current list is always required."""

from datetime import datetime, timedelta
from pathlib import Path

from pydantic import Field, ValidationError

from job_crawler.config import IncrementalConfig
from job_crawler.filtering import Window, select
from job_crawler.models import Collection, Issue, Job, Model, Scope
from job_crawler.storage import Store, fingerprint


class DetailRecord(Model):
    listing_digest: str
    jobs: list[Job]
    fetched_at: datetime | None = None


class SourceHistory(Model):
    completed_at: datetime | None = None
    entries: dict[str, DetailRecord] = Field(default_factory=dict)
    present: list[str] = Field(default_factory=list)


class IncrementalSource:
    def __init__(
        self,
        store: Store,
        identity: str,
        window: Window,
        as_of: datetime,
        observed_at: datetime,
        config: IncrementalConfig,
    ) -> None:
        self.store = store
        self.identity = identity
        self.window = window
        self.as_of = as_of
        self.observed_at = observed_at
        self.config = config
        raw = store.load_history(identity)
        self.history = SourceHistory()
        self.warnings: list[Issue] = []
        if raw:
            try:
                self.history = SourceHistory.model_validate_json(raw)
                if self.history.completed_at is None or self.history.completed_at.tzinfo is None:
                    raise ValueError("历史时间无效")
            except (ValidationError, ValueError):
                self.warnings.append(
                    Issue(code="history_invalid", message="历史不可用，重新读取并建立基线")
                )
                self.history = SourceHistory()
        if self.history.completed_at and self.history.completed_at > observed_at:
            self.history = SourceHistory()
            self.warnings.append(Issue(code="history_future", message="历史来自未来时刻，不复用"))
        self.previous_present = set(self.history.present)
        self.seen: set[str] = set()
        self.pending: dict[str, DetailRecord] = {}
        self.handled_jobs: set[str] = set()

    def decorate(self, entity: str, jobs: list[Job]) -> list[Job]:
        old = self.history.entries.get(entity)
        prior = {job.key: job for job in old.jobs} if old else {}
        for job in jobs:
            previous = prior.get(job.key)
            job.first_seen_at = previous.first_seen_at if previous else self.observed_at
            job.discovery_eligible = (
                previous.discovery_eligible if previous else self.history.completed_at is not None
            )
            self.handled_jobs.add(job.key)
        return jobs

    def remember(self, entity: str, listing: object, jobs: list[Job]) -> None:
        self.seen.add(entity)
        self.pending[entity] = DetailRecord(
            listing_digest=fingerprint(listing),
            jobs=self.decorate(entity, jobs),
            fetched_at=self.observed_at,
        )

    def before_detail(
        self,
        entity: str,
        listing: object,
        scope: Scope,
        evidence: str,
        listing_job: Job | None = None,
    ) -> list[Job] | None:
        """Return resolved jobs (possibly empty announcement), or None to fetch."""
        self.seen.add(entity)
        if self.window != "day" or not self.config.enabled:
            return None
        if listing_job is not None:
            reason = select(listing_job, "day", self.as_of).reason
            if reason in {"outside_window", "expired"}:
                listing_job.detail_mode = "listing_only"
                listing_job.field_sources["detail"] = f"listing_prefilter:{reason}"
                self.pending[entity] = DetailRecord(
                    listing_digest=fingerprint(listing),
                    jobs=self.decorate(entity, [listing_job]),
                )
                if reason == "expired":
                    scope.skipped_expired += 1
                else:
                    scope.skipped_window += 1
                return [listing_job]
        previous = self.history.entries.get(entity)
        if (
            previous is None
            or entity not in self.previous_present
            or previous.listing_digest != fingerprint(listing)
            or previous.fetched_at is None
            or previous.fetched_at.tzinfo is None
            or not timedelta(0)
            <= self.observed_at - previous.fetched_at
            < timedelta(days=self.config.refresh_days)
            or any(j.detail_mode == "listing_only" for j in previous.jobs)
            or (
                entity.startswith("job:")
                and (
                    len(previous.jobs) != 1
                    or previous.jobs[0].source_key != entity.removeprefix("job:")
                )
            )
            or (
                entity.startswith("announcement:")
                and any(
                    not j.source_key.startswith(entity.removeprefix("announcement:") + ":")
                    for j in previous.jobs
                )
            )
            or len({j.key for j in previous.jobs}) != len(previous.jobs)
            or any(not Path(p).is_file() for j in previous.jobs for p in j.evidence)
        ):
            return None
        jobs = [job.model_copy(deep=True) for job in previous.jobs]
        for job in jobs:
            job.detail_mode = "cached"
            job.field_sources["detail"] = (
                f"history:{previous.fetched_at.isoformat()};current_list:{evidence}"
            )
            if evidence and evidence not in job.evidence:
                job.evidence.append(evidence)
            self.handled_jobs.add(job.key)
        self.pending[entity] = previous
        scope.reused_details += 1
        return jobs

    def finish(self, collection: Collection) -> None:
        # List APIs containing complete bodies still need discovery tracking, not extra requests.
        for job in collection.jobs:
            if job.key not in self.handled_jobs:
                self.remember(f"job:{job.source_key}", {"source_key": job.source_key}, [job])
        collection.warnings.extend(self.warnings)
        if self.window == "day" and self.history.completed_at is None:
            collection.warnings.append(
                Issue(
                    code="discovery_baseline",
                    message="本来源正在建立基线；无发布日期的存量不作为每日新增，完整数据保留在 jobs.json",
                )
            )
        if collection.coverage_issues() or len({j.key for j in collection.jobs}) != len(
            collection.jobs
        ):
            return
        snapshot = SourceHistory(
            completed_at=self.observed_at,
            entries={**self.history.entries, **self.pending},
            present=sorted(self.seen),
        )
        self.store.save_history(self.identity, snapshot.model_dump_json())
