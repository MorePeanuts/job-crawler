import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.faw import FawCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, failure: str = ""):
        self.page = self
        self.project = "205701"
        self.failure = failure
        self.pages: list[tuple[str, int]] = []

    async def content(self) -> str:
        return (
            "".join(
                f'<a href="/positionList?recruitType=1&projectId={p}">{p}</a>'
                for p in ["205701", "205601", "205801", "203201"]
            )
            + '<a href="/positionList?recruitType=12&projectId=100301">实习</a>'
        )

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        q = parse_qs(urlsplit(url).query)
        if "projectId" in q:
            self.project = q["projectId"][0]

    async def observed(self, needle: str) -> dict[str, Any]:
        query = f"recruitType=1&pageSize=10&currentPage=1&externalProjectStr={self.project}"
        return {
            "url": f"https://{FawCampus.host}/wecruit{needle}{FawCampus.suite}?{query}",
            "post_data": None,
            "body": json.dumps({"state": "200", "data": {}}),
        }

    def row(self, key: str) -> dict[str, Any]:
        return {
            "postId": key,
            "postName": f"工程师{key}",
            "recruitType": 1,
            "projectId": self.project,
            "workPlaceStr": "长春市",
            "projectName": "2027校园招聘",
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert payload is None
        if detail:
            assert form is not None and form["recruitType"] == "1"
            row = self.row(form["postId"])
            row.update(
                workContent="岗位职责：设计开发",
                serviceCondition="任职要求：机械专业",
                education="本科",
            )
            if self.failure == "detail_identity" and form["postId"] == "205701-0":
                row["projectId"] = "other"
            return {"state": "200", "data": row}
        assert form is None
        q = parse_qs(urlsplit(url).query)
        assert q["externalProjectStr"] == [self.project]
        page = int(q["currentPage"][0])
        self.pages.append((self.project, page))
        total = 11 if self.project == "205701" else 0 if self.project == "205601" else 1
        rows = [
            self.row(f"{self.project}-{i}") for i in range((page - 1) * 10, min(page * 10, total))
        ]
        if self.failure == "empty" and page == 2:
            rows = []
        elif self.failure == "count" and page == 2:
            total += 1
        elif self.failure == "kind" and self.project == "205701":
            rows[0]["recruitType"] = 12
        return {
            "state": "200",
            "data": {
                "pageForm": {
                    "dataCount": total,
                    "totalPage": (total + 9) // 10,
                    "currentPage": page,
                    "pageSize": 10,
                    "pageData": rows,
                }
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0047",
        company_id="COM0047",
        company="中国第一汽车集团有限公司",
        url=f"https://{FawCampus.host}/",
    )


async def test_four_projects_pagination_and_actual_empty(now: datetime) -> None:
    replay = Replay()
    result = await FawCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == 13
    assert replay.pages == [
        ("205701", 1),
        ("205701", 2),
        ("205601", 1),
        ("205801", 1),
        ("203201", 1),
    ]
    assert result.scopes[1].expected == 0 and result.scopes[1].terminal
    assert result.jobs[0].requirements == "机械专业"


@pytest.mark.parametrize("failure", ["detail_identity", "empty", "count", "kind"])
async def test_project_errors_preserve_other_projects(now: datetime, failure: str) -> None:
    result = await FawCampus(source(), Replay(failure), now).collect()
    assert result.coverage_issues()
    assert result.scopes[-1].terminal
    assert any(job.source_key == "203201-0" for job in result.jobs)
