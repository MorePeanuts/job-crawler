import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.hotjob import Yutong
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, failure: str = ""):
        self.failure = failure
        self.recruit_type = "1"
        self.types: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.recruit_type = "12" if url.endswith("/intern") else "1"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": f"https://wecruit.hotjob.cn/wecruit{needle}{Yutong.suite}?ref=campus",
            "post_data": f"recruitType={self.recruit_type}&currentPage=1&pageSize=10&coordinateLat=&coordinateLng=",
            "body": json.dumps({"state": "200", "data": {}}),
        }

    async def request(
        self,
        url: str,
        *,
        form: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert not detail and payload is None and form is not None
        assert form["recruitType"] == self.recruit_type
        assert "isFrompb" not in form
        self.types.append(self.recruit_type)
        data: dict[str, Any] = {
            "totalPage": 0,
            "pageSize": 0,
            "pageData": [],
            "currentPage": 0,
            "dataCount": 0,
        }
        if self.recruit_type == "12":
            if self.failure == "nonempty_size_zero":
                data.update(totalPage=1, dataCount=1, currentPage=1)
            elif self.failure == "zero_inconsistent":
                data["totalPage"] = 1
        return {"state": "200", "data": {"pageForm": data, "positonNum": 0}}


def source() -> Source:
    return Source(
        source_id="COM0362",
        company_id="COM0362",
        company="宇通客车股份有限公司",
        url=f"https://{Yutong.host}{Yutong.path}",
    )


async def test_both_actual_empty_catalogs_and_doctor_route(now: datetime) -> None:
    replay = Replay()
    adapter = Yutong(source(), replay, now)
    result = await adapter.collect()
    assert not result.coverage_issues()
    assert replay.types == ["1", "12"]
    assert len(result.scopes) == 2 and not result.jobs
    assert all(scope.expected == 0 and scope.terminal for scope in result.scopes)
    assert parse_qs(urlsplit(adapter.detail_page("123")).query)["recruitType"] == ["intern"]


@pytest.mark.parametrize("failure", ["nonempty_size_zero", "zero_inconsistent"])
async def test_invalid_doctor_page_keeps_campus_success(now: datetime, failure: str) -> None:
    result = await Yutong(source(), Replay(failure), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].terminal
    assert not result.scopes[1].terminal
