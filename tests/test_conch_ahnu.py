"""Conch New Materials' announced roles, without splitting headcount."""

import pytest

from job_crawler.adapters.conch_ahnu import demand
from job_crawler.transport import CrawlError


def notice(*, extra: str = "", employer: str = "海螺（安徽）节能环保新材料股份有限公司") -> str:
    return (
        '<div class="news_detail"><div class="news_detail_title">'
        "安徽海螺集团有限责任公司2027届校园招聘简章</div>"
        "<div>日期：<span>2026-10-14 09:48:37</span></div>"
        '<div class="news_detail_cont"><div class="v_news_content">'
        f"<p>集团控股经营海螺水泥、海螺新材；{employer}招聘</p>"
        "<p>（一）招聘岗位</p><table>"
        "<tr><td>招聘岗位</td><td>专业类别</td><td>招聘人数</td></tr>"
        "<tr><td>财务类</td><td>财务管理、会计学等专业</td><td>若干</td></tr>"
        "<tr><td>语言类</td><td>英语等专业</td><td>若干</td></tr>"
        f"{extra}</table></div></div></div>"
    )


def test_two_rows_not_split_by_major_or_headcount() -> None:
    published, rows = demand(notice())
    assert published == "2026-10-14"
    assert [(row["title"], row["headcount"]) for row in rows] == [
        ("财务类", "若干"),
        ("语言类", "若干"),
    ]


def test_new_row_or_changed_employer_fails_closed() -> None:
    with pytest.raises(CrawlError):
        demand(notice(extra="<tr><td>新岗位</td><td>不限</td><td>1</td></tr>"))
    with pytest.raises(CrawlError):
        demand(notice(employer="另一家公司"))
