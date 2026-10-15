"""Current WuXi AppTec portal must close its 2027 campus catalog."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhiye import WuxiApptec
from job_crawler.models import Source


class SmallCatalog(WuxiApptec):
    page_size = 2


class Replay:
    last_evidence = "wuxi-list.json"

    def __init__(self, *, missing_body: bool = False):
        self.missing_body = missing_body
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://wuxiapptec.zhiye.com/campus/jobs"

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/api/Jobad/GetJobAdPageList"
        return {
            "url": "https://wuxiapptec.zhiye.com/api/Jobad/GetJobAdPageList",
            "post_data": json.dumps(
                {
                    "PageIndex": 0,
                    "PageSize": 2,
                    "Category": ["2"],
                    "KeyWords": "",
                    "SpecialType": 0,
                    "PortalId": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and not detail
        assert url.endswith("/api/Jobad/GetJobAdPageList")
        page = int(payload["PageIndex"])
        self.pages.append(page)
        rows = []
        for index in range(page * 2, min((page + 1) * 2, 5)):
            title = "2026届旧岗" if index == 2 else f"2027届研发岗{index}"
            rows.append(
                {
                    "Id": str(index),
                    "JobAdName": title,
                    "Org": None,
                    "CategoryId": "2",
                    "Kind": None,
                    **({} if self.missing_body and index == 4 else {"Duty": "药物研发"}),
                    "Require": "2027届本科及以上",
                    "PostDate": "2026-10-13T00:00:00",
                    "EndTime": "0001-01-01T00:00:00",
                    "LocNames": ["常州"],
                }
            )
        return {"Code": 200, "Count": 5, "Data": rows}


def source() -> Source:
    return Source(
        source_id="COM0337",
        company_id="COM0337",
        company="无锡药明康德新药开发股份有限公司",
        url="https://wuxiapptec.zhiye.com/campus/jobs",
    )


async def test_wuxi_current_2027_catalog(now: datetime) -> None:
    replay = Replay()
    result = await SmallCatalog(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [0, 1, 2]
    assert result.scopes[0].expected == 5
    assert result.scopes[0].skipped_out_of_scope == 1
    assert result.scopes[0].details == 4
    assert all(job.unit == "" for job in result.jobs)
    assert all(job.deadline == "" for job in result.jobs)


async def test_wuxi_missing_body_marks_partial(now: datetime) -> None:
    result = await SmallCatalog(source(), Replay(missing_body=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].details == 3
