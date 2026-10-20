"""GDUT's linked Hengtong roster and job identity checks."""

import pytest

from job_crawler.adapters.hengtong_gdut import TITLES, detail, listing
from job_crawler.transport import CrawlError


def notice(*, extra: str = "") -> str:
    rows = "".join(
        f'<tr><td>{i + 1:02d}</td><td><a href="/job/view/id/{2568108 + i}/from_type/3/from_id/191542">'
        f"{title}</a><ul><li>薪酬</li><li>广东省东莞市</li><li>全职</li><li>本科及以上</li></ul></td>"
        "<td>机械专业</td><td>投递简历</td></tr>"
        for i, title in enumerate(TITLES)
    )
    return (
        '<div class="details-mge"><div class="aContent"><p>亨通集团2027届校园招聘简章 '
        "亨通集团，是中国光纤光网企业</p><table><tr><td>招聘岗位</td></tr></table></div></div>"
        '<div class="details-table"><div class="css-table"><table>'
        "<tr><th>序号</th><th>职位信息</th><th>需求专业</th><th>操作</th></tr>"
        f"{rows}{extra}</table></div></div>"
    )


def job_page(*, title: str = "生产计划", employer: str = "亨通集团有限公司") -> str:
    return (
        f'<div class="details-title"><div class="title-message"><span class="title">{title}</span>'
        '广东省东莞市 | 全职 | 本科及以上</div><div class="share">2026-09-03发布</div></div>'
        f'<div class="siderinfo"><div class="unit-info"><div class="title"><a>{employer}</a></div></div></div>'
    )


def test_seven_linked_fulltime_jobs_and_detail_match() -> None:
    rows = listing(notice())
    assert len(rows) == 7
    assert [row["title"] for row in rows] == list(TITLES)
    assert len({row["key"] for row in rows}) == 7
    assert detail(job_page(), "生产计划") == "2026-09-03"


def test_added_job_or_detail_mismatch_fails_closed() -> None:
    with pytest.raises(CrawlError):
        listing(notice(extra="<tr><td>08</td><td>新增岗位</td></tr>"))
    with pytest.raises(CrawlError):
        detail(job_page(title="其他岗位"), "生产计划")
    with pytest.raises(CrawlError):
        detail(job_page(employer="其他集团"), "生产计划")
