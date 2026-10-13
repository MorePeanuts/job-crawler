import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.zhiye import Gotion
from job_crawler.models import Source


class Session:
    last_evidence = "fixture"

    def __init__(self, keyword: str = ""):
        self.keyword = keyword
        self.payloads: list[dict[str, Any]] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://gotion.zhiye.com/jobs"

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": "https://gotion.zhiye.com/api/Jobad/GetJobAdPageList",
            "post_data": json.dumps(
                {
                    "PageIndex": 0,
                    "PageSize": 20,
                    "KeyWords": self.keyword,
                    "SpecialType": 0,
                    "PortalId": "",
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None
        self.payloads.append(payload)
        return {"Code": 200, "Count": 0, "Data": []}


def source() -> Source:
    return Source(
        source_id="COM0342",
        company_id="COM0342",
        company="国轩高科股份有限公司",
        url="https://gotion.zhiye.com/jobs",
    )


async def test_gotion_filters_public_mixed_catalog_to_campus(now: datetime) -> None:
    session = Session()
    result = await Gotion(source(), session, now).collect()
    assert not result.coverage_issues()
    assert session.payloads[0]["Category"] == ["2"]
    assert session.payloads[0]["PageIndex"] == 0


async def test_gotion_rejects_pre_filtered_catalog(now: datetime) -> None:
    session = Session(keyword="机械")
    result = await Gotion(source(), session, now).collect()
    assert result.coverage_issues()
    assert session.payloads == []
