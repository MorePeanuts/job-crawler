"""United Aircraft's static campus catalog has stable ID and scope boundaries."""

import pytest

from job_crawler.adapters.uatair import UatairCampus
from job_crawler.transport import CrawlError


def catalog(*, duplicate: bool = False, wrong_scope: bool = False) -> str:
    active = "" if wrong_scope else ' class="active"'
    second_id = "458" if duplicate else "459"
    cards = "".join(
        f'<div class="col-12"><div data-id="{key}">'
        f'<p class="title-show">{title}</p>'
        '<p class="v1-size16-font v1-sec-font">2026-07-03 11:35:11'
        "<span>|</span>职位数：2<span>|</span>北京/西安</p></div>"
        '<div class="v1-jd-con"><p>岗位职责：设计飞控</p>'
        "<p>任职要求：本科及以上</p></div></div>"
        for key, title in (("458", "飞控工程师"), (second_id, "算法工程师"))
    )
    return (
        f'<a href="/about/school.html"{active}>校园招聘</a>'
        '<select id="zwid"><option value="">全部</option>'
        '<option value="飞控工程师">飞控工程师</option>'
        '<option value="算法工程师">算法工程师</option></select>'
        f'<div id="gwList">{cards}</div>'
    )


def test_uatair_parses_full_campus_page() -> None:
    rows = UatairCampus.parse_catalog(catalog())
    assert [row["id"] for row in rows] == ["458", "459"]
    assert rows[0]["published"] == "2026-07-03"
    assert rows[0]["location"] == "北京/西安"
    assert "设计飞控" in rows[0]["duties"]
    assert "本科及以上" in rows[0]["requirements"]


@pytest.mark.parametrize("mutation", [{"duplicate": True}, {"wrong_scope": True}])
def test_uatair_rejects_duplicate_or_social_page(mutation: dict[str, bool]) -> None:
    with pytest.raises(CrawlError):
        UatairCampus.parse_catalog(catalog(**mutation))
