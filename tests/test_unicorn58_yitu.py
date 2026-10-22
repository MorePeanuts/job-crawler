"""Replay Yitu's full-text campus listing and internship boundary."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.yitu import Yitu2027
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture:yitu-campus"

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://www.yitutech.com/cn/career?mode=campus"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == Yitu2027.endpoint
        return {
            "url": "https://api.mokahr.com/v1/jobs/yitu-inc?mode=campus&limit=1000&offset=0",
            "body": json.dumps(
                {"jobs": self.rows, "total": len(self.rows), "code": 0, "msg": "success"}
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("single complete page must use observed response")


def row(key: str, title: str, commitment: str) -> dict[str, Any]:
    return {
        "id": key,
        "orgId": "yitu-inc",
        "status": "open",
        "title": title,
        "commitment": commitment,
        "description": "<p>岗位职责：</p><p>研发产品</p><p>任职资格：</p><p>本科及以上学历</p>",
        "publishedAt": "2026-08-05T03:31:06.000Z",
        "updatedAt": "2026-10-20T03:31:06.000Z",
        "locations": [{"province": "上海市", "address": "云锦路701号"}],
    }


async def test_yitu_counts_internships_but_only_keeps_regular_campus(now: datetime) -> None:
    source = Source(
        source_id="COM0608",
        company_id="COM0608",
        company="依图科技",
        url="https://www.yitutech.com/cn/career?mode=campus",
    )
    replay = Replay(
        [
            row("a", "【2027届校招】AI研发工程师", "全职"),
            row("b", "AI研发工程师（实习）", "实习"),
            row("c", "产品实习生", "全职"),
        ]
    )
    result = await Yitu2027(source, replay, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == 3
    assert result.scopes[0].skipped_out_of_scope == 2
    assert [job.source_key for job in result.jobs] == ["a"]
    assert result.jobs[0].published == "2026-08-05T03:31:06.000Z"
    assert result.jobs[0].duties == "研发产品"
    assert result.jobs[0].requirements == "本科及以上学历"
