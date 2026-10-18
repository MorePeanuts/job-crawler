"""Experienced recruitment communications cannot become five campus jobs."""

from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.sasdragon import ENTRY, SasDragonCareers, notice
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

FIX = Path(__file__).parent / "fixtures/sasdragon/careers.html"


class Replay:
    def __init__(self, output, fault=""):
        self.output = output
        self.fault = fault
        self.last_evidence = "current-page"
        self.page = self
        self.url = ENTRY

    async def open(self, url, *, ready_endpoints=()):
        assert url == ENTRY
        if self.fault == "request":
            raise CrawlError("access_denied", "HTTP 403")
        if self.fault == "redirect":
            self.url = "https://sasdragon.com.cn/"

    async def content(self):
        return "<html></html>" if self.fault == "empty" else FIX.read_text()


async def test_one_notice_zero_formal_jobs(tmp_path, now):
    source = Source(
        source_id="COM0469", company_id="COM0469", company="时捷集团有限公司", url=ENTRY
    )
    result = await SasDragonCareers(source, cast(Session, Replay(tmp_path)), now).collect()
    assert not result.coverage_issues() and not result.jobs
    assert len(result.scopes) == 1
    assert result.scopes[0].unique == result.scopes[0].skipped_out_of_scope == 1


@pytest.mark.parametrize(
    "old,new",
    [
        ("Stock Code:1184", "Stock Code:9999"),
        ("high caliber and well-experienced people", "fresh graduates"),
        ("Careers</div>", "New Jobs</div>"),
        ("· Logistics", "· Graduate Trainee"),
        ("medical insurance", "different qualification"),
        ("mailto:frentemak@sasdragon.com.hk", "https://example.test/jobs.pdf"),
        ("</body>", '<a href="/new-campus">Campus jobs</a></body>'),
        ("</strong>", '</strong><img src="new-jobs.jpg">'),
        ("</body>", '<div class="pagination">2</div></body>'),
    ],
)
def test_changed_scope_cannot_inherit_old_zero(old, new):
    html = FIX.read_text()
    if old == "Careers</div>":
        html = html.replace("Careers", "New Jobs")
    else:
        assert old in html
        html = html.replace(old, new)
    with pytest.raises(CrawlError):
        notice(html)


@pytest.mark.parametrize("fault", ["request", "redirect", "empty"])
async def test_failed_page_never_counts_zero(tmp_path, now, fault):
    source = Source(
        source_id="COM0469", company_id="COM0469", company="时捷集团有限公司", url=ENTRY
    )
    result = await SasDragonCareers(source, cast(Session, Replay(tmp_path, fault)), now).collect()
    assert result.coverage_issues()
