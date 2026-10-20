"""The second branch's seven jobs must not absorb adjacent group branches."""

import pytest

from job_crawler.adapters.crecg_hebut import roster
from job_crawler.transport import CrawlError


def notice(
    *,
    roles: str = "土建技术岗、商务预算岗、安装技术岗、安全管理岗、综合管理岗、财务管理岗、法律合规岗",
) -> str:
    return (
        '<div class="zpxq"><div class="title">中国中铁建工集团有限公司 2027届校园招聘简章</div>'
        '<div class="info"><a href="/company/index/id/3801.html">【中铁建工集团山东有限公司】</a>'
        '<span class="fb">发布时间：2026-09-18</span></div>'
        '<div class="content">专业参考招聘简章</div><div class="content">'
        "<p>中铁建工集团有限公司（简称“中铁建工”）是世界500强——中国中铁股份有限公司的全资子公司</p>"
        "<p>二、分子公司相关信息</p>"
        "<p>1.中铁建工集团第一建设有限公司（北京）</p>"
        "<p>（3）简历投递方式：邮箱</p>"
        "<p>2.中铁建工集团第二建设有限公司（青岛）</p>"
        "<p>（1）工作地点：青岛、济南等</p>"
        f"<p>（2）招聘岗位：{roles}</p>"
        "<p>（3）简历投递方式：邮箱</p>"
        "<p>3.中铁建工集团第三建设有限公司（天津）</p>"
        "<p>（1）工作地点：天津</p><p>（2）招聘岗位：财务岗</p>"
        "</div></div>"
    )


def test_only_second_branch_seven_roles() -> None:
    published, titles, locations = roster(notice())
    assert published == "2026-09-18"
    assert len(titles) == 7
    assert titles[0] == "土建技术岗"
    assert titles[-1] == "法律合规岗"
    assert "青岛" in locations
    assert "财务岗" not in titles


def test_new_job_and_changed_boundary_fail_closed() -> None:
    with pytest.raises(CrawlError):
        roster(notice(roles="土建技术岗、新增岗位"))
    with pytest.raises(CrawlError):
        roster(notice().replace("3.中铁建工集团第三建设有限公司", "3.其他企业"))
    with pytest.raises(CrawlError):
        roster(notice().replace("2027届", "2026届"))
