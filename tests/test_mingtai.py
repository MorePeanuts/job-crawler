"""Replay the public seven-job directory; never use application form data."""

from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from bs4 import BeautifulSoup

from job_crawler.adapters.mingtai import COMPANY, PATH, ROOT, MingtaiCampus, accepts_graduates
from job_crawler.models import Source
from job_crawler.transport import Session

HTML = (Path(__file__).parent / "fixtures/mingtai/catalog.html").read_text()


class Replay:
    last_evidence = "public-inline-directory"

    def __init__(self, html: str = HTML):
        self.html = html
        self.page = self

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == ROOT + PATH and not ready_endpoints

    async def content(self) -> str:
        return self.html


def adapter(html: str, now: datetime) -> MingtaiCampus:
    return MingtaiCampus(
        Source(source_id="COM0411", company_id="COM0411", company=COMPANY, url=ROOT + PATH),
        cast(Session, Replay(html)),
        now,
    )


async def test_complete_dual_layout_is_seven_jobs_not_fourteen(now: datetime) -> None:
    result = await adapter(HTML, now).collect()
    assert not result.coverage_issues()
    scope = result.scopes[0]
    assert scope.expected == scope.listed == scope.unique == 7
    assert scope.details == 2 and scope.skipped_out_of_scope == 5 and scope.terminal
    assert [job.source_key for job in result.jobs] == ["1646865502762569728", "1647144639339302912"]
    recycled, aluminium = result.jobs
    assert recycled.title == "外贸业务员-再生铝方向" and recycled.location == "巩义"
    assert aluminium.location == "郑州" and recycled.published == "2025-05-16"
    assert "全球废铝资源" in recycled.duties and "接受应届毕业生" in recycled.requirements
    assert recycled.unit == "销售外贸部" and recycled.work_type == "校招"
    assert recycled.deadline == "" and recycled.source_url.endswith(recycled.source_key + ".shtml")
    assert recycled.evidence == ["public-inline-directory"]


@pytest.mark.parametrize(
    "fault",
    ["identity", "empty", "mobile", "duplicate_id", "mismatch", "date", "body", "pagination"],
)
async def test_unproven_catalog_is_not_complete(fault: str, now: datetime) -> None:
    doc = BeautifulSoup(HTML, "html.parser")
    if fault == "identity":
        html = HTML.replace(COMPANY, "其他公司")
    elif fault == "empty":
        html = "暂无数据"
    elif fault == "pagination":
        html = HTML + '<a href="?page=2">下一页</a>'
    else:
        mobile = doc.select(".table-box-xs > ul > li > a")
        if fault == "mobile":
            mobile[-1].decompose()
        elif fault == "duplicate_id":
            mobile[-1]["href"] = mobile[0]["href"]
        elif fault == "mismatch":
            doc.select(".table-box > ul.table > li > .item")[0].string = "错误标题"
        elif fault == "date":
            doc = BeautifulSoup(str(doc).replace("2025-05-16", "2025-15-16"), "html.parser")
        elif fault == "body":
            doc.select(".table-box > ul.table > li > .con")[-1].decompose()
        html = str(doc)
    assert (await adapter(html, now).collect()).coverage_issues()


@pytest.mark.parametrize("fault", ["heading", "attachment", "unknown_graduate", "paragraph"])
async def test_later_bad_detail_preserves_first_job(fault: str, now: datetime) -> None:
    doc = BeautifulSoup(HTML, "html.parser")
    body = doc.select(".table-box > ul.table > li > .con")[-1]
    block = body.select(":scope > .bb")[0]
    if fault == "heading":
        heading = block.select_one(".tt")
        assert heading is not None
        heading.string = "未知章节"
    elif fault == "attachment":
        block.append(BeautifulSoup('<img src="requirements.png">', "html.parser"))
    elif fault == "paragraph":
        for p in block.find_all("p", recursive=False):
            p.decompose()
    else:
        for p in block.find_all("p", recursive=False):
            if "接受应届毕业生" in p.get_text():
                p.string = "2、应届毕业生条件请咨询。"
    result = await adapter(str(doc), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 1
    assert result.jobs[0].source_key == "1646865502762569728"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2、接受应届毕业生，有外贸经验者优先;", True),
        ("2、不接受应届毕业生。", False),
        ("3、有经验者优先。", False),
    ],
)
def test_only_explicit_graduate_eligibility(value: str, expected: bool) -> None:
    assert accepts_graduates(value) is expected


@pytest.mark.parametrize("value", ["应届请咨询", "2、接受应届毕业生。\n3、不接受应届毕业生。"])
def test_ambiguous_graduate_eligibility_fails(value: str) -> None:
    with pytest.raises(Exception, match="应届资格"):
        accepts_graduates(value)


async def test_equal_titles_keep_distinct_source_ids(now: datetime) -> None:
    html = HTML.replace("外贸业务员-铝加工方向", "外贸业务员-再生铝方向")
    result = await adapter(html, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 2
    assert result.jobs[0].title == result.jobs[1].title
    assert result.jobs[0].source_key != result.jobs[1].source_key
