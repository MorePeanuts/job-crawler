"""东风柳汽专题完整岗位卡与集团关系回放。"""

import pytest

from job_crawler.adapters.dongfeng_liuzhou import COUNTS, positions, verify_parent
from job_crawler.transport import CrawlError


def catalog(*, duplicate_title: bool = False, pagination: bool = False) -> str:
    cards = []
    number = 0
    for category, count in COUNTS.items():
        for _ in range(count):
            number += 1
            title = "重复标题" if duplicate_title else f"岗位{number}"
            cards.append(
                '<div class="job-card"><h3 class="job-card-title">'
                f'{title}</h3><span class="job-card-cat">{category}</span>'
                '<span class="job-card-tag">本科及以上</span>'
                '<span class="job-card-city">工作地址：<span class="cell-city">柳州</span></span>'
                '<div class="cell-collapse"><div class="cell-content">职责原文</div></div>'
                '<div class="cell-collapse"><div class="cell-content">要求原文</div></div>'
                '<a class="job-apply" href="https://www.liepin.com/lptjob/123">职位申请</a></div>'
            )
    page = '<div class="pagination">2</div>' if pagination else ""
    return (
        "<title>东风柳汽2027届校园招聘</title>"
        f'<div class="job_table job_cards">{"".join(cards)}</div>{page}'
    )


def test_all_cards_count_even_when_application_links_repeat() -> None:
    rows = positions(catalog())
    assert len(rows) == 36
    assert len({row["title"] for row in rows}) == 36
    assert rows[0]["education"] == "本科及以上"


def test_card_identity_and_pagination_fail_closed() -> None:
    with pytest.raises(CrawlError):
        positions(catalog(duplicate_title=True))
    with pytest.raises(CrawlError):
        positions(catalog(pagination=True))
    verify_parent("东风柳州汽车有限公司2027届；东风汽车集团股份有限公司持股75%")
    with pytest.raises(CrawlError):
        verify_parent("东风柳州汽车有限公司2027届")
