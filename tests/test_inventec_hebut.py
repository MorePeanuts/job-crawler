"""Inventec Tianjin HEBUT notice split and drift checks."""

import pytest

from job_crawler.adapters.inventec_hebut import roles
from job_crawler.transport import CrawlError


def notice(*, employer: str = "英业达集团（天津）电子技术有限公司", total: int = 15) -> str:
    return (
        '<div class="zpxq"><div class="title">2027秋季招聘职位</div><div class="info">'
        '<a href="/company/index/id/2310.html">'
        f'【{employer}】</a><span class="fb">发布时间：2026-09-21</span>'
        f"<p>工作地域：天津市 职位类别：工程技术人员 学历要求：本科 招聘人数：{total}人</p>"
        '</div><div class="content">计算机、电子信息</div><div class="content">'
        "<p>一、软件开发工程师（10人）</p><p>职位描述：</p><p>参与需求分析</p>"
        "<p>职位要求：</p><p>本科及以上学历</p>"
        "<p>二、软件测试工程师—电子电路（5人）</p><p>职位描述：</p>"
        "<p>负责功能测试</p><p>职位要求：</p><p>熟悉测试框架</p></div></div>"
    )


def test_two_roles_and_headcount() -> None:
    published, rows = roles(notice())
    assert published == "2026-09-21"
    assert [(row["title"], row["headcount"]) for row in rows] == [
        ("软件开发工程师", "10"),
        ("软件测试工程师—电子电路", "5"),
    ]
    assert rows[0]["duties"] == "参与需求分析"
    assert rows[1]["requirements"] == "熟悉测试框架"


@pytest.mark.parametrize(
    "html",
    [
        notice(employer="其他公司"),
        notice(total=16),
        notice().replace("2027秋季", "2026秋季"),
        notice().replace("二、软件测试", "三、软件测试"),
        notice().replace("<p>负责功能测试</p>", ""),
    ],
)
def test_notice_drift_rejected(html: str) -> None:
    with pytest.raises(CrawlError):
        roles(html)
