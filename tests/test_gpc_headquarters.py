"""The GPC campus tenant contains independent subsidiaries beside headquarters."""

import pytest

from job_crawler.adapters.hotjob import GpcHeadquarters2027
from job_crawler.transport import CrawlError


def test_group_directory_only_attributes_headquarters() -> None:
    adapter = GpcHeadquarters2027.__new__(GpcHeadquarters2027)
    adapter.validate_terms(
        {
            "orgList": [
                {"code": "0/122736", "nameCh": "广州医药集团有限公司（总部）", "positionsNum": 9}
            ]
        }
    )
    assert adapter.include_listing(
        {"company": "广州医药集团有限公司（总部）", "orgCode": "0/122736/122742"}
    )
    assert not adapter.include_listing(
        {"company": "广州白云山花城药业有限公司", "orgCode": "0/122870/133404"}
    )
    with pytest.raises(CrawlError, match="机构代码错配"):
        adapter.include_listing(
            {"company": "广州医药集团有限公司（总部）", "orgCode": "0/122870/133404"}
        )
