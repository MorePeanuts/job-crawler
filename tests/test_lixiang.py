"""Offline checks for Li Auto's formal campus filter and detail contract."""

import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from test_adapters import source

from job_crawler.adapters.lixiang import API_ORIGIN, DETAIL_PATH, LIST_PATH, LiAutoCampus


def row(job_id: int) -> dict[str, Any]:
    return {
        "id": job_id,
        "code": f"A{job_id}",
        "title": f"正式工程师{job_id}",
        "hire_mode": 2,
        "job_mode_name": "正式",
        "location_title": "上海",
        "second_job_function_title": "研发",
    }


def detail_data(job_id: int) -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            **row(job_id),
            "description": "<p>研发系统</p>",
            "requirements": "<p>本科及以上</p>",
            "subject_name": (
                "2027“理想+”" if job_id == 2 else "实习生招聘" if job_id == 3 else "2027校园招聘"
            ),
            "department_title": "研发部门",
        },
    }


class Replay:
    last_evidence = "offline:lixiang"

    def __init__(self, *, repeated: bool = False, drift: bool = False, wrong: bool = False):
        self.repeated = repeated
        self.drift = drift
        self.wrong = wrong
        self.pages: list[int] = []
        self.details: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle == LIST_PATH:
            return {"url": f"{API_ORIGIN}{LIST_PATH}?page=1&page_size=10"}
        assert needle == f"{DETAIL_PATH}?"
        return {
            "url": f"{API_ORIGIN}{DETAIL_PATH}?job_id=1",
            "body": json.dumps(detail_data(1)),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is None
        p = urlsplit(url)
        q = parse_qs(p.query)
        if p.path == LIST_PATH:
            assert q["job_mode"] == ["1"] and q["page_size"] == ["100"]
            page = int(q["page"][0])
            self.pages.append(page)
            ids = range(1, 101) if page == 1 else [1 if self.repeated else 101]
            return {
                "code": 0,
                "data": {
                    "page": page,
                    "page_size": 100,
                    "total_pages": 2,
                    "total_count": 102 if self.drift and page == 2 else 101,
                    "items": [row(i) for i in ids],
                },
            }
        assert p.path == DETAIL_PATH and detail is True
        job_id = int(q["job_id"][0])
        self.details.append(job_id)
        return detail_data(999 if self.wrong and job_id == 2 else job_id)


async def test_li_auto_reads_formal_pages_and_full_details(now: datetime) -> None:
    replay = Replay()
    result = await LiAutoCampus(source(LiAutoCampus.host), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert len(result.jobs) == 101 and len(replay.details) == 100
    assert result.jobs[0].duties == "研发系统"
    assert result.jobs[0].requirements == "本科及以上"
    assert result.jobs[0].published == ""
    assert result.jobs[1].work_type == "校招"
    assert result.jobs[2].work_type == "实习"


async def test_li_auto_total_drift_preserves_first_page_details(now: datetime) -> None:
    result = await LiAutoCampus(source(LiAutoCampus.host), Replay(drift=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 100
    assert any("总数变化" in issue.message for issue in result.issues)


async def test_li_auto_duplicate_page_preserves_first_page_details(now: datetime) -> None:
    result = await LiAutoCampus(source(LiAutoCampus.host), Replay(repeated=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 100
    assert any(issue.code == "duplicate_page" for issue in result.issues)


async def test_li_auto_wrong_detail_is_partial(now: datetime) -> None:
    result = await LiAutoCampus(source(LiAutoCampus.host), Replay(wrong=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 100
    assert any(issue.job_key == "2" for issue in result.issues)
