from datetime import datetime
from pathlib import Path
from typing import Any

from job_crawler.adapters.coapi51 import Wanxiang
from job_crawler.config import CrawlConfig
from job_crawler.models import Source


class Session:
    last_evidence = "fixture"

    def __init__(self, output: Path, *, repeat: bool = False):
        self.output = output
        self.page = self
        self.config = CrawlConfig(delay=0)
        self.repeat = repeat
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://campus.51job.com/wxxz2027/about2.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("不应观察接口")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("不应直接请求 JSON")

    async def content(self) -> str:
        cards = "".join(f'<div class="tel_top" jobid="{n}"></div>' for n in range(1, 11))
        return f"<html><script>var params = {{ctmid: '8019567'}};</script>{cards}</html>"

    def consume_request(self) -> None:
        pass

    async def evaluate(self, script: str, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            assert value["ctmid"] == "8019567"
            assert not value["functype"] and not value["jobarea"] and not value["poscode"]
            page = value["pagenum"]
            self.pages.append(page)
            ids = list(range(1, 11)) if page == 1 else [1 if self.repeat else 11]
            return {
                "resultbody": {
                    "totalnum": 11,
                    "joblist": [
                        {"jobid": str(n), "ctmid": "8019567", "jobname": f"岗位{n}"} for n in ids
                    ],
                }
            }
        return {
            "resultbody": {
                "jobid": str(value),
                "ctmid": "8019567",
                "jobname": f"岗位{value}",
                "jobinfo": "岗位职责：负责研发 任职要求：本科及以上",
                "jobareaname": "杭州",
                "degreefrom": "本科",
                "funtype": "研发",
                "status": "24",
            }
        }


def source() -> Source:
    return Source(
        source_id="COM0133",
        company_id="COM0133",
        company="万向集团公司",
        url="https://campus.51job.com/wxxz2027/about2.html",
    )


async def test_wanxiang_covers_pages_and_details(tmp_path: Path, now: datetime) -> None:
    session = Session(tmp_path)
    result = await Wanxiang(source(), session, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 11
    assert session.pages == [1, 2]
    assert result.jobs[-1].requirements == "本科及以上"


async def test_wanxiang_duplicate_second_page_is_incomplete(tmp_path: Path, now: datetime) -> None:
    result = await Wanxiang(source(), Session(tmp_path, repeat=True), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
