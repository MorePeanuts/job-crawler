"""Offline contract checks for the observed PDD graduate APIs."""

import json
from datetime import datetime
from typing import Any

from test_adapters import source

from job_crawler.adapters.pdd import DETAIL_PATH, LIST_PATH, PddCampus


def listing(job_id: int) -> dict[str, Any]:
    return {
        "id": str(job_id),
        "name": f"研发工程师{job_id}",
        "workLocationName": "上海",
        "jobName": "研发",
        "releaseTime": 1788315871000,
        "graduationYear": "2027",
    }


def detail_data(job_id: int) -> dict[str, Any]:
    return {
        "success": True,
        "result": {
            **listing(job_id),
            "jobDuty": "构建训练平台",
            "serveRequirement": "硕士及以上学历",
            "normal": True,
        },
    }


class Replay:
    last_evidence = "offline:pdd"

    def __init__(self, *, repeat: bool = False, drift: bool = False, wrong_detail: bool = False):
        self.repeat = repeat
        self.drift = drift
        self.wrong_detail = wrong_detail
        self.pages: list[int] = []
        self.details: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle == LIST_PATH:
            return {
                "url": f"https://{PddCampus.host}{LIST_PATH}",
                "post_data": json.dumps({"page": 1, "pageSize": 10, "t": None}),
            }
        assert needle == DETAIL_PATH
        return {
            "url": f"https://{PddCampus.host}{DETAIL_PATH}",
            "post_data": json.dumps({"id": "1", "t": None}),
            "body": json.dumps(detail_data(1)),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None
        if url.endswith(LIST_PATH):
            page = payload["page"]
            self.pages.append(page)
            rows = (
                [listing(i) for i in range(1, 11)]
                if page == 1
                else [listing(1 if self.repeat else 11)]
            )
            return {
                "success": True,
                "result": {"total": 12 if self.drift and page == 2 else 11, "list": rows},
            }
        assert url.endswith(DETAIL_PATH) and detail is True
        job_id = payload["id"]
        self.details.append(job_id)
        return detail_data(99 if self.wrong_detail and job_id == "2" else int(job_id))


async def test_pdd_enumerates_all_pages_and_keeps_source_date(now: datetime) -> None:
    replay = Replay()
    result = await PddCampus(source(PddCampus.host), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert len(result.jobs) == 11
    assert len(replay.details) == 10  # first detail is reused from the observed page response
    assert result.jobs[0].published.startswith("2026-09-02T")
    assert result.jobs[0].requirements == "硕士及以上学历"


async def test_pdd_repeated_page_does_not_claim_complete(now: datetime) -> None:
    result = await PddCampus(source(PddCampus.host), Replay(repeat=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 10
    assert any(issue.code == "duplicate_page" for issue in result.issues)


async def test_pdd_wrong_detail_keeps_other_jobs_but_is_partial(now: datetime) -> None:
    result = await PddCampus(source(PddCampus.host), Replay(wrong_detail=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 10
    assert any(issue.job_key == "2" for issue in result.issues)


async def test_pdd_total_drift_is_partial(now: datetime) -> None:
    result = await PddCampus(source(PddCampus.host), Replay(drift=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 10
    assert any("总数变化" in issue.message for issue in result.issues)
