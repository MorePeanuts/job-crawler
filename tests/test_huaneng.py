import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from job_crawler.adapters.huaneng import HuanengCampus
from job_crawler.models import Source


def position(key: int) -> dict[str, Any]:
    return {
        "id": key,
        "announcementId": 100,
        "positionName": f"工程师{key}",
        "address": "北京、天津",
        "eduType": "5",
        "endDate": "2027-01-01 18:00:00",
        "recruitCompanyId": 1,
        "postCode": "technical",
        "status": 1,
        "jobReq": "专业基础扎实",
        "majors": [{"positionId": key, "majorName": "电气工程"}],
    }


def announcement() -> dict[str, Any]:
    return {
        "id": 100,
        "title": "公司应届招聘",
        "recruitType": 1,
        "taskType": 1,
        "recruitCompanyId": 1,
        "recruitCompanyName": "华能子公司",
        "status": 1,
        "recruitYear": "2027",
        "publishTime": "2026-09-14 18:00:00",
        "createTime": "2026-09-01",
        "positions": [position(key) for key in range(1, 12)],
    }


class Replay:
    last_evidence = "fixture"

    def __init__(self, output: Path, failure: str = ""):
        self.output = output
        self.page = self
        self.failure = failure
        self.config = SimpleNamespace(delay=0, timeout=2)
        self.detail_calls = 0
        self.queries: list[tuple[int, int]] = []

    def consume_request(self) -> None:
        pass

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def content(self) -> str:
        return "中国华能集团有限公司"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "body": json.dumps(
                {
                    "code": 0,
                    "data": [
                        {
                            "classifyCode": "education",
                            "children": [{"value": "5", "label": "硕士研究生"}],
                        },
                        {
                            "classifyCode": "job_category",
                            "children": [{"value": "technical", "label": "生产技术"}],
                        },
                    ],
                }
            )
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("Only public application functions")


def source() -> Source:
    return Source(
        source_id="COM0070",
        company_id="COM0070",
        company="中国华能集团有限公司",
        url="https://zhaopin.chng.com.cn/CampusRecruit?aId=2000145",
    )


class UnitReplay(Replay):
    def __init__(self, output: Path, failure: str = "", kind: int = 0):
        super().__init__(output, failure)
        self.kind = kind
        self.count_calls = 0

    async def evaluate(self, script: str, args: dict[str, Any]) -> dict[str, Any]:
        operation = args["operation"]
        if operation in {"units", "top", "good"}:
            kind = args["params"] if operation == "units" else 2
            if kind != self.kind or operation == "top":
                return {"code": 0, "data": []}
            units = [{"companyId": 1, "name": "华能子公司", "children": []}]
            if self.failure == "duplicate_unit":
                units += deepcopy(units)
            if self.failure == "nested_unit":
                units[0]["children"] = [{"companyId": 2}]
            return {"code": 0, "data": units if kind == 2 else [{"children": units}]}
        if operation == "company":
            assert args["params"] == {
                "recruitType": 1,
                "taskType": self.kind,
                "companyId": 1,
                "contentBody": "华能子公司",
            }
            detail = announcement()
            detail["taskType"] = self.kind
            if self.failure == "business":
                return {"code": 1, "data": []}
            if self.failure == "major":
                detail["positions"][0]["majors"][0]["positionId"] = 999
            if self.failure == "education":
                detail["positions"][0]["eduType"] = "unknown"
            if self.failure == "wrong_kind":
                detail["taskType"] = 99
            if self.failure == "foreign_company":
                detail["recruitCompanyId"] = 999
            if self.failure == "duplicate_job":
                detail["positions"].append(deepcopy(detail["positions"][0]))
            if self.failure == "missing_job":
                detail["positions"].pop()
            return {"code": 0, "data": [detail]}
        assert operation == "catalog"
        kind = args["params"]["taskType"]
        self.queries.append((kind, args["params"]["pageNo"]))
        total = 11 if kind == self.kind else 0
        if kind == self.kind:
            self.count_calls += 1
        if self.failure == "changing_count" and kind == self.kind and self.count_calls == 2:
            total = 12
        return {"code": 0, "data": {"total": total, "list": []}}


@pytest.mark.parametrize("kind", [0, 1, 2])
async def test_unit_catalog_reconciles_independent_total(
    now: datetime, tmp_path: Path, kind: int
) -> None:
    replay = UnitReplay(tmp_path, kind=kind)
    result = await HuanengCampus(source(), replay, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 11
    assert replay.detail_calls == 0
    assert replay.queries == [(0, 1), (0, 1), (1, 1), (1, 1), (2, 1), (2, 1)]
    job = result.jobs[0]
    route = ["CampusRecruit", "InternRecruit", "ManagementTraineeRecruit"][kind]
    assert job.source_url.endswith(f"/{route}?aId=100")
    assert job.education == "硕士研究生" and job.location == "北京、天津"
    assert job.published == "2026-09-14 18:00:00" and job.deadline == "2027-01-01 18:00:00"
    assert "电气工程" in job.requirements and not job.duties


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate_unit",
        "nested_unit",
        "foreign_company",
        "duplicate_job",
        "missing_job",
        "changing_count",
        "major",
        "education",
        "business",
        "wrong_kind",
    ],
)
async def test_unit_catalog_rejects_incomplete_scope(
    now: datetime, tmp_path: Path, failure: str
) -> None:
    result = await HuanengCampus(source(), UnitReplay(tmp_path, failure), now).collect()
    assert result.coverage_issues()
