"""Behavioral checks for the Zhejiang University employer announcement."""

import pytest

from job_crawler.adapters.zjamp import parse_announcement
from job_crawler.transport import CrawlError


def announcement(*, total: int = 29, repeat: bool = False) -> str:
    names = ["农技业务岗", "农业技术岗", "贸易业务岗", "文秘岗", "财务会计岗"]
    if repeat:
        names[4] = names[3]
    counts = [22, 1, 4, 1, 1]
    rows = "".join(
        f"<tr><td>{name}（{count}人）</td><td>1. 本科及以上；2. 负责相关工作。</td></tr>"
        for name, count in zip(names, counts, strict=True)
    )
    return (
        f"<h1>浙农集团股份有限公司2027届校园招聘</h1><div>{total}人</div>"
        "<table><tr><td>热招岗位</td><td>岗位职责及要求</td></tr>" + rows + "</table>"
    )


def test_parses_all_five_jobs_and_keeps_headcount_separate() -> None:
    rows = parse_announcement(announcement())
    assert len(rows) == 5
    assert [row["headcount"] for row in rows] == [22, 1, 4, 1, 1]
    assert rows[0]["name"] == "农技业务岗"


@pytest.mark.parametrize(
    "html",
    [
        announcement(total=28),
        announcement(repeat=True),
        "<h1>浙农集团股份有限公司2027届校园招聘</h1><div>29人</div>",
        announcement().replace("浙农集团股份有限公司", "另一家公司"),
    ],
)
def test_rejects_incomplete_or_mismatched_announcement(html: str) -> None:
    with pytest.raises(CrawlError):
        parse_announcement(html)
