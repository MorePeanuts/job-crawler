"""The Li Ning campus tenant has one verified 2027 project."""

import pytest

from job_crawler.adapters.hotjob import Lining2027
from job_crawler.transport import CrawlError


def test_lining_project_scope_and_detail_identity() -> None:
    adapter = Lining2027.__new__(Lining2027)
    listing = {
        "postId": "abc",
        "postName": "零售管培生",
        "company": "执行董事兼联席CEO管辖",
        "projectName": "2027校园招聘",
    }
    assert adapter.include_listing(listing)
    assert not adapter.include_listing({**listing, "projectName": "2026校园招聘"})
    with pytest.raises(CrawlError, match="缺少校招项目"):
        adapter.include_listing({**listing, "projectName": ""})
    with pytest.raises(CrawlError, match="与列表不符"):
        adapter._job(
            {**listing, "postId": "other", "workContent": "岗位职责"},
            listing,
            "evidence.json",
            {},
            "",
        )
