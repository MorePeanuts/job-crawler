"""石药校园频道的公开单页目录与范围回放。"""

import json
from datetime import datetime
from typing import Any, cast
from urllib.parse import urlencode

import pytest

from job_crawler.adapters.cspc import CHANNEL_ID, CHANNEL_URL, LIST_PATH, CspcCampus
from job_crawler.models import Source
from job_crawler.transport import Session


def row(key: str, *, applicant: str = "应届生", age: str = "-2") -> dict[str, Any]:
    return {
        "REQUEST_ID": key,
        "PUBLISH_NAME": f"岗位{key}",
        "ORG_ALIAS_NAME": "石药招聘单位",
        "item2": applicant,
        "item5": "全职",
        "WORK_AGE": age,
        "item1": "本科",
        "work_place": "河北省石家庄市",
        "JOB_DUTY": "岗位职责：研发工作",
        "JOB_REQUEST": "任职要求：本科及以上",
        "APPLY_TIME": "2026-10-20",
        "UPDATE_TIME": "2026-10-20 10:00:00",
        "EXPECT_DATE": "无",
    }


class Page:
    def __init__(self, html: str):
        self.html = html

    async def content(self) -> str:
        return self.html


class Replay:
    def __init__(self, rows: list[dict[str, Any]], *, link: str = CHANNEL_URL):
        self.rows = rows
        self.page = Page(f'<a href="{link}">校园招聘</a>')
        self.last_evidence = "replay.json"
        self.opens: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opens.append(url)

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == LIST_PATH
        return {
            "url": f"https://ehr.e-cspc.com:8081{LIST_PATH}",
            "post_data": urlencode(
                {
                    "channelQrId": CHANNEL_ID,
                    "root_id": "cspc",
                    "sortName": "zri.ext_rankNum",
                    "push_request_id": ",".join(row["REQUEST_ID"] for row in self.rows),
                }
            ),
            "body": json.dumps({"state": "1", "total": "", "jsonList": self.rows}),
        }


def adapter(replay: Replay) -> CspcCampus:
    source = Source(
        source_id="COM0490",
        company_id="COM0490",
        company="石药集团有限公司",
        url="https://www.e-cspc.com/hr/",
    )
    return CspcCampus(source, cast(Session, replay), datetime(2026, 10, 20))


@pytest.mark.asyncio
async def test_full_channel_filters_scope_and_preserves_date_semantics() -> None:
    replay = Replay(
        [row("a"), row("b", applicant="在校生", age="-3"), row("c", applicant="2年", age="2")]
    )
    replay.page.html += f'<a href="{CHANNEL_URL}">校园招聘</a>'
    result = await adapter(replay).collect()
    assert replay.opens == ["https://www.e-cspc.com/hr/", CHANNEL_URL]
    assert not result.coverage_issues()
    assert (
        result.scopes[0].listed,
        result.scopes[0].details,
        result.scopes[0].skipped_out_of_scope,
    ) == (3, 1, 2)
    assert len(result.jobs) == 1
    assert result.jobs[0].source_key == "a"
    assert result.jobs[0].location == "河北省/石家庄市"
    assert result.jobs[0].published == result.jobs[0].deadline == ""
    assert result.jobs[0].duties == "研发工作"


@pytest.mark.asyncio
async def test_wrong_official_link_does_not_use_other_portal() -> None:
    result = await adapter(Replay([row("a")], link="https://other.example/campus")).collect()
    assert result.coverage_issues()
    assert not result.jobs


@pytest.mark.asyncio
async def test_duplicate_and_missing_body_keep_partial() -> None:
    duplicate = await adapter(Replay([row("a"), row("a")])).collect()
    assert duplicate.coverage_issues()
    assert not duplicate.jobs
    broken = row("b")
    broken["JOB_REQUEST"] = ""
    partial = await adapter(Replay([row("a"), broken])).collect()
    assert len(partial.jobs) == 1
    assert partial.coverage_issues()
    assert partial.issues[0].job_key == "b"


@pytest.mark.asyncio
async def test_unknown_applicant_code_fails_closed() -> None:
    result = await adapter(Replay([row("a", applicant="不限", age="-2")])).collect()
    assert not result.jobs
    assert result.coverage_issues()
