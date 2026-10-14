"""Replay published campus categories and their unsupported branches."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.grcbank import GuangzhouRuralBankCampus
from job_crawler.models import Source


def card(job_id: str, title: str) -> dict[str, Any]:
    return {
        "id": job_id,
        "pkPostCategory": job_id,
        "type": 1,
        "children": [],
        "name": title,
        "title": title,
        "duty": "负责客户服务",
        "qualification": "2027届大学本科及以上应届毕业生",
    }


class Replay:
    last_evidence = "entry.json"

    def __init__(self) -> None:
        self.published = True
        self.rows = [
            card("postdoc", "博士后研究人员"),
            card("a", "英才生A计划"),
            card("b", "客服培养生"),
        ]

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://cdms.grcbank.com:8083/yp/school"

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError(f"unexpected request: {url}")

    async def observed(self, needle: str) -> dict[str, Any]:
        self.last_evidence = needle + ".json"
        if needle.endswith("getPageSchool"):
            return {
                "body": json.dumps(
                    {
                        "statusCode": "2000",
                        "status": "success",
                        "data": {
                            "state": 1 if self.published else 0,
                            "stateName": "已发布" if self.published else "草稿",
                        },
                    }
                )
            }
        return {
            "post_data": json.dumps({"params": {"type": "BD241031112855lxqk9m"}, "source": 0}),
            "body": json.dumps({"statusCode": "2000", "status": "success", "data": self.rows}),
        }


def source() -> Source:
    return Source(
        source_id="COM0390",
        company_id="COM0390",
        company="广州农村商业银行股份有限公司",
        url="https://cdms.grcbank.com:8083/yp/school",
    )


async def test_grcbank_complete_catalog(now: datetime) -> None:
    result = await GuangzhouRuralBankCampus(source(), Replay(), now).collect()
    assert result.coverage_issues() == []
    assert [(s.expected, s.details, s.skipped_out_of_scope, s.terminal) for s in result.scopes] == [
        (3, 2, 1, True)
    ]
    assert [j.source_key for j in result.jobs] == ["a", "b"]
    assert all(j.published == "" and j.deadline == "" and j.location == "" for j in result.jobs)


async def test_grcbank_duplicate_id_is_partial(now: datetime) -> None:
    replay = Replay()
    replay.rows[2] = card("a", "客服培养生")
    result = await GuangzhouRuralBankCampus(source(), replay, now).collect()
    assert result.coverage_issues()
    assert [j.source_key for j in result.jobs] == ["a"]


async def test_grcbank_unpublished_page_is_blocked(now: datetime) -> None:
    replay = Replay()
    replay.published = False
    result = await GuangzhouRuralBankCampus(source(), replay, now).collect()
    assert result.coverage_issues()
    assert result.jobs == []


async def test_grcbank_missing_duties_is_partial(now: datetime) -> None:
    replay = Replay()
    replay.rows[1]["duty"] = ""
    result = await GuangzhouRuralBankCampus(source(), replay, now).collect()
    assert result.coverage_issues()
    assert result.jobs == []
