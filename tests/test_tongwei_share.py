"""通威股份 2027 届公告两组岗位与专业关联。"""

import pytest

from job_crawler.adapters.tongwei_share import roster
from job_crawler.transport import CrawlError


def page(*, missing_group: bool = False, duplicate: bool = False) -> str:
    first = "销售岗/供应链岗/技术支持岗/产品管理岗"
    if duplicate:
        first = "销售岗/销售岗/技术支持岗/产品管理岗"
    second = (
        ""
        if missing_group
        else "<p>热招岗位：电池研发岗、组件研发岗、组件材料研发岗、可靠性研究岗</p>"
        "<p>匹配专业：物理学类、材料学类</p>"
    )
    return (
        "通威股份 2027届校园招聘 通威股份有限公司由通威集团控股 "
        "光伏商务部 光伏技术部 发布时间：2026-09-16"
        '<div class="zpnr">'
        f"<p>热招岗位：{first}</p><p>优选专业：机械类、英语类</p>" + second + "</div>"
    )


def test_tongwei_eight_roles_keep_department_requirements() -> None:
    published, rows = roster(page())
    assert published == "2026-09-16"
    assert len(rows) == 8
    assert rows[0]["id"] == "1:销售岗"
    assert rows[0]["majors"] == "机械类、英语类"
    assert rows[4]["id"] == "2:电池研发岗"
    assert rows[4]["majors"] == "物理学类、材料学类"


@pytest.mark.parametrize("kwargs", [{"missing_group": True}, {"duplicate": True}])
def test_tongwei_missing_or_duplicate_group_fails_closed(kwargs: dict[str, bool]) -> None:
    with pytest.raises(CrawlError):
        roster(page(**kwargs))
