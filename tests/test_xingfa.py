"""Xingfa notice must contain all five numbered job categories."""

import pytest

from job_crawler.adapters.xingfa import parse_notice
from job_crawler.transport import CrawlError


def notice(*, omit: int = -1, duplicate: bool = False) -> str:
    names = ["专职研发类", "生产工艺类", "营销贸易类", "信息技术类", "财务会计类"]
    numbers = "一二三四五"
    parts = []
    for index, name in enumerate(names):
        if index == omit:
            continue
        number = numbers[2] if duplicate and index == 3 else numbers[index]
        parts.extend(
            [
                f"<p>（{number}）{name}</p>",
                "<p>需求专业：化学工程</p>",
                "<p>学历层次：2027届本科及以上毕业生</p>",
                "<p>工作地点：宜昌市</p>",
            ]
        )
    return (
        "<h1>湖北兴发化工集团股份有限公司</h1><div class='aContent'>"
        "<p>兴发集团2027届校园人才招聘简章</p>"
        "<h3>二、需求岗位</h3>" + "".join(parts) + "<p>三、其他重点福利待遇</p>"
        "<p>秋季校园招聘时间为2026年9月至11月</p></div>"
    )


def test_extracts_five_announcement_categories() -> None:
    rows = parse_notice(notice())
    assert len(rows) == 5
    assert rows[0]["name"] == "专职研发类"
    assert rows[4]["requirements"] == "化学工程"


@pytest.mark.parametrize(
    "html",
    [
        notice(omit=4),
        notice(duplicate=True),
        notice().replace("湖北兴发化工集团股份有限公司", "另一家公司"),
        notice().replace("需求专业：化学工程", "其他字段：化学工程", 1),
    ],
)
def test_rejects_incomplete_or_wrong_notice(html: str) -> None:
    with pytest.raises(CrawlError):
        parse_notice(html)
