import pytest

from job_crawler.adapters.tcl import DETAIL_SUITE, parse_list_page
from job_crawler.transport import CrawlError


def page(title: str = "视觉开发工程师", recruit_type: str = "1", post_id: str = "abc123") -> dict:
    return {
        "title": "success",
        "total_counts": 1,
        "content": f"""
            <div class="itembox">
              <div class="item proInfoConList">
                <div class="head" data-postid="{post_id}" data-recruittype="{recruit_type}">
                  <div class="name">{title}</div>
                  <div class="tag"><span>大显示供应链管理平台</span><span>惠州市</span>
                    <span>智能制造类</span><span>若干</span><span>2026-10-12</span></div>
                </div>
                <div class="details"><a class="tool-btn" href="https://wecruit.hotjob.cn/{DETAIL_SUITE}/pb/posDetail.html?postId={post_id}&amp;postType=campus">立即申请</a></div>
              </div>
            </div>
        """,
    }


def test_tcl_page_parser_keeps_campus_identity_and_unit() -> None:
    total, jobs = parse_list_page(page())

    assert total == 1
    assert jobs == [
        {
            "id": "abc123",
            "title": "视觉开发工程师",
            "unit": "大显示供应链管理平台",
            "location": "惠州市",
            "category": "智能制造类",
            "headcount": "若干",
            "apply_url": f"https://wecruit.hotjob.cn/{DETAIL_SUITE}/pb/posDetail.html?postId=abc123&postType=campus",
        }
    ]


def test_tcl_page_parser_rejects_non_campus_and_mismatched_detail() -> None:
    with pytest.raises(CrawlError):
        parse_list_page(page(recruit_type="2"))

    with pytest.raises(CrawlError):
        parse_list_page(
            page().copy() | {"content": page()["content"].replace("postId=abc123", "postId=wrong")}
        )
