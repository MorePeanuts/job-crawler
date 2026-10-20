"""Satellite Group's main table, total, and duplicate annex boundaries."""

import pytest

from job_crawler.adapters.satellite_hust import TITLES, demand
from job_crawler.transport import CrawlError


def notice(*, extra_row: str = "", total: str = "401") -> str:
    counts = (17, 192, 15, 15, 8, 15, 10, 11, 10, 12, 3, 48, 6, 2, 11, 8, 3, 6, 9)
    rows = "".join(
        f"<tr><td>{title}</td><td>对应专业</td><td>本硕</td><td>{count}</td></tr>"
        for title, count in zip(TITLES, counts, strict=True)
    )
    return (
        '<div class="nyrtit"><h4 class="tit">卫星集团2027届校园招聘简章</h4>'
        '<div class="time">发布时间：2026-08-28</div></div>'
        '<div class="arc-con"><div class="content">'
        "<p>卫星集团2027届校园招聘简章 卫星化学创立于1992年 招聘岗位：</p>"
        "<table><tr><td>岗位</td><td>专业</td><td>学历</td><td>人数</td></tr>"
        f"{rows}{extra_row}<tr><td>合计</td><td>{total}</td></tr></table>"
        "<table><tr><td>学历</td></tr></table>"
        "<table><tr><td>需求岗位</td></tr><tr><td>采购专员</td></tr></table>"
        "<p>网申通道：关注“卫星招聘”微信公众号-校园招聘-应届生-招聘职位-投递简历</p>"
        "</div></div>"
    )


def test_main_table_has_19_jobs_and_duplicate_annex_is_excluded() -> None:
    date, rows = demand(notice())
    assert date == "2026-08-28"
    assert len(rows) == 19
    assert [row["title"] for row in rows].count("采购专员") == 1
    assert sum(int(row["headcount"]) for row in rows) == 401


def test_added_row_or_inconsistent_total_fails_closed() -> None:
    with pytest.raises(CrawlError):
        demand(notice(extra_row="<tr><td>新岗位</td><td>专业</td><td>本科</td><td>1</td></tr>"))
    with pytest.raises(CrawlError):
        demand(notice(total="402"))
