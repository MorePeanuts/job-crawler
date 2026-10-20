"""China Hongqiao's campus demand table stays a four-role roster."""

import pytest

from job_crawler.adapters.hongqiao_cup import demand
from job_crawler.transport import CrawlError


def notice(*, extra: str = "", stock: str = "1378.HK") -> str:
    rows = "".join(
        f"<tr><td>{title}</td><td>本科及以上</td><td>材料专业</td></tr>"
        for title in (
            "产业研究院研发工程师",
            "青年储备干部（职能管理方向）",
            "青年储备干部（生产制造方向）",
            "数智化工程师",
        )
    )
    return (
        '<div class="aTitle">中国宏桥集团有限公司2027届校园招聘</div>'
        '<div class="aInfo"><span id="pub_date">2026年10月17日16:28</span></div>'
        '<div class="aContent"><p>中国宏桥集团有限公司是一家企业，'
        f"股票代码：{stock}。一、招聘岗位：</p>"
        f"<table><tr><td>岗位</td><td>学历</td><td>专业</td></tr>{rows}{extra}</table>"
        "</div>"
    )


def test_four_distinct_roles_from_one_table() -> None:
    date, rows = demand(notice())
    assert date == "2026-10-17"
    assert [row["title"] for row in rows] == [
        "产业研究院研发工程师",
        "青年储备干部（职能管理方向）",
        "青年储备干部（生产制造方向）",
        "数智化工程师",
    ]


def test_extra_row_or_changed_listed_identity_fails_closed() -> None:
    with pytest.raises(CrawlError):
        demand(notice(extra="<tr><td>新增岗</td><td>本科</td><td>化工</td></tr>"))
    with pytest.raises(CrawlError):
        demand(notice(stock="0000.HK"))
