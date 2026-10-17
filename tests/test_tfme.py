from datetime import datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlencode

import pytest

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.tfme import COMPANY, EMPLOYER, ROOT, TfmeCampus, catalog, detail
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session


def listing(count: int = 2) -> str:
    rows = "".join(
        f'<tr><td><a href="{ROOT}/job/view/id/{i}">工程师{i}-27</a></td>'
        f'<td><a class="apply_job" data-id="{i}">投递</a></td></tr>'
        for i in range(1, count + 1)
    )
    return f'<div class="unit-info"><div class="title"><h5>{COMPANY}</h5></div></div><p v-text-job-total>{count}个</p><table>{rows}</table>'


def job_page(identity: str = "1", degree: str = "博士") -> str:
    url = ROOT + "/job/view/id/" + identity
    share = "https://connect.qq.com/widget/shareqq/index.html?" + urlencode({"url": url})
    return f'''<div class="title-message"><span class="title">工程师{identity}-27</span>
    <a href="{EMPLOYER}">{COMPANY}</a></div>
    <div class="message-info">面议 | 不限 | 不限</div>
    <div class="share-link"><a class="icon-qq" href="{share}">分享</a></div>
    <li class="full-width">需求专业：物理学</li>
    <div class="details-mge"><h5 class="mge-title">职位详情</h5>
    <div class="aContent">岗位职责：\n开发新工艺。\n任职要求：\n1、全日制{degree}学历，物理相关专业（本科及研究生阶段211院校以上）。\n2、良好的沟通能力。</div></div>
    <div class="details-mge"><h5 class="mge-title">公司信息</h5><div class="aContent">公司1997年成立，南通市地址。不能作为岗位正文。</div></div>'''


def test_complete_catalog_and_body_degree_over_placeholder() -> None:
    count, rows = catalog(listing())
    assert count == len(rows) == 2
    values = detail(job_page(), rows[0])
    assert values["education"] == "博士"
    assert values["duties"] == "开发新工艺。"
    assert "本科及研究生阶段211" in values["requirements"]
    assert values["requirements"].endswith("需求专业：物理学")
    assert "1997" not in str(values)
    missing = job_page().replace(
        "1、全日制博士学历，物理相关专业（本科及研究生阶段211院校以上）。", "1、良好动手能力。"
    )
    assert detail(missing, rows[0])["education"] == ""


@pytest.mark.parametrize("change", ["count", "duplicate", "type", "employer", "page", "apply"])
def test_catalog_cannot_hide_missing_or_wrong_scope(change: str) -> None:
    html = listing()
    if change == "count":
        html = html.replace("2个", "3个")
    elif change == "duplicate":
        html = html.replace("/id/2", "/id/1").replace('data-id="2"', 'data-id="1"')
    elif change == "type":
        html = html.replace("工程师1-27", "实习生1-27")
    elif change == "employer":
        html = html.replace(COMPANY, "其他企业")
    elif change == "page":
        html += '<div class="pagination">下一页</div>'
    else:
        html = html.replace('data-id="2"', 'data-id="3"')
    with pytest.raises(CrawlError):
        catalog(html)


@pytest.mark.parametrize("change", ["identity", "title", "employer", "attachment", "empty"])
def test_detail_identity_and_unhandled_content_fail(change: str) -> None:
    row = catalog(listing())[1][0]
    html = job_page()
    if change == "identity":
        html = html.replace("%2Fid%2F1", "%2Fid%2F2")
    elif change == "title":
        html = html.replace("工程师1-27", "工程师2-27")
    elif change == "employer":
        html = html.replace("410286", "999999")
    elif change == "attachment":
        html = html.replace("开发新工艺。", '<a href="/unparsed.pdf">详细要求</a>')
    else:
        html = html.replace("职位详情", "未提供")
    with pytest.raises(CrawlError):
        detail(html, row)


class Replay:
    last_evidence = "catalog-evidence"

    def __init__(self, output: Path, fail: bool = False):
        self.output = output
        self.page = self
        self.fail = fail
        self.reads: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == EMPLOYER + "/tab/1"

    async def content(self) -> str:
        return listing()

    async def request_html(self, url: str, *, detail: bool = False) -> str:
        assert detail
        self.reads.append(url)
        if self.fail and url.endswith("/1"):
            raise CrawlError("request_failed", "临时详情失败")
        self.last_evidence = url
        return job_page(url.rsplit("/", 1)[-1])


def source() -> Source:
    return Source(source_id="COM0472", company_id="COM0472", company=COMPANY, url=EMPLOYER)


async def test_partial_failure_preserves_next_job_and_unknown_dates(
    tmp_path: Path, now: datetime
) -> None:
    replay = Replay(tmp_path, fail=True)
    result = await TfmeCampus(source(), cast(Session, replay), now).collect()
    assert len(result.jobs) == 1 and result.jobs[0].source_key == "2"
    assert result.scopes[0].unique == 2 and result.scopes[0].details == 1
    assert result.coverage_issues()
    job = result.jobs[0]
    assert job.location == job.address == job.published == job.deadline == ""
    assert job.evidence == ["catalog-evidence", ROOT + "/job/view/id/2"]


async def test_incremental_reuse_skips_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, now: datetime
) -> None:
    def before(
        self: Adapter,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job]:
        assert listing_job is not None and listing_job.published == ""
        assert evidence == "catalog-evidence"
        scope.reused_details += 1
        return [listing_job]

    monkeypatch.setattr(Adapter, "before_detail", before)
    replay = Replay(tmp_path)
    result = await TfmeCampus(source(), cast(Session, replay), now).collect()
    assert result.coverage_issues() == [] and len(result.jobs) == 2
    assert replay.reads == [] and result.scopes[0].reused_details == 2
