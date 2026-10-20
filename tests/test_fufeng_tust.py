"""Offline identity and directory checks for the TUST employer account."""

import pytest

from job_crawler.adapters.fufeng_tust import detail_job, profile_jobs
from job_crawler.transport import CrawlError


def profile(*, employer: str = "内蒙古沃丰农业发展有限公司", extra: str = "") -> str:
    return (
        f'<div class="company_index"><div class="p1">{employer}</div></div>'
        '<a class="lizw" href="/correcruit/content/id/46912.html">'
        '<div class="zw_title"><p class="p1">2027届管培生</p>'
        '<p class="p2">2026-10-17</p></div></a>'
        f"{extra}"
    )


def detail(*, employer: str = "内蒙古沃丰农业发展有限公司") -> str:
    return (
        '<div class="zhaopinxx_con1"><p class="p1">2027届管培生</p>'
        f'<a class="p2" href="/company/index/id/16813.html">{employer}</a>'
        '<p class="p3">发布时间：2026-10-17</p>'
        '<ul class="zpxx_ul"><li>工作地域：内蒙古自治区</li>'
        "<li>职位类别：农林牧渔业技术人员</li><li>学历要求：硕士</li></ul></div>"
        '<div class="zhaopinxx_con2"><div class="zhaopinxx_con2_title">专业要求：</div>'
        '<div class="zhaopinxx_con2_con">材料与化工</div></div>'
        '<div class="zhaopinxx_con2"><div class="zhaopinxx_con2_title">职位描述：</div>'
        '<div class="zhaopinxx_con2_con">内蒙古沃丰农业是阜丰集团全资子公司。'
        "岗位职责:轮岗学习。岗位要求:本科以上学历。福利待遇：五险一金。</div></div>"
    )


def test_directory_detail_identity_and_fields() -> None:
    rows = profile_jobs(profile())
    assert rows == [
        {
            "id": "46912",
            "title": "2027届管培生",
            "published": "2026-10-17",
            "url": "https://jy.tust.edu.cn/correcruit/content/id/46912.html",
        }
    ]
    data = detail_job(detail(), rows[0])
    assert data["duties"] == "轮岗学习。"
    assert data["requirements"] == "本科以上学历。"
    assert data["education"] == "硕士"


def test_directory_rejects_wrong_company_and_pagination() -> None:
    with pytest.raises(CrawlError, match="企业账号"):
        profile_jobs(profile(employer="另一家公司"))
    with pytest.raises(CrawlError, match="分页"):
        profile_jobs(profile(extra='<div class="pagination"><a>2</a></div>'))


def test_detail_rejects_wrong_employer() -> None:
    with pytest.raises(CrawlError, match="雇主错配"):
        detail_job(detail(employer="另一家公司"), profile_jobs(profile())[0])
