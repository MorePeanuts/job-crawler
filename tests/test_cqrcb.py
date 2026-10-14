from datetime import datetime
from pathlib import Path
from typing import Any

from job_crawler.adapters.coapi51 import Cqrcb2027
from job_crawler.config import CrawlConfig
from job_crawler.models import Source


class Session:
    last_evidence = "fixture"

    def __init__(self, output: Path, *, wrong_detail: bool = False):
        self.output = output
        self.page = self
        self.config = CrawlConfig(delay=0)
        self.wrong_detail = wrong_detail
        self.details: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://campus.51job.com/CQRCB2027/job.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("不应观察接口")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("不应直接请求 JSON")

    def consume_request(self) -> None:
        pass

    async def evaluate(self, script: str, value: Any = None) -> Any:
        codes = [
            "A",
            "B",
            "C",
            *(f"D{i}" for i in range(1, 7)),
            *(f"E{i:02}" for i in range(1, 43)),
            *(f"F{i}" for i in range(1, 5)),
        ]
        if "JOB_NAV_DATA" in script:
            return codes
        if isinstance(value, dict):
            assert value["ctmid"] == "9586513"
            assert value["poscode"] == "" and value["pagesize"] == 2000
            return {
                "resultbody": {
                    "totalnum": 55,
                    "joblist": [
                        {
                            "jobid": str(i),
                            "ctmid": "9586513",
                            "poscode": code,
                            "jobname": f"岗位{code}",
                            "coname": "重庆农村商业银行股份有限公司",
                            "term": "全职",
                            "issuedate": "2026-10-10",
                        }
                        for i, code in enumerate(codes, 1)
                    ],
                }
            }
        self.details.append(str(value))
        code = codes[int(value) - 1]
        return {
            "resultbody": {
                "jobid": str(value),
                "ctmid": "9586513",
                "poscode": "F1" if self.wrong_detail and code == "B" else code,
                "coname": "重庆农村商业银行股份有限公司",
                "jobname": f"岗位{code}",
                "jobinfo": "岗位职责：负责研发 任职要求：本科及以上",
                "jobareaname": "重庆",
                "degreefrom": "本科",
                "status": "24",
            }
        }


def source() -> Source:
    return Source(
        source_id="COM0309",
        company_id="COM0309",
        company="重庆农村商业银行股份有限公司",
        url="https://campus.51job.com/CQRCB2027/job.html",
    )


async def test_cqrcb_excludes_other_legal_branches(tmp_path: Path, now: datetime) -> None:
    session = Session(tmp_path)
    result = await Cqrcb2027(source(), session, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].unique == 55
    assert result.scopes[0].skipped_out_of_scope == 5
    assert result.scopes[0].details == len(result.jobs) == 50
    assert len(session.details) == 50
    assert {job.source_key for job in result.jobs}.isdisjoint({"1", "52", "53", "54", "55"})


async def test_cqrcb_rejects_detail_code_conflict(tmp_path: Path, now: datetime) -> None:
    result = await Cqrcb2027(source(), Session(tmp_path, wrong_detail=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 49
    assert any(issue.job_key == "2" for issue in result.issues)
