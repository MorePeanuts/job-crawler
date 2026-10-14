"""Replay the observed Yili campus catalog and headquarters boundary."""

from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from job_crawler.adapters.yili import YiliHeadquarters
from job_crawler.models import Source


class Replay:
    last_evidence = "yili-list.json"

    def __init__(self, *, duplicate: bool = False, bad_department: bool = False):
        self.duplicate = duplicate
        self.bad_department = bad_department
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert "recruitType=1" in url

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/wt/yili/web/json/position/list"
        return {
            "url": "https://yili.hotjob.cn/wt/yili/web/json/position/list?"
            "positionType=&comPart=&sicCorpCode=&brandCode=1&releaseTime=&"
            "trademark=1&recruitType=1&projectId=&lanType=1&workPlace=&page=1&keyWord="
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert not detail and payload is None
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        self.pages.append(page)
        rows = (
            [
                self.row("1", "总部", "2027", "2026-10-14"),
                self.row("2", "液态奶事业部", "2027", "2027-12-31"),
            ]
            if page == 1
            else [
                self.row("1" if self.duplicate else "3", "总部", "2026", "2027-12-31"),
                self.row("4", "总部", "2027", "2027-12-31"),
            ]
        )
        if self.bad_department:
            rows[0]["deptOrgName"] = "独立子公司"
        return {
            "req_state": 9200,
            "page": page,
            "pageCount": 2,
            "rowSize": 2,
            "rowCount": 4,
            "postList": rows,
        }

    @staticmethod
    def row(post_id: str, org: str, cohort: str, deadline: str) -> dict[str, Any]:
        return {
            "postId": post_id,
            "recruitType": 1,
            "postName": f"伊利{cohort}届校招-培训生（总部）",
            "orgName": org,
            "deptOrgName": "总部人力资源部" if org == "总部" else org,
            "workPlace": "呼和浩特市",
            "education": "本科及以上",
            "postType": "人力资源",
            "workContent": "负责人力资源工作",
            "serviceCondition": "2027届本科及以上学历",
            "publishDate": "2026-09-30",
            "endDate": deadline,
        }


def source() -> Source:
    return Source(
        source_id="COM0189",
        company_id="COM0189",
        company="内蒙古伊利实业集团股份有限公司",
        url="https://yili.hotjob.cn/wt/yili/web/templet1000/index/corpwebPosition1000yili!gotoPostListForAjax?brandCode=1&recruitType=1",
    )


async def test_yili_full_catalog_and_headquarters_scope() -> None:
    replay = Replay()
    result = await YiliHeadquarters(
        source(), replay, datetime(2026, 10, 14, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
    ).collect()
    assert result.coverage_issues() == []
    assert replay.pages == [1, 2]
    assert [job.source_key for job in result.jobs] == ["1", "4"]
    assert [job.deadline for job in result.jobs] == ["2026-10-14", "2027-12-31"]
    assert result.scopes[0].expected == result.scopes[0].unique == 4
    assert result.scopes[0].skipped_out_of_scope == 2
    assert all(job.evidence == ["yili-list.json"] for job in result.jobs)


async def test_yili_rejects_duplicate_page_and_unknown_headquarters_department() -> None:
    for replay in (Replay(duplicate=True), Replay(bad_department=True)):
        result = await YiliHeadquarters(
            source(), replay, datetime(2026, 10, 14, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
        ).collect()
        assert result.coverage_issues()
        assert result.scopes[0].terminal is False
