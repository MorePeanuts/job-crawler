"""Huafa's actual nine expired campus records and explicit empty group channel."""

import copy
import json
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.huafa import CAMPAIGN, GROUP, GROUP_LIST, GROUP_TERMS, HuafaListedCampus
from job_crawler.filtering import select
from job_crawler.models import Source
from job_crawler.transport import Session

FIX = Path(__file__).parent / "fixtures/huafa"
CAT = json.loads((FIX / "catalog.json").read_text())
GROUP_DATA = json.loads((FIX / "group.json").read_text())


class Replay:
    last_evidence = "initial"

    def __init__(self, fault=""):
        self.fault = fault
        self.current = ""
        self.page = self
        self.calls = []

    async def open(self, url, *, ready_endpoints=()):
        self.current = url
        self.calls.append(url)
        assert "/apply" not in url

    async def content(self):
        if self.current == CAMPAIGN:
            s = (FIX / "campaign.html").read_text()
            return (
                s.replace("SU67b2e3bb1eb80555b7a457f7", "other-suite")
                if self.fault == "entry"
                else s
            )
        return (FIX / "group.html").read_text()

    def snapshot(self, label, html):
        self.last_evidence = label
        return label

    async def observed(self, needle):
        if needle == GROUP_TERMS:
            return {
                "url": "https://wecruit.hotjob.cn" + GROUP_TERMS,
                "body": json.dumps({"state": "200", "data": {}}),
            }
        if needle == GROUP_LIST:
            d = GROUP_DATA.copy()
            if self.fault == "filter":
                d["post_data"] += "&orgId=123"
            return d
        assert needle == HuafaListedCampus.endpoint
        return {"url": CAT["url"]}

    async def request(self, url, *, form=None, detail=False):
        self.calls.append(url)
        self.last_evidence = url
        if GROUP_LIST in url:
            d = copy.deepcopy(GROUP_DATA["body"])
            if self.fault == "nonzero":
                d["data"]["pageForm"].update(dataCount=1, pageData=[{"postId": 99}])
            if self.fault == "group_count":
                d["data"]["positonNum"] = 1
            if self.fault == "group_failure":
                d["state"] = "500"
            return d
        assert parse_qs(urlsplit(url).query)["page"] == ["1"]
        d = copy.deepcopy(CAT["body"])
        row = d["postList"][0]
        if self.fault == "unit":
            row["orgName"] = "母集团另一上市公司"
        if self.fault == "date":
            row["publishDateTime"] = "2025-03-01 11:00:00"
        if self.fault == "deadline":
            row["endDate"] = "unknown"
        if self.fault == "permanent":
            row["isLongTermRelease"] = 1
        if self.fault == "body":
            row["serviceCondition"] = ""
        if self.fault == "count":
            d["postList"].pop()
        if self.fault == "duplicate":
            d["postList"][-1] = row.copy()
        return d


def make(replay, now):
    return HuafaListedCampus(
        Source(
            source_id="COM0223",
            company_id="COM0223",
            company="珠海华发实业股份有限公司",
            url="https://sc.hotjob.cn/wt/huafa/web/index/campus",
        ),
        cast(Session, replay),
        now,
    )


@pytest.mark.asyncio
async def test_actual_expired_nine_and_group_zero(now):
    replay = Replay()
    result = await make(replay, now).collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == 9
    assert result.scopes[0].skipped_expired == 9 and result.scopes[0].details == 0
    assert result.scopes[1].expected == 0 and result.scopes[1].terminal
    assert all(select(j, "all", now).reason == "expired" for j in result.jobs)
    assert result.jobs[0].published == "2025-02-26" and result.jobs[0].deadline == "2026-02-26"
    assert "租金收缴率" in result.jobs[0].duties and "本科" in result.jobs[0].requirements
    assert CAMPAIGN in replay.calls and GROUP in replay.calls
    assert not any(
        "getOnePosition" in u for u in replay.calls
    )  # Full body is already in public list.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["unit", "date", "deadline", "permanent", "body", "count", "duplicate"]
)
async def test_legacy_contract_fails_without_hiding_group_scope(fault, now):
    result = await make(Replay(fault), now).collect()
    assert result.coverage_issues()
    assert result.scopes[1].terminal


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["entry", "filter", "group_count", "group_failure", "nonzero"])
async def test_group_failures_retain_legacy_jobs(fault, now):
    result = await make(Replay(fault), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 9
    assert result.scopes[0].terminal and not result.scopes[1].terminal
    if fault == "nonzero":
        assert any(i.code == "unsupported_scope" for i in result.issues)
