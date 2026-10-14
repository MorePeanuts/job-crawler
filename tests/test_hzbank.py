"""Replay Hangzhou Bank's numbered public campus result set."""

from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.hzbank import HzbankCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "bank-list.json"

    def __init__(self, *, duplicate: bool = False, unknown_unit: bool = False):
        self.duplicate = duplicate
        self.unknown_unit = unknown_unit
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://myjob.hzbank.com.cn/hzzp-apply-web/static/index.html#/employ/school"

    async def observed(self, needle: str) -> dict[str, Any]:
        if "queryActiveBatchList" in needle:
            return {
                "url": "https://myjob.hzbank.com.cn/hzzp-apply/employInfo/queryActiveBatchList?positionType=01"
            }
        return {
            "url": "https://myjob.hzbank.com.cn/hzzp-apply/employInfo/queryEmployInfosList?page=0&positionName=&positionType=01&size=6&organNo=&batchNos="
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is None and not detail
        if "queryActiveBatchList" in url:
            return {
                "errorCode": "0",
                "result": [
                    {
                        "batchNo": "20260904183140415187",
                        "batchName": "2027届秋季校园招聘项目",
                        "type": "01",
                    }
                ],
            }
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        self.pages.append(page)
        rows = (
            [self.row(i) for i in range(1, 7)]
            if page == 0
            else [self.row(6 if self.duplicate else 7)]
        )
        return {
            "errorCode": "0",
            "result": {
                "totalElements": 7,
                "totalPages": 2,
                "size": 6,
                "number": page,
                "content": rows,
                "last": page == 1,
            },
        }

    def row(self, number: int) -> dict[str, Any]:
        unit = "杭银理财" if number == 6 else "总行" if number == 1 else "北京分行"
        if number == 7 and self.unknown_unit:
            unit = "未知公司"
        return {
            "id": number,
            "batchNo": "20260904183140415187",
            "positionType": "01",
            "organizationName": unit,
            "positionName": f"培训生{number}",
            "workSpace": "杭州",
            "jobDesc": "培养银行岗位人才。",
            "jobRequire": "2027届本科及以上。",
            "startTime": "20260903000000",
            "endTime": "20261025235959",
        }


def source() -> Source:
    return Source(
        source_id="COM0241",
        company_id="COM0241",
        company="杭州银行股份有限公司",
        url="https://myjob.hzbank.com.cn/hzzp-apply-web/static/index.html#/employ/school",
    )


async def test_hzbank_full_pages_and_subsidiary_boundary(now: datetime) -> None:
    replay = Replay()
    result = await HzbankCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [0, 1]
    assert len(result.jobs) == 6
    assert result.scopes[0].skipped_out_of_scope == 1
    assert result.jobs[0].deadline == "2026-10-25 23:59:59"
    assert result.jobs[0].published == ""


async def test_hzbank_duplicate_or_unknown_unit_fails_coverage(now: datetime) -> None:
    for replay in (Replay(duplicate=True), Replay(unknown_unit=True)):
        result = await HzbankCampus(source(), replay, now).collect()
        assert result.coverage_issues()
