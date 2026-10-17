import json
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.hailiang import Education, HailiangCampus, Stock
from job_crawler.filtering import select
from job_crawler.models import Scope, Source
from job_crawler.transport import Session


def record(key: str, title: str = "教师", kind: str = "201") -> dict[str, object]:
    return {
        "id": key,
        "title": title,
        "description": "承担教学及课程建设。",
        "requirement": "热爱教育，具备学科知识。",
        "recruit_type": {
            "id": kind,
            "name": "实习" if kind == "202" else "正式",
            "parent": {"id": "2", "name": "校招"},
        },
        "job_post_info": {"required_degree": 7, "address_list": [{"name": "学校公开地址"}]},
        "city_list": [{"name": "绍兴"}, {"name": "宁波"}],
        "publish_time": 1752043035165,
    }


class Replay:
    last_evidence = "fixture"

    def __init__(self, output: Path, *, fail_stock: bool = False, duplicate: bool = False):
        self.output = output
        self.page = self
        self.pending: list[object] = []
        self.responses: list[dict[str, object]] = []
        self.current = "583086"
        self.offset = 0
        self.clicks = 0
        self.budget = 0
        self.fail_stock = fail_stock
        self.rows = {
            "583086": [
                record("edu0", "未来校长班（28&29届实习生）"),
                record("edu1", "校园大使", "202"),
                *[record(f"edu{i}") for i in range(2, 11)],
            ],
            "campus": [record("edu2" if duplicate else "stock0", "航海家管培生")],
        }

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.current = url.split("/")[3]
        self.offset = 0
        self.responses = []

    async def content(self) -> str:
        if self.current == "campus":
            return "未知企业" if self.fail_stock else Stock.identity
        return Education.identity

    def response(self) -> dict[str, object]:
        rows = self.rows[self.current]
        return {
            "url": "https://hailiang.jobs.feishu.cn/api/v1/search/job/posts?"
            f"limit=10&offset={self.offset}&portal_type=6&_signature=fixture",
            "status": 200,
            "body": json.dumps(
                {
                    "code": 0,
                    "data": {
                        "count": len(rows),
                        "job_post_list": rows[self.offset : self.offset + 10],
                    },
                }
            ),
        }

    async def observed(self, needle: str) -> dict[str, object]:
        return self.response()

    def consume_request(self) -> None:
        self.budget += 1

    def locator(self, selector: str) -> "Replay":
        assert selector == 'li[title="下一页"]'
        return self

    async def click(self, **kwargs: object) -> None:
        self.offset += 10
        self.clicks += 1
        self.responses.append(self.response())


def adapter(session: Replay, now: datetime) -> HailiangCampus:
    return HailiangCampus(
        Source(
            source_id="COM0105",
            company_id="COM0105",
            company="海亮集团有限公司",
            url="https://hailiang.jobs.feishu.cn/583086",
        ),
        cast(Session, session),
        now,
    )


async def test_both_portals_page_to_end_and_exclude_mislabeled_internship(
    tmp_path: Path, now: datetime
) -> None:
    session = Replay(tmp_path)
    result = await adapter(session, now).collect()
    assert result.coverage_issues() == [] and len(result.jobs) == 12
    assert session.clicks == session.budget == 1
    assert [s.expected for s in result.scopes] == [11, 1]
    assert [s.unique for s in result.scopes] == [11, 1]
    assert sum(select(j, "all", now).reason == "outside_campus_scope" for j in result.jobs) == 2
    assert {j.unit for j in result.jobs} == {Education.unit, Stock.unit}
    assert result.jobs[0].education == "硕士及以上"
    assert result.jobs[0].address == "学校公开地址"
    assert result.jobs[0].location == "绍兴、宁波"
    assert result.jobs[-1].source_url.endswith("/campus/position/stock0/detail")
    assert result.jobs[0].source_url.endswith("/583086/position/edu0/detail")
    assert all(j.company == "海亮集团有限公司" for j in result.jobs)


async def test_second_portal_identity_failure_preserves_first(
    tmp_path: Path, now: datetime
) -> None:
    result = await adapter(Replay(tmp_path, fail_stock=True), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 11
    assert all(j.unit == Education.unit for j in result.jobs)


async def test_cross_portal_duplicate_requires_review(tmp_path: Path, now: datetime) -> None:
    result = await adapter(Replay(tmp_path, duplicate=True), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 11
    assert len({j.source_key for j in result.jobs}) == len(result.jobs)


@pytest.mark.parametrize("change", ["parent", "kind", "degree"])
async def test_unknown_type_or_degree_preserves_other_portal(
    tmp_path: Path, now: datetime, change: str
) -> None:
    session = Replay(tmp_path)
    row = session.rows["583086"][0]
    if change == "degree":
        row["job_post_info"] = {"required_degree": 99}
    else:
        row["recruit_type"] = {
            "id": "999" if change == "kind" else "201",
            "name": "正式",
            "parent": {"id": "1" if change == "parent" else "2", "name": "校招"},
        }
    result = await adapter(session, now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 1 and result.jobs[0].unit == Stock.unit


def test_incremental_fingerprint_preserves_portal_and_unit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, now: datetime
) -> None:
    captured: list[tuple[str, object]] = []

    def remember(self: Adapter, entity: str, listing: object, jobs: object) -> None:
        captured.append((entity, listing))

    monkeypatch.setattr(Adapter, "remember", remember)
    source = adapter(Replay(tmp_path), now).source
    for portal in (Education, Stock):
        instance = portal(source, cast(Session, Replay(tmp_path)), now)
        job = instance.job(
            "same-id", title="管培生", source_url=f"https://{portal.host}{portal.path}"
        )
        row = record("same-id")
        instance.before_detail("job:same-id", row, Scope(name="campus"), job)
        assert job.unit == portal.unit and job.education == "硕士及以上"
        instance.remember("job:same-id", row, [job])
    assert captured[0][0] == captured[1][0] == "job:same-id"
    assert captured[0][1] != captured[1][1]
