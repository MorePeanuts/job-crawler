"""Yankuang's UIBE list/detail identity and publication-date semantics."""

import pytest

from job_crawler.adapters.yankuang_uibe import detail, listing
from job_crawler.transport import CrawlError


def notice(*, links: str = "") -> str:
    if not links:
        links = '<a href="/front/zwxx.jspa?xqzwId=101&zpxxId=2098326250287316994">&gt; 财务管理</a>'
    return (
        '<h3 class="content_title">兖矿能源集团股份有限公司2027届校园招聘</h3>'
        '<div class="content">招聘单位：兖矿能源集团股份有限公司。'
        "兖矿能源是山东能源集团的旗舰资产。"
        "国(境)内外2027年毕业的本科及以上学历毕业生。"
        f"<h3>在招职位</h3>{links}</div>"
    )


def role(*, employer: str = "兖矿能源集团股份有限公司", title: str = "财务管理") -> str:
    return (
        f'<h3 class="content_header_title">{title}</h3>'
        f'<div class="content_header_desc">{employer} 发布于2026-09-11</div>'
        '<div class="content">招聘专业：会计学、财务管理 岗位要求：'
        "国(境)内外2027年毕业的本科及以上学历毕业生。</div>"
        '<div class="content_detail"><p><b>工作地点：</b>山东省济宁市</p></div>'
    )


def test_all_current_links_and_detail_fields() -> None:
    rows = listing(notice())
    assert rows == [
        {
            "key": "101",
            "title": "财务管理",
            "url": "https://aeo.uibe.edu.cn/front/zwxx.jspa?xqzwId=101&zpxxId=2098326250287316994",
        }
    ]
    fields = detail(role(), "财务管理")
    assert fields["published"] == "2026-09-11"
    assert fields["location"] == "山东省济宁市"
    assert "会计学" in fields["majors"]


def test_wrong_parent_or_detail_identity_fails_closed() -> None:
    wrong = '<a href="/front/zwxx.jspa?xqzwId=101&zpxxId=200">财务管理</a>'
    with pytest.raises(CrawlError):
        listing(notice(links=wrong))
    with pytest.raises(CrawlError):
        detail(role(employer="另一家企业"), "财务管理")
    with pytest.raises(CrawlError):
        detail(role(title="其他岗位"), "财务管理")
