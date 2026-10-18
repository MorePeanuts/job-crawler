"""Do not accept an empty campus while an announcement branch is incomplete."""

import json
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.nbport import ENTRY, INFO, ROOT, SCOPES, NbportCampus
from job_crawler.models import Source
from job_crawler.transport import Session

FIX = Path(__file__).parent / "fixtures/nbport"


class Replay:
    last_evidence = "entry"

    def __init__(self, fault=""):
        self.fault = fault
        self.page = self
        self.url = ENTRY
        self.repeated = []
        self.current = "jobs"

    async def open(self, url, *, ready_endpoints):
        assert url in {ROOT + row[1] for row in SCOPES}
        assert len(ready_endpoints) == 1
        self.url = url
        self.current = {
            ROOT + row[1]: name
            for row, name in zip(SCOPES, ["jobs", "activity", "notices"], strict=True)
        }[url]

    def data(self, name, repeat=False):
        obj = json.loads((FIX / (name + ".json")).read_text())
        body = obj["body"]
        if name == "identity":
            if self.fault == "identity":
                body["Data"]["TenantId"] = 7
            return obj
        if name == "jobs":
            data = body["Data"]
            if self.fault == "filter":
                obj["url"] += "&ky=工程师"
            if self.fault == "response_filter":
                data["c2"] = "1"
            if self.fault == "rows":
                data["data"]["DataResult"] = [{"id": "x"}]
            if self.fault == "page_count":
                data["data"]["PageCount"] = 1
            if self.fault == "nonzero" or (self.fault == "changed" and repeat):
                data["data"].update(RowCount=1, DataResult=[{"id": "x"}])
            if self.fault == "business":
                body["Code"] = 403
            if self.fault == "missing":
                del data["data"]["RowCount"]
        if name == "activity":
            if self.fault == "activity":
                body["Data"] = [{"id": "new-campus-announcement"}]
            if self.fault == "failure":
                raise TimeoutError("activity unavailable")
            if self.fault == "shape":
                body["Data"] = {}
        return obj

    async def observed_path(self, endpoint):
        name = "identity" if endpoint == INFO else self.current
        obj = self.data(name)
        self.last_evidence = name
        return {"url": obj["url"], "body": json.dumps(obj["body"]), "post_data": None}

    async def request(self, url):
        self.repeated.append(self.current)
        obj = self.data(self.current, repeat=True)
        assert url == obj["url"]
        self.last_evidence = self.current + "-repeat"
        return obj["body"]

    def get_by_text(self, text, *, exact):
        assert text == "这里什么都没有..." and exact
        return self

    async def wait_for(self, **kwargs):
        if self.fault == "shell" and self.current == "jobs":
            raise TimeoutError("empty state missing")

    async def content(self):
        return "<html>这里什么都没有...</html>"

    def snapshot(self, label, html):
        return label


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "",
        "identity",
        "filter",
        "response_filter",
        "rows",
        "page_count",
        "nonzero",
        "changed",
        "business",
        "missing",
        "activity",
        "failure",
        "shape",
        "shell",
        "entry",
    ],
)
async def test_complete_or_partial(now, fault):
    replay = Replay(fault)
    source = Source(
        source_id="COM0438",
        company_id="COM0438",
        company="宁波舟山港股份有限公司",
        url=ENTRY.replace("jc=2", "jc=1") if fault == "entry" else ENTRY,
    )
    result = await NbportCampus(source, cast(Session, replay), now).collect()
    assert not result.jobs
    if not fault:
        assert not result.coverage_issues()
        assert len(result.scopes) == 3 and replay.repeated == ["jobs", "activity", "notices"]
        assert all(
            s.expected == s.listed == s.unique == s.details == 0 and s.terminal
            for s in result.scopes
        )
        assert all(len(s.evidence) == 4 for s in result.scopes)
    else:
        assert result.issues and result.coverage_issues()
        if fault not in {"identity", "entry"}:
            assert result.scopes[-1].terminal, (
                "a failed earlier branch must not erase later success"
            )
        if fault in {"nonzero", "activity"}:
            assert result.issues[0].code == "unsupported_scope"
