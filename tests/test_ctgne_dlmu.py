"""三峡能源高校公告列表与职位详情身份回放。"""

import pytest

from job_crawler.adapters.ctgne_dlmu import roster, verify_detail
from job_crawler.transport import CrawlError


def notice(
    *, second: bool = False, employer: str = "中国三峡新能源（集团）股份有限公司辽宁分公司"
) -> str:
    extra = (
        '<tr><td>02</td><td><a href="/job/view/id/2/from_type/4/from_id/869349">工程师</a>'
        "<li>8000</li><li>辽宁省沈阳市沈河区</li><li>全职</li><li>硕士</li></td>"
        '<td>电气</td><td><a class="apply_job" data-id="2">投递</a></td></tr>'
        if second
        else ""
    )
    return (
        "<h5>中国三峡新能源（集团）股份有限公司2027年秋季校园招聘公告</h5>"
        f'<a href="/company/view/id/940413">{employer}</a>'
        "<table><tr><th>序号</th><th>职位信息</th><th>需求专业</th><th>操作</th></tr>"
        '<tr><td>01</td><td><a href="/job/view/id/1/from_type/4/from_id/869349">业务经理</a>'
        "<li>6000</li><li>辽宁省沈阳市沈河区</li><li>全职</li><li>本科</li></td>"
        '<td>人工智能</td><td><a class="apply_job" data-id="1">投递</a></td></tr>'
        f"{extra}</table>"
    )


def detail(*, employer: str = "中国三峡新能源（集团）股份有限公司辽宁分公司") -> str:
    return (
        '<span class="title" title="业务经理">业务经理</span>'
        "<div>辽宁省沈阳市沈河区 全职 本科</div>"
        f'<a href="/company/view/id/940413">{employer}</a>'
    )


def test_notice_exhausts_jobs_and_matches_detail_identity() -> None:
    rows = roster(notice(second=True))
    assert [row["id"] for row in rows] == ["1", "2"]
    assert rows[0]["location"] == "辽宁省沈阳市沈河区"
    verify_detail(detail(), rows[0])
    with pytest.raises(CrawlError):
        verify_detail(detail(employer="其他公司"), rows[0])


def test_notice_rejects_wrong_company_and_job_id() -> None:
    with pytest.raises(CrawlError):
        roster(notice(employer="其他公司"))
    with pytest.raises(CrawlError):
        roster(notice().replace('data-id="1"', 'data-id="9"'))
