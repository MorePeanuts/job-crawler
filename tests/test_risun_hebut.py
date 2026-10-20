"""Risun Dingzhou's four demand categories and salary-table exclusion."""

import pytest

from job_crawler.adapters.risun_hebut import demand
from job_crawler.transport import CrawlError


def notice(*, extra: str = "", account: str = "河北旭阳能源有限公司") -> str:
    rows = (
        "<tr><td>化工、生工类</td><td>化工等专业</td><td>本科以及上</td><td>50</td></tr>"
        "<tr><td>机电及自动化类</td><td>机械等专业</td><td>本科以及上</td><td>30</td></tr>"
        "<tr><td>环境、材料类</td><td>材料等专业</td><td>本科以及上</td><td>10</td></tr>"
        "<tr><td>博士专家</td><td>数学等专业</td><td>博士</td><td>8</td></tr>"
    )
    return (
        '<div class="zpxq"><div class="title">旭阳集团定州园区2027年应届生</div>'
        f'<div class="info"><a href="/company/index/id/9247.html">【{account}】</a>'
        '<span class="fb">发布时间：2026-10-07</span></div>'
        '<div class="content">专业要求</div><div class="content">'
        "<p>旭阳集团定州园区2027届校园招聘简章</p>"
        "<p>拥有中国旭阳集团（01907.HK）</p>"
        "<p>旭阳集团定州园区2027届校园招聘需求表</p>"
        "<table><tr><td>职位类别</td><td>专业要求</td><td>学历要求</td>"
        f"<td>招聘人数</td></tr>{rows}{extra}</table>"
        "<p>【工作地点】河北省定州市胜利路旭阳集团定州园区</p>"
        "<table><tr><td>学历</td><td>薪酬</td></tr><tr><td>博士</td>"
        "<td>年薪面谈</td></tr></table></div></div>"
    )


def test_four_roles_exclude_salary_table_and_headcount() -> None:
    published, rows, location = demand(notice())
    assert published == "2026-10-07"
    assert [row["title"] for row in rows] == [
        "化工、生工类",
        "机电及自动化类",
        "环境、材料类",
        "博士专家",
    ]
    assert [row["headcount"] for row in rows] == ["50", "30", "10", "8"]
    assert location.startswith("河北省定州市")


def test_new_row_or_changed_account_fails_closed() -> None:
    with pytest.raises(CrawlError):
        demand(notice(extra="<tr><td>新增岗</td><td>材料</td><td>本科</td><td>1</td></tr>"))
    with pytest.raises(CrawlError):
        demand(notice(account="其他公司"))
