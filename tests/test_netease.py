import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.netease import PROJECTS, NeteaseCampus
from job_crawler.filtering import select
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, failure: str = ""):
        self.failure = failure
        self.page = self
        self.current_project = 103
        self.opened = ""
        self.pages: list[tuple[int, int]] = []
        self.details: list[tuple[int, str]] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opened = url
        params = parse_qs(urlsplit(url).query)
        if "leihuo" in url:
            self.current_project = 77
        elif "projectId" in params:
            self.current_project = int(params["projectId"][0])
        elif "/job/position" in url:
            self.current_project = int(params["id"][0])
        self.last_evidence = f"open-{self.current_project}"

    async def content(self) -> str:
        if "stars" in self.opened:
            return '<a href="http://campus.163.com/app/detail/index?id=4788&projectId=103"></a>'
        return "<p>27届应届校招 10月15日网申截止</p>"

    async def observed(self, needle: str) -> dict[str, Any]:
        pid = self.current_project
        if "navigation" in needle:
            children = [
                {
                    "title": name,
                    "link": f"https://{host}/app/job/position?id={identity}"
                    if identity != 77
                    else "https://leihuo.163.com/campus/#/full?channel=iSfFmJe",
                }
                for identity, (name, host) in PROJECTS.items()
            ]
            children.append(
                {
                    "title": "星火计划2027届人力资源培训生",
                    "link": "https://campus.163.com/app/talents/stars",
                }
            )
            if self.failure == "new_project":
                children.append({"title": "其他校招", "link": "https://campus.163.com/new"})
            return {
                "url": "https://campus.163.com" + needle,
                "body": json.dumps(
                    {"code": 200, "data": [{"title": "应届生", "children": children}]}
                ),
            }
        if "banner" in needle:
            return {
                "url": "https://campus.163.com" + needle,
                "body": json.dumps(
                    {
                        "code": 200,
                        "data": {
                            "projectStatus": 0
                            if self.failure == "closed_project" and pid == 102
                            else 1,
                            "projectName": PROJECTS[pid][0],
                        },
                    }
                ),
            }
        if "Details" in needle:
            return {
                "url": "https://"
                + ("campus.game.163.com" if pid == 102 else "campus.163.com")
                + needle
                + f"?id=0&projectId={pid}"
            }
        params = (
            "project_id=77&page_number=1&page_size=10&job_name="
            if pid == 77
            else f"projectId={pid}&currentPage=1&pageSize=10"
        )
        if self.failure == "filter" and pid == 102:
            params += "&keyword=技术"
        return {"url": f"https://{PROJECTS[pid][1]}{needle}?{params}"}

    @staticmethod
    def identity(pid: int, index: int) -> str:
        return "4788" if pid == 103 and index == 0 else str(pid * 100 + index)

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is None
        params = parse_qs(urlsplit(url).query)
        pid = int(params.get("projectId", params.get("project_id", ["0"]))[0])
        if pid == 77:
            assert urlsplit(self.opened).hostname == (
                "campus.163.com" if detail else "leihuo.163.com"
            ), "Request must use the portal's allowed browser origin"
        if detail:
            identity = params["id"][0]
            self.details.append((pid, identity))
            self.last_evidence = f"detail-{pid}-{identity}"
            return {
                "code": 200,
                "data": {
                    "id": "wrong" if self.failure == "detail" and identity == "10200" else identity,
                    "projectId": pid,
                    "positionName": f"岗位{identity}",
                    "projectName": PROJECTS[pid][0],
                    "positionDescription": "开发软件",
                    "positionRequirement": "本科及以上",
                    "workPlaceName": "杭州",
                    "positionTypeName": "技术",
                    "publishTime": "2026-07-19",
                },
            }
        page = int(params.get("currentPage", params.get("page_number", ["0"]))[0])
        self.pages.append((pid, page))
        self.last_evidence = f"list-{pid}-{page}"
        start = (page - 1) * 10
        if self.failure == "duplicate" and pid == 102:
            start = 0
        rows = []
        for i in range(start, min(start + 10, 11)):
            identity = self.identity(pid, i)
            if pid == 77:
                rows.append(
                    {
                        "ehr_job_id": identity,
                        "ehr_project_id": "77",
                        "ehr_job_type": "1",
                        "type_name": "全职",
                        "target": "2027届应届毕业生",
                        "job_name": f"岗位{identity}",
                        "job_detail_url": f"https://campus.163.com/app/detail/index?id={identity}&projectId=77",
                    }
                )
            else:
                rows.append(
                    {
                        "id": identity,
                        "projectId": pid,
                        "positionName": f"岗位{identity}",
                        "updateTime": 1791959412000,
                    }
                )
        if pid == 77:
            return {
                "status": 200,
                "data": {
                    "count_number": 11,
                    "pages_count": 2,
                    "last_page": page == 2,
                    "apply_job_list": rows,
                },
            }
        return {"code": 200, "data": {"total": 11, "pages": 2, "list": rows}}


def source() -> Source:
    return Source(
        source_id="COM0190",
        company_id="COM0190",
        company="网易公司",
        url="https://campus.163.com/app/index",
    )


async def test_three_projects_four_entries_and_publication_semantics(now: datetime) -> None:
    replay = Replay()
    result = await NeteaseCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [(102, 1), (102, 2), (103, 1), (103, 2), (77, 1), (77, 2)]
    assert len(result.jobs) == len(replay.details) == 33
    assert len({job.source_key for job in result.jobs}) == 33
    assert sum(job.source_key == "103:4788" for job in result.jobs) == 1
    assert all(job.published == "2026-07-19" for job in result.jobs)
    assert all(job.duties == "开发软件" for job in result.jobs)
    leihuo = [job for job in result.jobs if job.source_key.startswith("77:")]
    assert len(leihuo) == 11
    assert all(select(job, "all", now).reason == "unparsed_deadline" for job in leihuo)
    assert all(job.deadline == "10月15日" for job in leihuo)


@pytest.mark.parametrize(
    "failure", ["new_project", "closed_project", "filter", "duplicate", "detail"]
)
async def test_scope_and_partial_failures_cannot_be_complete(now: datetime, failure: str) -> None:
    result = await NeteaseCampus(source(), Replay(failure), now).collect()
    assert result.coverage_issues()
    if failure == "detail":
        assert len(result.jobs) == 32
        assert "102:10200" not in {job.source_key for job in result.jobs}
