"""Hualing Cable's single demand row and announcement identity."""

import pytest

from job_crawler.adapters.hunansteel_hualing import demand
from job_crawler.transport import CrawlError


def notice(*, extra: str = "", group: str = "湖南钢铁集团") -> str:
    return (
        "<span>发布时间：2026-09-09</span>"
        "<p>湖南华菱线缆股份有限公司2027届校园招聘简章</p>"
        f"<p>为世界五百强{group}子公司</p>"
        "<p>招聘对象：2027届本科、硕士、博士应届毕业生</p>"
        "<table><tr><td>需求岗位</td><td>需求人数</td><td>需求学历</td>"
        "<td>需求专业</td><td>其他要求</td></tr>"
        "<tr><td>技术/管理储备</td><td>26</td><td>本科</td>"
        f"<td>电气工程及其自动化</td><td></td></tr>{extra}</table>"
    )


def test_single_table_row_not_three_directions() -> None:
    published, row = demand(notice())
    assert published == "2026-09-09"
    assert row == {
        "title": "技术/管理储备",
        "headcount": "26",
        "education": "本科",
        "majors": "电气工程及其自动化",
    }


def test_new_row_or_changed_group_fails_closed() -> None:
    with pytest.raises(CrawlError):
        demand(notice(extra="<tr><td>另一岗位</td></tr>"))
    with pytest.raises(CrawlError):
        demand(notice(group="其他集团"))
