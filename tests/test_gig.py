import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.gig import API, LABELS, GigCampus, announcement
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session

ARTICLE = {
    "detail": {
        "title": "广西投资集团2027届秋季校园招聘启事",
        "content": "二、招聘对象<p><span>202</span><span>7</span>届高校毕业生。</p>"
        "专项面向<span>2027</span>届硕士、博士毕业生。"
        "<p>报名截止时间：<span>202</span><span>6</span>年10月24日18:00。</p>"
        "广西投资集团有限公司<p><span>202</span><span>6</span>年9月14日</p>",
        "siteFileList": [],
        "createTime": "2026-09-10 14:24:34",
    }
}


def record(key: str, dept: str) -> dict[str, object]:
    return {
        "id": key,
        "jobName": "管理储备岗",
        "jobNumber": f"2026-{key}",
        "deptId": dept,
        "jobGroupName": "校园招聘",
        "status": 1,
        "eduRecord": "硕士研究生及以上",
        "professionReq": "经济学等相关专业",
        "customkey076177cd58ab": f"企业{dept}",
        "customkey3d9b2e7c1e25": "管理储备类",
        "customkey70ce360cce67": "广西南宁/贺州",
    }


class Replay:
    last_evidence = "fixture"

    def __init__(self, output: Path):
        self.output = output
        self.page = self
        self.clicks: list[str] = []
        self.label = ""
        self.budget = 0
        self.rows = [record("one", "a"), record("two", "b")]
        self.tree = [
            {
                "id": "root",
                "parentId": "",
                "name": "校园招聘",
                "jobNum": 0,
                "childJobNum": 2,
                "childs": [
                    {"id": "a", "parentId": "root", "name": "专项", "jobNum": 1},
                    {"id": "b", "parentId": "root", "name": "单位", "jobNum": 1},
                ],
            }
        ]
        self.payload: dict[str, object] = {"jobName": "", "deptIds": [], "jobGroups": ["campus"]}
        self.data: dict[str, object] = {
            "site": {"siteName": "广西投资集团有限公司"},
            "cms-menu/listArticleByMenuId": deepcopy(ARTICLE),
            "job-info/job-column-type-list-reformc": [
                {"name": "校园招聘", "value": "campus", "jobDataNum": 2}
            ],
            "job-info/job-title-list": [
                {"jobColumnKey": k, "jobColumnName": v, "showIs": 1} for k, v in LABELS.items()
            ],
        }

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://gtjt.zhaopin.com/"

    def consume_request(self) -> None:
        self.budget += 1

    def get_by_text(self, label: str, *, exact: bool) -> "Replay":
        assert exact
        self.label = label
        return self

    @property
    def first(self) -> "Replay":
        return self

    async def click(self, **kwargs: object) -> None:
        self.clicks.append(self.label)

    async def observed_path(self, path: str) -> dict[str, object]:
        endpoint = path.removeprefix(API)
        if endpoint == "job-info/portal-list-reformc":
            assert self.clicks == ["招聘岗位", "校园招聘"]
            value = self.rows
        elif endpoint == "site/dept/tree/list":
            value = self.tree
        else:
            value = self.data[endpoint]
        self.last_evidence = f"fixture:{endpoint}"
        return {
            "url": f"https://zkapi.zhaopin.com{path}",
            "body": json.dumps({"code": 200, "success": True, "data": value}),
            "post_data": json.dumps(self.payload),
        }


def adapter(session: Replay, now: datetime) -> GigCampus:
    return GigCampus(
        Source(
            source_id="COM0122",
            company_id="COM0122",
            company="广西投资集团有限公司",
            url="https://gtjt.zhaopin.com/",
        ),
        cast(Session, session),
        now,
    )


async def test_full_catalog_closes_tree_without_login_or_detail_requests(
    tmp_path: Path, now: datetime
) -> None:
    session = Replay(tmp_path)
    result = await adapter(session, now).collect()
    assert result.coverage_issues() == [] and len(result.jobs) == 2
    assert session.budget == 2
    assert [s.unique for s in result.scopes] == [3, 0, 1, 1]
    assert {j.source_key for j in result.jobs} == {"one", "two"}
    assert len({j.title for j in result.jobs}) == 1
    job = result.jobs[0]
    assert job.published == "2026-09-14" and job.deadline == "2026-10-24 18:00:00"
    assert job.duties == "" and job.location == "广西南宁/贺州"
    assert job.unit == "企业a" and job.company == "广西投资集团有限公司"
    assert "2027届高校毕业生" in job.requirements and "经济学" in job.requirements
    assert len(job.evidence) == 5


@pytest.mark.parametrize(
    "change", ["duplicate", "number", "unit", "count", "tree", "filter", "labels"]
)
async def test_incomplete_or_mismatched_public_catalog_fails(
    tmp_path: Path, now: datetime, change: str
) -> None:
    session = Replay(tmp_path)
    if change == "duplicate":
        session.rows[1]["id"] = "one"
    elif change == "number":
        session.rows[1]["jobNumber"] = "2026-one"
    elif change == "unit":
        session.rows[1]["deptId"] = "unknown"
    elif change == "count":
        session.rows.pop()
    elif change == "tree":
        session.tree[0]["childJobNum"] = 3
    elif change == "filter":
        session.payload["deptIds"] = ["a"]
    else:
        session.data["job-info/job-title-list"] = []
    result = await adapter(session, now).collect()
    assert result.coverage_issues() and result.jobs == []


async def test_unknown_status_preserves_other_unit(tmp_path: Path, now: datetime) -> None:
    session = Replay(tmp_path)
    session.rows[1]["status"] = 0
    result = await adapter(session, now).collect()
    assert result.coverage_issues() and [j.source_key for j in result.jobs] == ["one"]


def test_missing_deadline_or_changed_audience_not_replaced_with_creation_date() -> None:
    data = deepcopy(ARTICLE)
    data["detail"]["content"] = "二、招聘对象：社会人才"
    with pytest.raises(CrawlError):
        announcement(data)


async def test_incremental_reuse_counts_and_keeps_announcement_in_fingerprint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, now: datetime
) -> None:
    captured: list[object] = []

    def before(
        self: Adapter,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job]:
        assert listing_job is not None and evidence == "fixture:job-info/portal-list-reformc"
        captured.append(listing)
        scope.reused_details += 1
        return [listing_job]

    monkeypatch.setattr(Adapter, "before_detail", before)
    result = await adapter(Replay(tmp_path), now).collect()
    assert result.coverage_issues() == []
    assert sum(s.reused_details for s in result.scopes) == 2
    assert all(isinstance(v, dict) and v["announcement"] == ARTICLE for v in captured)
