from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from job_crawler.adapters.jianlong import JianlongCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, output: Path, failure: str = ""):
        self.output = output
        self.failure = failure
        self.config = SimpleNamespace(delay=0)
        self.page = self
        self.units: list[str] = []

    def consume_request(self) -> None:
        pass

    async def wait_for_selector(self, selector: str, **options: int) -> None:
        assert options == {"timeout": 30000}

    async def content(self) -> str:
        return '<div class="list"><div class="z"><li coid="1">公司1</li><li coid="2">公司2</li><li coid="3">公司3</li></div></div><div class="tel_top" jobid="11"></div><div class="tel_top" jobid="12"></div>'

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("COAPI uses the page's public callback")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("COAPI uses the page's public callback")

    @staticmethod
    def row(key: str, company: str) -> dict[str, Any]:
        return {
            "jobid": key,
            "coid": company,
            "ctmid": "9551405",
            "coname": f"公司{company}",
            "jobname": f"工程师{key}",
            "term": "全职",
            "issuedate": "2026-09-10",
            "jobareaname": "北京",
            "degreefrom": "硕士",
            "funtype": "矿业",
        }

    async def evaluate(self, script: str, arg: Any) -> dict[str, Any]:
        if isinstance(arg, dict):
            company = arg["coid"]
            self.units.append(company)
            assert arg["pagesize"] == 1000 and arg["ctmid"] == "9551405"
            keys = ["11", "12"] if company == "1" else [] if company == "2" else ["31"]
            if self.failure == "duplicate" and company == "3":
                keys = ["11"]
            rows = [self.row(key, company) for key in keys]
            total = len(rows) + (1 if self.failure == "count" and company == "3" else 0)
            return {"status": "1", "resultbody": {"totalnum": total, "joblist": rows}}
        company = "1" if arg.startswith("1") else "3"
        row = self.row(arg, company)
        if self.failure == "cross_company" and arg == "31":
            row["coid"] = "1"
        row.update(
            status="24", jobinfo="岗位职责：<br>矿山设计", major="采矿工程", address="园区一号"
        )
        return {"status": "1", "resultbody": row}


def source() -> Source:
    return Source(
        source_id="COM0120",
        company_id="COM0120",
        company="北京建龙重工集团有限公司",
        url="https://campus.51job.com/jljt2027/about.html",
    )


async def test_all_units_including_empty_and_detail_fields(now: datetime, tmp_path: Path) -> None:
    replay = Replay(tmp_path)
    result = await JianlongCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.units == ["1", "2", "3"] and len(result.jobs) == 3
    assert result.scopes[1].expected == 0 and result.scopes[1].terminal
    assert all(
        job.requirements == "专业要求：采矿工程" and job.address == "园区一号"
        for job in result.jobs
    )


@pytest.mark.parametrize("failure", ["duplicate", "count", "cross_company"])
async def test_company_errors_keep_prior_complete_units(
    now: datetime, tmp_path: Path, failure: str
) -> None:
    result = await JianlongCampus(source(), Replay(tmp_path, failure), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 2
    assert result.scopes[0].terminal and result.scopes[1].terminal
