from datetime import datetime
from pathlib import Path
from typing import Any

from job_crawler.adapters.coapi51 import Cimc2027
from job_crawler.config import CrawlConfig
from job_crawler.models import Source


class Page:
    def __init__(self, session: "Session"):
        self.session = session

    def locator(self, selector: str) -> "Page":
        assert selector == "#job-list tr[rel]"
        return self

    @property
    def first(self) -> "Page":
        return self

    async def wait_for(self, **kwargs: int) -> None:
        assert kwargs == {"timeout": 20000}

    async def content(self) -> str:
        cards = "".join(f'<tr rel="{i}"></tr>' for i in range(1, 11))
        return (
            '<tbody id="job-list">'
            + cards
            + '</tbody><script>var coid = {"Z":"中集集团总部","A02":"宁波中集"};</script>'
        )

    async def evaluate(self, script: str, value: Any = None) -> dict[str, Any]:
        if isinstance(value, dict):
            assert value["ctmid"] == "7973180"
            assert value["pagenum"] == 1 and value["pagesize"] == 2000
            assert value["poscode"] == value["divid"] == value["jobarea"] == ""
            return {
                "resultbody": {
                    "totalnum": 11,
                    "joblist": [
                        {
                            "jobid": str(i),
                            "ctmid": "7973180",
                            "jobname": f"研发岗位{i}",
                            "poscode": "Z" if i == 11 else "A02",
                            "coname": "中国国际海运集装箱（集团）股份有限公司",
                            "term": "全职",
                            "issuedate": "2026-10-15",
                        }
                        for i in range(1, 12)
                    ],
                }
            }
        self.session.details.append(str(value))
        return {
            "resultbody": {
                "jobid": str(value),
                "ctmid": "7973180",
                "jobname": f"研发岗位{value}",
                "poscode": "Z" if value == "11" else "A02",
                "coname": "中国国际海运集装箱（集团）股份有限公司",
                "term": "实习" if self.session.bad_detail and value == "2" else "全职",
                "jobinfo": "岗位职责：技术研发。任职要求：本科及以上。",
                "status": "24",
            }
        }


class Session:
    last_evidence = "fixture"

    def __init__(self, output: Path, *, bad_detail: bool = False):
        self.output = output
        self.page = Page(self)
        self.config = CrawlConfig(delay=0)
        self.bad_detail = bad_detail
        self.details: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://campus.51job.com/cimc/post.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected observation: {needle}")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError(f"unexpected request: {url}")

    def consume_request(self) -> None:
        pass


def source() -> Source:
    return Source(
        source_id="COM0163",
        company_id="COM0163",
        company="中国国际海运集装箱（集团）股份有限公司",
        url="https://campus.51job.com/cimc/post.html",
    )


async def test_cimc_2027_all_businesses_and_units(tmp_path: Path, now: datetime) -> None:
    session = Session(tmp_path)
    result = await Cimc2027(source(), session, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == result.scopes[0].details == 11
    assert [job.unit for job in result.jobs] == ["宁波中集"] * 10 + ["中集集团总部"]
    assert len(session.details) == 11


async def test_cimc_2027_detail_type_change_is_partial(tmp_path: Path, now: datetime) -> None:
    result = await Cimc2027(source(), Session(tmp_path, bad_detail=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 10
    assert any(issue.job_key == "2" for issue in result.issues)
