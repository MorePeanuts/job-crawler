"""An experienced vacancy table cannot stand in for an unchecked youth branch."""

from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.newworld import (
    ENTRY,
    PROGRAMME,
    NewWorldCareers,
    catalog,
    experience,
    programme,
)
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

FIX = Path(__file__).parent / "fixtures/newworld"


def test_real_experience_and_upload_date():
    rows = catalog((FIX / "catalog.html").read_text())
    assert len(rows) == 3
    assert rows[0].key == "1502" and rows[0].uploaded == "2026年10月13日"
    for row in rows:
        evidence = experience((FIX / f"{row.key}.html").read_text(), row)
        assert "experience" in evidence and any(x.isdigit() for x in evidence)
    assert "HYAB" in programme((FIX / "youth.html").read_text())


@pytest.mark.parametrize(
    "phrase",
    [
        "Fresh graduates are welcome with relevant internships.",
        "Recent graduate applications accepted.",
        "No prior experience required.",
        "0-1 years of working experience.",
        "1 year of experience is preferred.",
        "University graduates in finance.",
    ],
)
def test_no_assumed_experience(phrase):
    row = catalog((FIX / "catalog.html").read_text())[0]
    html = f'<h1><span itemprop="title">{row.title}</span></h1><script>{{"internalId":"1502-en_US"}}</script><span class="jobdescription">Requirements:\n{phrase}</span>'
    with pytest.raises(CrawlError):
        experience(html, row)


def test_graduate_exception_overrides_experience():
    row = catalog((FIX / "catalog.html").read_text())[0]
    html = (FIX / "1502.html").read_text()
    html = html.replace("</html>", "").replace(
        "</span><script", "<p>Fresh graduates will also be considered.</p></span><script"
    )
    # Keep the ordinary one-year clause: the alternative must still block exclusion.
    assert "Minimum 1-year" in html
    with pytest.raises(CrawlError):
        experience(html, row)


@pytest.mark.parametrize("fault", ["identity", "title", "body", "requirements"])
def test_detail_contract(fault):
    row = catalog((FIX / "catalog.html").read_text())[0]
    html = (FIX / "1502.html").read_text()
    if fault == "identity":
        html = html.replace("1502-en_US", "1503-en_US")
    if fault == "title":
        html = html.replace("Customer Service Officer", "Another Position")
    if fault == "body":
        html = html.replace('class="jobdescription"', 'class="unknown"')
    if fault == "requirements":
        html = html.replace("Requirements:", "Qualifications:")
    with pytest.raises(CrawlError):
        experience(html, row)


@pytest.mark.parametrize(
    "fault", ["empty", "duplicate", "external", "pager", "missing_date", "extra_link"]
)
def test_catalog_contract(fault):
    html = (FIX / "catalog.html").read_text()
    if fault == "empty":
        html = "<html>新世界发展有限公司</html>"
    if fault == "duplicate":
        html = html.replace("/1551", "/1502")
    if fault == "external":
        html = html.replace("careers.nwplatform.com", "other.example")
    if fault == "pager":
        html += '<div class="pager">next</div>'
    if fault == "missing_date":
        html = html.replace("date-display-single", "unknown")
    if fault == "extra_link":
        html += '<a href="https://careers.nwplatform.com/job-invite/8888">new role</a>'
    with pytest.raises(CrawlError):
        catalog(html)


class Replay:
    last_evidence = "entry"

    def __init__(self, output, fault=""):
        self.output = output
        self.fault = fault
        self.page = self
        self.url = ENTRY
        self.requested = []

    async def open(self, url, **kwargs):
        self.url = url
        self.last_evidence = url

    async def content(self):
        if self.url == ENTRY:
            return (FIX / "catalog.html").read_text()
        if self.url == PROGRAMME:
            html = (FIX / "youth.html").read_text()
            return html.replace("HYAB", "New Graduate Programme") if self.fault == "youth" else html
        return self.detail(self.url)

    def detail(self, url):
        key = url.rsplit("/", 1)[-1]
        self.requested.append(key)
        if self.fault == "detail" and key == "1551":
            raise TimeoutError("unavailable")
        return (FIX / f"{key}.html").read_text()

    async def request_html(self, url):
        self.last_evidence = url
        return self.detail(url)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["", "detail", "youth"])
async def test_collection(tmp_path, now, fault):
    replay = Replay(tmp_path, fault)
    source = Source(
        source_id="COM0499", company_id="COM0499", company="新世界发展有限公司", url=ENTRY
    )
    result = await NewWorldCareers(source, cast(Session, replay), now).collect()
    assert not result.jobs and replay.requested == ["1502", "1551", "1587"]
    if not fault:
        assert not result.coverage_issues()
        assert result.scopes[0].expected == result.scopes[0].skipped_out_of_scope == 3
        assert result.scopes[1].skipped_out_of_scope == 1
    else:
        assert result.issues and result.coverage_issues()
        if fault == "detail":
            assert result.scopes[0].skipped_out_of_scope == 2 and result.scopes[1].terminal
        else:
            assert result.scopes[0].skipped_out_of_scope == 3
