"""Minimal real response shapes captured by code in the earlier validation run."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from test_adapters import Replay, source

from job_crawler.adapters import REGISTRY
from job_crawler.filtering import SHANGHAI


class ObservedReplay(Replay):
    def __init__(self, platform: str):
        super().__init__(platform)
        self.sample = json.loads(Path("tests/fixtures/observed-platform-samples.json").read_text())[
            platform
        ]

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        self.calls.append((url, payload, detail))
        if self.platform == "pingan":
            return {
                "responseCode": "10001",
                "data": {"totalCount": 1, "totalPage": 1, "list": [self.sample]},
            }
        if self.platform == "ccb":
            if detail:
                return self.sample
            return {
                "SUCCESS": "true",
                "TOTAL_REC": 1,
                "TOTAL_PAGE": 1,
                "planPostList": [
                    {
                        "planPost": self.sample["planPost"],
                        "planPostName": self.sample["planPostName"],
                        "planId": "sample-plan",
                        "planType": "XY",
                        "orgId": "sample-unit",
                        "secondOrgId": "",
                    }
                ],
            }
        if self.platform == "cnpc":
            if detail:
                return self.sample
            return {"totals": 1, "recruitInfo": [{"id": self.sample["recruitInfoObj"]["id"]}]}
        return {
            "success": True,
            "content": {"totalCount": 1, "pageSize": 100, "datas": [self.sample]},
        }


@pytest.mark.parametrize("platform", ["pingan", "ccb", "cnpc", "alibaba"])
async def test_observed_payload_shapes(platform: str) -> None:
    adapter = REGISTRY[platform]
    replay = ObservedReplay(platform)
    result = await adapter(
        source(adapter.host), replay, datetime(2026, 10, 1, tzinfo=SHANGHAI)
    ).collect()
    assert not result.coverage_issues()
    assert result.jobs and all(job.title and job.source_url for job in result.jobs)
    if platform == "alibaba":
        assert result.jobs[0].published == "" and result.jobs[0].education == ""
    if platform == "ccb":
        assert result.jobs[0].deadline == "2026-10-08"
