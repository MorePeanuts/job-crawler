"""The immediate-signing 2027 notice keeps exactly its two roles."""

import pytest

from job_crawler.adapters.bgyfw_xasyxy import demand
from job_crawler.transport import CrawlError


def notice(*, added: str = "", signing: str = "终面通过即签约，现在投递，现在可安排面试") -> str:
    return (
        '<div class="aTitle">【碧桂园服务集团2027届校园招聘】</div>'
        '<div class="aInfo">发布时间：2026年09月11日13:03 来源：西安思源学院</div>'
        '<div class="aContent"><p>一、招聘岗位：</p>'
        f"<p>1、项目管理岗（管楼盘物业）2、生活服务岗（做经营服务）{added}（以上均为非销售岗位）</p>"
        "<p>二、相关要求：2027届本科及以上学历毕业生</p>"
        "<p>三、工作地点：惠州市。</p>"
        f"<p>五、面试安排 {signing}</p></div>"
    )


def test_two_roles_keep_original_explanations() -> None:
    date, titles = demand(notice())
    assert date == "2026-09-11"
    assert titles == ["项目管理岗（管楼盘物业）", "生活服务岗（做经营服务）"]


def test_added_role_or_signing_change_fails_closed() -> None:
    with pytest.raises(CrawlError):
        demand(notice(added="3、新岗位"))
    with pytest.raises(CrawlError):
        demand(notice(signing="通过实习考核后考虑录用"))
