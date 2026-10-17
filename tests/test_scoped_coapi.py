from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from job_crawler.adapters.scoped_coapi import BcdhListedCampus, KsfCampus, ScopedCoapi
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, output: Path, cls: type[ScopedCoapi], failure: str = ""):
        self.output = output
        self.cls = cls
        self.failure = failure
        self.page = self
        self.config = SimpleNamespace(delay=0)
        self.queries: list[tuple[str, int]] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    def consume_request(self) -> None:
        pass

    async def content(self) -> str:
        if self.cls is KsfCampus:
            return (
                "".join(f'<a rel="{r}">{r}</a>' for r in ["a", "aa", "b", *map(str, range(1, 9))])
                + '<script>var params={ctmid:"8861224"}</script>'
            )
        return '<p data-id="1">首开股份</p><script src="js/job.js"></script>'

    async def request_html(self, url: str, *, validate_html: bool) -> str:
        assert not validate_html and url.endswith("/bcdh2026/js/job.js")
        return 'ctmid:"7324087"'

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("public callback")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("public callback")

    def row(self, key: str) -> dict[str, Any]:
        return {
            "jobid": key,
            "ctmid": self.cls.ctmid,
            "jobname": f"工程师{key}",
            "poscode": "C1a" if self.cls is KsfCampus else ("2" if key == "other" else "1"),
            "coname": "事业单位",
            "jobareaname": "北京",
            "issuedate": "2026-09-01",
            "degreefrom": "本科",
        }

    async def evaluate(self, script: str, arg: Any) -> dict[str, Any]:
        if isinstance(arg, dict):
            code, page = arg["poscode"], arg["pagenum"]
            assert arg["ctmid"] == self.cls.ctmid
            self.queries.append((code, page))
            total = (11 if code == "1a" else 0) if self.cls is KsfCampus else 2
            size = arg["pagesize"]
            ids = (
                [str(i) for i in range((page - 1) * size, min(page * size, total))]
                if self.cls is KsfCampus
                else ["0", "other"]
            )
            if self.failure == "duplicate" and page == 2:
                ids = ["0"]
            rows = [self.row(k) for k in ids]
            if rows and self.failure == "code":
                rows[0]["poscode"] = "unknown"
            if self.failure == "count" and page == 2:
                total += 1
            return {"status": "1", "resultbody": {"totalnum": str(total), "joblist": rows}}
        row = self.row(arg)
        row.update(status="24", jobinfo="岗位职责：<br>工程设计<br>任职要求：<br>土木工程本科")
        if self.failure == "detail" and arg == "0":
            row["ctmid"] = "wrong"
        return {"status": "1", "resultbody": row}


def source(cls: type[ScopedCoapi]) -> Source:
    return Source(
        source_id="COM0234" if cls is KsfCampus else "COM0448",
        company_id="company",
        company="测试公司",
        url=f"https://{cls.host}{cls.path}",
    )


async def test_all_sixteen_filters_and_paging(now: datetime, tmp_path: Path) -> None:
    replay = Replay(tmp_path, KsfCampus)
    result = await KsfCampus(source(KsfCampus), replay, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 11
    assert len(result.scopes) == 16 and len(replay.queries) == 17
    assert replay.queries[:2] == [("1a", 1), ("1a", 2)]
    assert all(s.terminal for s in result.scopes)


async def test_only_listed_company_not_group_sibling(now: datetime, tmp_path: Path) -> None:
    result = await BcdhListedCampus(
        source(BcdhListedCampus), Replay(tmp_path, BcdhListedCampus), now
    ).collect()
    assert not result.coverage_issues() and len(result.jobs) == 1
    assert result.scopes[0].skipped_out_of_scope == 1


@pytest.mark.parametrize("failure", ["duplicate", "code", "count", "detail"])
async def test_partial_failures_never_become_empty_success(
    now: datetime, tmp_path: Path, failure: str
) -> None:
    result = await KsfCampus(source(KsfCampus), Replay(tmp_path, KsfCampus, failure), now).collect()
    assert result.coverage_issues()
    assert result.scopes[-1].terminal
