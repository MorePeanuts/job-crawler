"""Linkerbot public category tree preserves campus scope and job fields."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from job_crawler.adapters.linkerbot import LinkerbotCampus
from job_crawler.models import Source
from job_crawler.transport import Session as TransportSession


class Session:
    last_evidence = ""

    def __init__(self, output: Path, duplicate: bool = False) -> None:
        self.output = output
        self.duplicate = duplicate

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://linkerbot.cn/about/join"

    async def observed(self, needle: str) -> dict[str, Any]:
        rows = [
            {
                "id": "1",
                "title": "算法工程师",
                "recruitType": "campus",
                "status": "published",
                "category": "技术",
                "locations": '["北京"]',
                "responsibilities": '["研发算法"]',
                "requirements": '["硕士及以上"]',
                "createTime": "2026-08-20 15:12:21",
            },
            {
                "id": "2",
                "title": "实习工程师",
                "recruitType": "campus",
                "status": "published",
                "category": "技术",
                "locations": "[]",
                "responsibilities": '["实习研发"]',
                "requirements": "[]",
            },
            {
                "id": "1" if self.duplicate else "3",
                "title": "销售经理",
                "recruitType": "social",
                "status": "published",
            },
        ]
        return {
            "url": "https://linkerbot.cn/jeecg-boot/lingxin/jobCategory/public/tree",
            "body": json.dumps(
                {"success": True, "code": 200, "result": [{"id": "group", "positions": rows}]}
            ),
        }


def source() -> Source:
    return Source(
        source_id="COM0587",
        company_id="COM0587",
        company="灵心巧手",
        url="https://linkerbot.cn/about/join",
    )


async def test_linkerbot_campus_tree_and_missing_publication(tmp_path: Path, now: datetime) -> None:
    result = await LinkerbotCampus(
        source(), cast(TransportSession, Session(tmp_path)), now
    ).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert result.scopes[0].skipped_out_of_scope == 1
    assert len(result.jobs) == 2
    assert result.jobs[0].duties == "研发算法"
    assert result.jobs[0].requirements == "硕士及以上"
    assert result.jobs[0].location == "北京"
    assert not result.jobs[0].published
    assert result.jobs[1].work_type == "实习"


async def test_linkerbot_rejects_duplicate_identity(tmp_path: Path, now: datetime) -> None:
    result = await LinkerbotCampus(
        source(), cast(TransportSession, Session(tmp_path, duplicate=True)), now
    ).collect()
    assert result.coverage_issues()
