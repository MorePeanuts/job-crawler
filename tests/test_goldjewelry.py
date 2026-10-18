"""An explicit campus zero requires source count, DOM, filters and both pages."""

from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.goldjewelry import (
    COMPANY,
    ENTRY,
    ROOT,
    SEARCH,
    GoldJewelryCampus,
    empty_campus,
    navigation,
)
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

FIX = Path(__file__).parent / "fixtures/goldjewelry"


class Replay:
    def __init__(self, output, failed_url="", fault=""):
        self.output = output
        self.failed_url = failed_url
        self.fault = fault
        self.last_evidence = ""
        self.url = ""
        self.page = self
        self.visited = []

    async def open(self, url, *, ready_endpoints=()):
        assert url in [ROOT, ENTRY, SEARCH]
        self.visited.append(url)
        self.url = url
        self.last_evidence = f"page-{len(self.visited)}"
        if url == self.failed_url:
            if self.fault == "http":
                raise CrawlError("http_error", "HTTP 502")
            if self.fault == "redirect":
                self.url = "https://chnau99999.com/"

    async def content(self):
        if self.url == self.failed_url and self.fault == "empty":
            return "<html></html>"
        filename = {ROOT: "talents.html", ENTRY: "campus.html", SEARCH: "search.html"}[self.url]
        html = (FIX / filename).read_text()
        if self.url == self.failed_url and self.fault == "positive":
            return html.replace("total: 0", "total: 1")
        return html


def source():
    return Source(source_id="COM0253", company_id="COM0253", company=COMPANY, url=ENTRY)


async def test_complete_two_response_zero_with_verified_type(tmp_path, now):
    replay = Replay(tmp_path)
    result = await GoldJewelryCampus(source(), cast(Session, replay), now).collect()
    assert not result.coverage_issues() and not result.jobs
    assert replay.visited == [ROOT, ENTRY, SEARCH]
    nav, campus = result.scopes
    assert (nav.unique, nav.details, nav.skipped_out_of_scope) == (3, 1, 2)
    assert campus.expected == campus.listed == campus.unique == 0
    assert nav.terminal and campus.terminal and len(campus.evidence) == 3
    assert navigation((FIX / "talents.html").read_text())["校园招聘"] == ENTRY


@pytest.mark.parametrize(
    "old,new",
    [
        ("社会招聘", "春季招聘"),
        ("/page/social/1", "/page/social/9"),
        ("校园招聘", "社会招聘"),
        (COMPANY, "中国黄金集团有限公司"),
        ("</body>", '<div class="tab-box-li-2">新入口</div></body>'),
    ],
)
def test_navigation_cannot_silently_change(old, new):
    with pytest.raises(CrawlError):
        navigation((FIX / "talents.html").read_text().replace(old, new))


@pytest.mark.parametrize(
    "old,new",
    [
        ("total: 0", "total: 1"),
        ("total: 0", "unknown: 0"),
        ("new Paging({", "new Paging({unknown:1,"),
        ("var zhaopintype = 1;", "var zhaopintype = 0;"),
        ("<i>0</i>", "<i>1</i>"),
        ('class="paging"', 'class="missing-paging"'),
        ('class="social-content"', 'class="missing-content"'),
        ("岗位名称", "职位名称"),
        ('<div class="social-content-table">', '<div class="social-content-table">新岗位'),
        (
            '<div class="social-content-table">',
            '<div class="social-content-table"><img src="jobs.png">',
        ),
        (
            '<div class="social-content-table">',
            '<div class="social-content-table"><div class="social-content-table-tdata"></div>',
        ),
        ('<div class="social-content">', '<div class="social-content"><div>另一个单位</div>'),
        ('<option value="1">上海', '<option selected="selected" value="1">上海'),
        ('id="gangweimingcheng"', 'value="财务" id="gangweimingcheng"'),
        ('"/page/social/Search/"', '"/changed/Search/"'),
        ("</script>", "var other = new Paging({total:0});</script>"),
        (COMPANY, "中国黄金集团有限公司"),
    ],
)
def test_changed_or_filtered_catalog_is_not_zero(old, new):
    html = (FIX / "campus.html").read_text()
    assert old in html
    with pytest.raises(CrawlError):
        empty_campus(html.replace(old, new))


@pytest.mark.parametrize("url", [ROOT, ENTRY, SEARCH])
@pytest.mark.parametrize("fault", ["http", "redirect", "empty"])
async def test_any_failed_response_keeps_coverage_incomplete(tmp_path, now, url, fault):
    result = await GoldJewelryCampus(
        source(), cast(Session, Replay(tmp_path, url, fault)), now
    ).collect()
    assert result.coverage_issues() and not result.jobs


async def test_search_disagrees_with_initial_zero(tmp_path, now):
    replay = Replay(tmp_path, SEARCH, "positive")
    result = await GoldJewelryCampus(source(), cast(Session, replay), now).collect()
    assert result.coverage_issues() and not result.jobs
    assert not result.scopes[-1].terminal
    assert result.scopes[-1].evidence == ["page-2"]
