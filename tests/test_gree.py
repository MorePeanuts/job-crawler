"""Offline replay of Gree's observed campus directory and detail contract."""

from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.gree import GreeCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "evidence.json"

    def __init__(self, *, duplicate: bool = False, wrong_detail: bool = False):
        self.duplicate = duplicate
        self.wrong_detail = wrong_detail
        self.pages: list[int] = []
        self.details: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://zhaopin.greeyun.com/home"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/api/apply/jobs?"
        return {
            "url": "https://zhaopin.greeyun.com/api/apply/jobs?category=&pageNum=1&pageSize=8&property=1"
        }

    @staticmethod
    def row(number: int) -> dict[str, Any]:
        return {
            "ID": number,
            "Code": f"G{number}",
            "Position": f"研发岗位{number}",
            "Category": "技术研发类",
            "Location": "珠海市",
            "Education": "本科",
            "Experience": "应届毕业生",
            "Description": f"岗位{number}职责",
            "Qualifications": f"岗位{number}资格",
            "PubTime": "2026-08-26",
            "Status": 1,
            "property": 1,
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is None
        if detail:
            key = url.rsplit("=", 1)[1]
            self.details.append(key)
            row = self.row(int(key[1:]))
            if self.wrong_detail and key == "G9":
                row["Code"] = "G99"
            return {"code": 200, "data": row}
        page = int(url.split("pageNum=", 1)[1].split("&", 1)[0])
        self.pages.append(page)
        rows = [self.row(n) for n in range(1, 9)] if page == 1 else [self.row(9)]
        if self.duplicate and page == 2:
            rows[0]["Code"] = "G8"
        return {"code": 200, "data": {"total": 9, "list": rows}}


@pytest.mark.parametrize("duplicate,wrong_detail", [(False, False), (True, False), (False, True)])
async def test_gree_directory_and_detail(
    duplicate: bool, wrong_detail: bool, now: datetime
) -> None:
    replay = Replay(duplicate=duplicate, wrong_detail=wrong_detail)
    source = Source(
        source_id="COM0152",
        company_id="COM0152",
        company="珠海格力电器股份有限公司",
        url="https://zhaopin.greeyun.com/home",
    )
    result = await GreeCampus(source, replay, now).collect()
    assert replay.pages == [1, 2]
    if duplicate:
        assert result.coverage_issues()
    elif wrong_detail:
        assert result.coverage_issues()
        assert len(result.jobs) == 8
    else:
        assert result.coverage_issues() == []
        assert result.scopes[0].expected == result.scopes[0].unique == 9
        assert result.scopes[0].details == 9
        assert len(result.jobs) == 9
        assert result.jobs[0].duties == "岗位1职责"
        assert result.jobs[0].published == "2026-08-26"
