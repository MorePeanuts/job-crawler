"""Replay the CTG project tree and a full page boundary."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.ctg_dutyfree import BRANCH, COMPANY, CtgDutyFreeCampus
from job_crawler.models import Source

PARENT_ID = "parent"
BRANCH_ID = "branch"


def row(job_id: str, company_id: str, company_name: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "job_name": f"岗位{job_id}",
        "company_id": company_id,
        "company_name": company_name,
        "recruitment_type_cn": "校园招聘",
        "nature_cn": "校招",
        "status": 1,
        "hide": 0,
        "start_time": "2026-09-30 09:00:00",
        "end_time": "2026-12-31 23:59:59",
        "contents": "【职位描述】负责相关项目执行\n【任职资格】应届毕业生",
        "district_list": [{"area_cn": "北京"}],
        "category_cn": "人力资源",
        "education_cn": "本科",
    }


class Replay:
    last_evidence = "tree.json"

    def __init__(self) -> None:
        self.rows = [
            row("1", PARENT_ID, COMPANY),
            row("2", BRANCH_ID, "中旅免税-" + BRANCH),
            *[row(str(i), "other", "其他独立法人") for i in range(3, 102)],
        ]
        self.parent_count = 1
        self.branch_count = 1
        self.total_change = False

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://ctgjob.iguopin.com/job-campus"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected observed call: {needle}")

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "include",
    ) -> dict[str, Any]:
        assert payload is not None
        assert credentials == "omit"
        if url.endswith("project-company"):
            self.last_evidence = "tree.json"
            return {
                "code": 200,
                "msg": "OK",
                "data": {
                    "list": {
                        "children": [
                            {
                                "name": COMPANY,
                                "company_id": PARENT_ID,
                                "job_count": self.parent_count,
                                "children": [
                                    {
                                        "name": BRANCH,
                                        "company_id": BRANCH_ID,
                                        "job_count": self.branch_count,
                                    }
                                ],
                            }
                        ]
                    }
                },
            }
        assert payload["company_id_with_sub"] == PARENT_ID
        page = payload["page"]
        assert payload["page_size"] == 100
        self.last_evidence = f"page-{page}.json"
        return {
            "code": 200,
            "msg": "OK",
            "data": {
                "page": page,
                "page_size": 100,
                "total": len(self.rows) + (1 if self.total_change and page == 2 else 0),
                "list": self.rows[(page - 1) * 100 : page * 100],
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0295",
        company_id="COM0295",
        company=COMPANY,
        url="https://ctgjob.iguopin.com/job-campus",
    )


async def test_complete_two_pages_and_exact_employers(now: datetime) -> None:
    result = await CtgDutyFreeCampus(source(), Replay(), now).collect()
    assert result.coverage_issues() == []
    assert len(result.jobs) == 2
    assert [job.unit for job in result.jobs] == [COMPANY, BRANCH]
    assert [
        (s.expected, s.unique, s.details, s.skipped_out_of_scope, s.terminal) for s in result.scopes
    ] == [(101, 101, 2, 99, True)]
    assert result.jobs[0].duties == "负责相关项目执行"
    assert result.jobs[0].requirements == "应届毕业生"
    assert result.jobs[0].published == ""


async def test_duplicate_job_id_marks_partial(now: datetime) -> None:
    replay = Replay()
    replay.rows[100]["job_id"] = "1"
    result = await CtgDutyFreeCampus(source(), replay, now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 2


async def test_changing_total_marks_partial(now: datetime) -> None:
    replay = Replay()
    replay.total_change = True
    result = await CtgDutyFreeCampus(source(), replay, now).collect()
    assert result.coverage_issues()


async def test_employer_count_mismatch_marks_partial(now: datetime) -> None:
    replay = Replay()
    replay.branch_count = 2
    result = await CtgDutyFreeCampus(source(), replay, now).collect()
    assert result.coverage_issues()


async def test_expired_and_malformed_contents(now: datetime) -> None:
    replay = Replay()
    replay.rows[0]["end_time"] = "2026-01-01 23:59:59"
    result = await CtgDutyFreeCampus(source(), replay, now).collect()
    assert result.coverage_issues() == []
    assert [job.unit for job in result.jobs] == [BRANCH]
    assert result.scopes[0].skipped_expired == 1

    replay = Replay()
    replay.rows[0]["contents"] = "unexpected"
    result = await CtgDutyFreeCampus(source(), replay, now).collect()
    assert result.coverage_issues()
    assert result.jobs == []
