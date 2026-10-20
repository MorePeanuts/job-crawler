"""恒力重工三个高校岗位 ID 与详情身份回放。"""

import pytest

from job_crawler.adapters.hengli_shipbuilding import roster, verify_detail
from job_crawler.transport import CrawlError


def listing(*, duplicate: bool = False) -> str:
    rows = []
    for index, title in enumerate(("研发设计储干", "生产/质量储干", "行政类储干"), start=1):
        key = 1 if duplicate else index
        rows.append(
            f'<tr><td>{index:02d}</td><td><a class="text-primary" href="/job/view/id/{key}/from_type/4/from_id/861683">{title}</a>'
            "<ul><li>10500</li><li>辽宁省 - 大连市</li><li>全职</li></ul></td>"
            f'<td>机械、电气等相关专业</td><td><a class="apply_job" data-id="{key}">投递简历</a></td></tr>'
        )
    return (
        "恒力重工集团2027届校园招聘 恒力重工集团有限公司 "
        "恒力重工产业园2027届校园招聘简章 发布时间：2026-09-27 10:47"
        "<table><tr><th>序号</th></tr>" + "".join(rows) + "</table>"
    )


def detail(title: str, *, wrong_company: bool = False) -> str:
    company = "其他公司" if wrong_company else "恒力重工集团有限公司"
    return (
        f'<span class="title" title="{title}">{title}</span>'
        "2026-09-27发布 恒力重工产业园 2027届校园招聘简章"
        f'<a href="/company/view/id/956041">{company}</a>'
    )


def test_hengli_three_jobs_and_detail_identity() -> None:
    published, rows = roster(listing())
    assert published == "2026-09-27"
    assert [row["id"] for row in rows] == ["1", "2", "3"]
    for row in rows:
        verify_detail(detail(row["title"]), row, published)


def test_hengli_duplicate_or_other_employer_fails_closed() -> None:
    with pytest.raises(CrawlError):
        roster(listing(duplicate=True))
    published, rows = roster(listing())
    with pytest.raises(CrawlError):
        verify_detail(detail(rows[0]["title"], wrong_company=True), rows[0], published)
