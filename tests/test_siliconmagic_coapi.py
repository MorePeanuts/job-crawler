"""Silicon Magic's three COAPI categories retain distinct city job IDs."""

from datetime import datetime
from pathlib import Path
from typing import Any, cast

from job_crawler.adapters.coapi51 import SiliconMagic2027
from job_crawler.models import Source
from job_crawler.transport import Session


class Page:
    def __init__(self, *, bad_detail: bool = False, missing_tab: bool = False) -> None:
        self.bad_detail = bad_detail
        self.missing_tab = missing_tab
        self.rows = {
            "001": [self.row("101", "上海市", "001"), self.row("102", "杭州市", "001")],
            "002": [self.row("201", "深圳市", "002")],
            "003": [self.row("301", "杭州市", "003")],
        }

    @staticmethod
    def row(key: str, city: str, poscode: str) -> dict[str, str]:
        return {
            "jobid": key,
            "ctmid": "6389574",
            "jobname": "模拟IC设计工程师" if poscode == "001" else "工程师" + key,
            "coname": "芯迈半导体技术（杭州）股份有限公司",
            "term": "全职",
            "workyearname": "在校生/应届生",
            "poscode": poscode,
            "jobareaname": city,
            "issuedate": "2026-10-21 04:45:05",
        }

    async def content(self) -> str:
        last = "" if self.missing_tab else '<li data-poscode="003">技术类/管理类</li>'
        links = "".join(
            '<a href="https://xyz.51job.com/external/apply.aspx?'
            f'jobid={row["jobid"]}&ctmid=6389574">{row["jobareaname"]}</a>'
            for row in self.rows["001"]
        )
        return (
            '<ul class="jobtype"><li data-poscode="001">研发类</li>'
            f'<li data-poscode="002">销售类</li>{last}</ul>'
            f'<div class="jobs"><div class="jobinfo"><div class="apply">{links}</div></div></div>'
        )

    async def evaluate(self, script: str, arg: Any) -> dict[str, Any]:
        if "getJobList" in script:
            assert arg["ctmid"] == "6389574" and arg["pagesize"] == "2000"
            rows = self.rows[arg["poscode"]]
            return {"status": "1", "resultbody": {"totalnum": len(rows), "joblist": rows}}
        key = str(arg)
        row = next(r for rows in self.rows.values() for r in rows if r["jobid"] == key)
        detail = {
            **row,
            "jobid": "999" if self.bad_detail and key == "102" else key,
            "jobareaname": row["jobareaname"],
            "degreefrom": "本科",
            "funtype": "研发",
            "status": "24",
            "jobinfo": "岗位职责：设计芯片\n任职要求：本科毕业",
        }
        return {"resultbody": detail}


class Replay:
    last_evidence = "page"

    def __init__(self, output: Path, *, bad_detail: bool = False, missing_tab: bool = False):
        self.output = output
        self.page = Page(bad_detail=bad_detail, missing_tab=missing_tab)
        self.config = self
        self.delay = 0

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith("/SiliconMagic2026/job.html")

    def consume_request(self) -> None:
        pass


def source() -> Source:
    return Source(
        source_id="COM0582",
        company_id="COM0582",
        company="芯迈",
        url="https://campus.51job.com/SiliconMagic2026/job.html",
    )


async def test_siliconmagic_three_categories_keep_both_city_ids(
    now: datetime, tmp_path: Path
) -> None:
    result = await SiliconMagic2027(source(), cast(Session, Replay(tmp_path)), now).collect()
    assert not result.coverage_issues()
    assert [scope.expected for scope in result.scopes] == [2, 1, 1]
    assert all(scope.terminal and scope.details == scope.unique for scope in result.scopes)
    assert [job.source_key for job in result.jobs] == ["101", "102", "201", "301"]
    assert result.jobs[0].title == result.jobs[1].title


async def test_siliconmagic_rejects_missing_category_and_detail_mismatch(
    now: datetime, tmp_path: Path
) -> None:
    missing = await SiliconMagic2027(
        source(), cast(Session, Replay(tmp_path, missing_tab=True)), now
    ).collect()
    assert missing.coverage_issues()
    mismatch = await SiliconMagic2027(
        source(), cast(Session, Replay(tmp_path, bad_detail=True)), now
    ).collect()
    assert mismatch.coverage_issues()
    assert mismatch.scopes[0].details == 1
