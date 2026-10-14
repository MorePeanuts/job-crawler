"""Replay Ningbo Bank campus pagination, legal units and detail identities."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.nbcb import DETAIL_API, DICT_API, LIST_API, NingboBank2027
from job_crawler.models import Source


def row(job_id: str, company: str, deadline: str = "2026-10-31") -> dict[str, str | None]:
    return {
        "id": job_id,
        "posName": "培训生" + job_id,
        "compHid": "20000" if company == "总行" else company + "-id",
        "compName": company,
        "recruitmentType": "1",
        "workLocation": "1",
        "education": "1",
        "endTime": deadline + " 00:00:00",
        "publishTime": None,
        "posDuty": "负责银行业务",
        "posRequiRement": "2027届本科及以上学历",
        "deptName": "培训生部门",
    }


class Replay:
    last_evidence = "notice.json"

    def __init__(self) -> None:
        self.rows = [
            row("head", "总行"),
            row("subsidiary", "宁银理财"),
            row("branch", "上海分行"),
            row("old", "北京分行", "2026-10-09"),
        ]
        self.bad_id = ""
        self.calls: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://zhaopin.nbcb.com.cn/"
        assert ready_endpoints == ("/api/positionNotice/notice",)

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/api/positionNotice/notice"
        return {"body": '{"status":"0000","data":{"posYear":"2027"}}'}

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        self.calls.append(url)
        self.last_evidence = f"response-{len(self.calls)}.json"
        if url == DICT_API:
            return {
                "status": "0000",
                "data": {
                    "CODE_COMPCITY": [{"dictId": "1", "dictName": "宁波市"}],
                    "CODE_RecEducation": [{"dictId": "1", "dictName": "本科及以上"}],
                },
            }
        if url == LIST_API:
            assert payload is not None and payload["recruitmentType"] == 1
            page = payload["page"]
            assert page in {1, 2}
            return {
                "status": "0000",
                "data": {
                    "list": self.rows[(page - 1) * 2 : page * 2],
                    "total": 4,
                    "pageNum": page,
                    "pages": 2,
                    "isLastPage": page == 2,
                },
            }
        assert url == DETAIL_API and detail and payload is not None
        item = next(r for r in self.rows if r["id"] == payload["id"]).copy()
        if item["id"] == self.bad_id:
            item["compHid"] = "wrong"
        return {"status": "0000", "data": item}


def source() -> Source:
    return Source(
        source_id="COM0185",
        company_id="COM0185",
        company="宁波银行股份有限公司",
        url="https://zhaopin.nbcb.com.cn/",
    )


async def test_nbcb_covers_pages_and_excludes_subsidiary_and_expired(now: datetime) -> None:
    replay = Replay()
    result = await NingboBank2027(source(), replay, now).collect()
    assert result.coverage_issues() == []
    assert [(s.expected, s.listed, s.unique, s.details) for s in result.scopes] == [(4, 4, 4, 2)]
    assert result.scopes[0].skipped_out_of_scope == 1
    assert result.scopes[0].skipped_expired == 1
    assert [j.source_key for j in result.jobs] == ["head", "branch"]
    assert {j.unit for j in result.jobs} == {"总行", "上海分行"}
    assert all(j.published == "" and j.location == "宁波市" for j in result.jobs)
    assert replay.calls.count(DETAIL_API) == 2


async def test_nbcb_detail_identity_failure_is_partial(now: datetime) -> None:
    replay = Replay()
    replay.bad_id = "branch"
    result = await NingboBank2027(source(), replay, now).collect()
    assert result.coverage_issues()
    assert [j.source_key for j in result.jobs] == ["head"]


async def test_nbcb_duplicate_page_is_not_complete(now: datetime) -> None:
    replay = Replay()
    replay.rows[2]["id"] = "head"
    result = await NingboBank2027(source(), replay, now).collect()
    assert result.coverage_issues()
    assert any("重复" in issue.message for issue in result.issues)
