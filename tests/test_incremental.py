"""Count requests with deterministic site replays, never real recruitment traffic."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_adapters import Replay as PlatformReplay
from test_zhiye import Replay, source

from job_crawler.adapters.platforms import CCB, CNPC, Alibaba, Pingan
from job_crawler.adapters.zhiye import Xiangyu
from job_crawler.config import IncrementalConfig
from job_crawler.filtering import Window, select
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Collection, Issue, Job, Scope, Source
from job_crawler.storage import Store


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    value = Store(tmp_path / "state.sqlite")
    yield value
    value.close()


def context(
    store: Store,
    now: datetime,
    window: Window = "day",
    identity: str = "test",
    *,
    enabled: bool = True,
) -> IncrementalSource:
    return IncrementalSource(store, identity, window, now, now, IncrementalConfig(enabled=enabled))


def complete(jobs: list[Job]) -> Collection:
    n = len(jobs)
    return Collection(
        jobs=jobs,
        scopes=[
            Scope(
                name="jobs",
                expected=n,
                listed=n,
                unique=n,
                details=n,
                terminal=True,
            )
        ],
    )


def seed(store: Store, now: datetime, job: Job) -> None:
    baseline = context(store, now, "all")
    baseline.remember("job:1", {"id": "1"}, [job])
    baseline.finish(complete([job]))


class DailyReplay(Replay):
    def __init__(
        self,
        evidence: Path,
        count: int = 21,
        dates: dict[str, str] | None = None,
        *,
        changed: set[str] | None = None,
        mismatch: bool = False,
    ):
        super().__init__(count=count, mismatch=mismatch)
        self.dates = dates or {}
        self.changed = changed or set()
        evidence.write_text("synthetic evidence")
        self.last_evidence = str(evidence)

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        result = await super().request(url, payload=payload, detail=detail)
        if payload is not None:
            for row in result["Data"]:
                row["PostDate"] = self.dates.get(row["Id"], "")
                row["JobAdName"] = f"工程师{row['Id']}"
                if row["Id"] in self.changed:
                    row["ChangeDate"] = "2026-10-11"
        return result


async def collect(replay: DailyReplay, ctx: IncrementalSource) -> Collection:
    result = await Xiangyu(source(), replay, ctx.observed_at, ctx.as_of, incremental=ctx).collect()
    ctx.finish(result)
    return result


async def test_1000_jobs_daily_prefilter_reduces_1050_to_70_requests(
    store: Store,
    tmp_path: Path,
    now: datetime,
) -> None:
    # New jobs are on the last page: seeing old rows must not terminate pagination.
    dates = {str(i): "2026-09-01" if i < 980 else "2026-10-10" for i in range(1000)}
    control = DailyReplay(tmp_path / "control.json", 1000, dates)
    original = await collect(control, context(store, now, identity="control", enabled=False))
    optimized = DailyReplay(tmp_path / "optimized.json", 1000, dates)
    result = await collect(optimized, context(store, now, identity="optimized"))
    assert not original.coverage_issues() and not result.coverage_issues()
    assert len(control.pages) == len(optimized.pages) == 50
    assert len(control.details) == 1000 and len(optimized.details) == 20
    assert result.scopes[0].skipped_window == 980
    assert {j.key for j in original.jobs if select(j, "day", now).kind == "include"} == {
        j.key for j in result.jobs if select(j, "day", now).kind == "include"
    }


async def test_undated_baseline_hot_cache_new_changed_and_all_refresh(
    store: Store,
    tmp_path: Path,
    now: datetime,
) -> None:
    first = DailyReplay(tmp_path / "first.json")
    baseline = await collect(first, context(store, now, "all"))
    assert len(first.details) == 21
    tomorrow = now + timedelta(days=1)
    hot = DailyReplay(tmp_path / "hot.json")
    result = await collect(hot, context(store, tomorrow))
    assert not hot.details and len(hot.opens) == 1 and hot.pages == [0, 1]
    assert result.scopes[0].reused_details == 21 and not result.coverage_issues()
    assert all(j.collected_at == now and j.detail_mode == "cached" for j in result.jobs)
    assert all(select(j, "day", tomorrow).reason == "undated_baseline" for j in result.jobs)
    changed = DailyReplay(tmp_path / "changed.json", 22, changed={"2"})
    new = await collect(changed, context(store, tomorrow + timedelta(hours=1)))
    assert set(changed.details) == {"2", "21"}
    added = next(j for j in new.jobs if j.source_key == "21")
    assert added.published == "" and added.discovery_eligible
    assert (
        select(added, "day", tomorrow + timedelta(hours=1)).reason
        == "first_discovered_without_publication"
    )
    assert select(added, "day", tomorrow, include_undated_new=False).reason == "missing_publication"
    assert not next(j for j in new.jobs if j.source_key == "2").discovery_eligible
    refresh = DailyReplay(tmp_path / "all.json", 22, changed={"2"})
    full = await collect(refresh, context(store, tomorrow + timedelta(hours=2), "all"))
    assert len(refresh.details) == 22 and full.scopes[0].reused_details == 0
    assert baseline.jobs[0].collected_at == now


@pytest.mark.parametrize(
    "published,skip",
    [
        ("2026-10-08", True),
        ("2026-10-09", False),
        ("2026-10-09T11:59:59+08:00", True),
        ("2026-10-09T12:00:00+08:00", False),
        ("2026-10-11", False),
        ("bad-date", False),
        ("", False),
    ],
)
async def test_listing_date_boundaries_and_unknowns(
    store: Store,
    tmp_path: Path,
    now: datetime,
    published: str,
    skip: bool,
) -> None:
    replay = DailyReplay(tmp_path / "evidence.json", 1, {"0": published})
    result = await collect(replay, context(store, now))
    assert len(replay.details) == (0 if skip else 1)
    assert result.scopes[0].skipped_window == int(skip)
    assert not result.coverage_issues()
    if not published:
        assert select(result.jobs[0], "day", now).reason == "undated_baseline"
    if published == "bad-date":
        assert select(result.jobs[0], "day", now).reason == "unparsed_publication"


@pytest.mark.parametrize(
    "window,elapsed,reuse",
    [
        ("day", 14, True),
        ("day", 15, False),
        ("all", 1, False),
        ("week", 1, False),
    ],
)
def test_cache_expiry_and_full_refresh(
    store: Store,
    now: datetime,
    job: Job,
    window: Window,
    elapsed: int,
    reuse: bool,
) -> None:
    seed(store, now, job)
    ctx = context(store, now + timedelta(days=elapsed), window)
    scope = Scope(name="jobs")
    result = ctx.before_detail("job:1", {"id": "1"}, scope, "")
    assert (result is not None) == reuse
    assert scope.reused_details == int(reuse)


def test_reappearance_failed_source_and_identity_isolation(
    store: Store,
    now: datetime,
    job: Job,
) -> None:
    seed(store, now, job)
    original = store.load_history("test")
    failed = context(store, now + timedelta(days=1))
    failed.finish(Collection(issues=[Issue(code="failed", message="failure")]))
    assert store.load_history("test") == original
    other = context(store, now + timedelta(days=1), identity="different-code-or-source")
    assert other.before_detail("job:1", {"id": "1"}, Scope(name="jobs"), "") is None
    empty = context(store, now + timedelta(days=1))
    empty.finish(complete([]))
    reappeared = context(store, now + timedelta(days=2))
    assert reappeared.before_detail("job:1", {"id": "1"}, Scope(name="jobs"), "") is None
    reappeared.remember("job:1", {"id": "1"}, [job])
    assert job.first_seen_at == now and not job.discovery_eligible


def test_missing_evidence_corrupt_cache_and_partial_cold_start(
    store: Store,
    tmp_path: Path,
    now: datetime,
    job: Job,
) -> None:
    job.evidence = [str(tmp_path / "missing.json")]
    seed(store, now, job)
    ctx = context(store, now + timedelta(days=1))
    assert ctx.before_detail("job:1", {"id": "1"}, Scope(name="jobs"), "") is None
    store.save_history("bad", '{"entries":{"wrong":1}}')
    corrupt = context(store, now, identity="bad")
    assert corrupt.warnings[0].code == "history_invalid"
    partial = context(store, now, identity="partial")
    partial.remember("job:1", {}, [job])
    result = complete([job])
    result.scopes[0].terminal = False
    partial.finish(result)
    assert store.load_history("partial") is None


def test_cached_detail_keeps_content_time_but_updates_last_seen(
    store: Store,
    now: datetime,
    job: Job,
) -> None:
    store.save([job], observed_at=now)
    store.save([job], observed_at=now + timedelta(days=1))
    first, last = store.db.execute(
        "SELECT first_seen,last_seen FROM records WHERE key=?", (job.key,)
    ).fetchone()
    assert first == now.isoformat()
    assert last == (now + timedelta(days=1)).isoformat()
    assert job.collected_at == now


def test_expired_listing_is_accounted_without_fetch(
    store: Store,
    now: datetime,
    job: Job,
) -> None:
    job.deadline = "2026-10-09"
    scope = Scope(name="jobs", expected=1, listed=1, unique=1, terminal=True)
    resolved = context(store, now).before_detail("job:1", {}, scope, "", job)
    assert resolved and resolved[0].detail_mode == "listing_only"
    assert scope.skipped_expired == 1
    assert not Collection(jobs=resolved, scopes=[scope]).coverage_issues()


@pytest.mark.parametrize("platform", ["ccb", "cnpc"])
async def test_platform_detail_reuse_and_announcement_expansion(
    store: Store,
    tmp_path: Path,
    now: datetime,
    platform: str,
) -> None:
    cls = CCB if platform == "ccb" else CNPC
    src = Source(source_id="TEST", company_id="TEST", company="测试", url=f"https://{cls.host}")
    evidence = tmp_path / "evidence.json"
    evidence.write_text("synthetic evidence")
    first = PlatformReplay(platform)
    first.last_evidence = str(evidence)
    initial = context(store, now, "all")
    baseline = await cls(src, first, now, incremental=initial).collect()
    initial.finish(baseline)
    second = PlatformReplay(platform)
    second.last_evidence = str(evidence)
    tomorrow = now + timedelta(days=1)
    daily = context(store, tomorrow)
    result = await cls(src, second, tomorrow, incremental=daily).collect()
    daily.finish(result)
    assert not result.coverage_issues()
    assert not any(detail for _, _, detail in second.calls)
    assert len(second.opened) == 1
    assert len(result.jobs) == 2
    assert result.scopes[0].reused_details == (2 if platform == "ccb" else 1)


@pytest.mark.parametrize(
    "published,expected_details", [("2026-09-01", 0), ("2026-10-10", 2), ("", 2)]
)
async def test_ccb_prefilters_only_reliable_old_list_dates(
    store: Store,
    now: datetime,
    published: str,
    expected_details: int,
) -> None:
    class Dates(PlatformReplay):
        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            response = await super().request(url, payload=payload, detail=detail)
            if "planPostList" in response:
                for row in response["planPostList"]:
                    row["postDate"] = published
            else:
                response["endTime"] = ""
            return response

    replay = Dates("ccb")
    src = Source(source_id="TEST", company_id="TEST", company="测试", url="https://job2.ccb.cn")
    result = await CCB(src, replay, now, incremental=context(store, now)).collect()
    assert not result.coverage_issues()
    assert sum(detail for _, _, detail in replay.calls) == expected_details
    assert all(j.published == published for j in result.jobs)


@pytest.mark.parametrize("platform", ["pingan", "alibaba"])
async def test_complete_list_bodies_track_first_discovery_without_extra_requests(
    store: Store,
    now: datetime,
    platform: str,
) -> None:
    cls = Pingan if platform == "pingan" else Alibaba
    src = Source(source_id="TEST", company_id="TEST", company="测试", url=f"https://{cls.host}")
    empty = context(store, now, "all")
    empty.finish(complete([]))
    daily = context(store, now + timedelta(days=1))
    replay = PlatformReplay(platform)
    result = await cls(src, replay, daily.observed_at, incremental=daily).collect()
    daily.finish(result)
    assert not result.coverage_issues()
    assert all(j.discovery_eligible for j in result.jobs)
    assert not any(detail for _, _, detail in replay.calls)
