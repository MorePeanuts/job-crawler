"""UnionTech card to panel identity and recruitment type conflict replay."""

from datetime import datetime
from typing import cast

from job_crawler.adapters.uniontech import UnionTechCampus
from job_crawler.models import Source
from job_crawler.transport import Session as TransportSession


def page_html(*, mismatch: bool = False) -> str:
    detail = "内核专家" if mismatch else "内核工程师"
    return f"""
    <div id="pos">
      <div class="zp-item" onclick="pageNew(1)"><span>内核工程师</span>
        <em>武汉 ｜ 校园招聘 ｜ 开发类</em><div class="zp-cont"><p>招聘中</p></div></div>
      <div class="zp-item" onclick="pageNew(2)"><span>产品经理</span>
        <em>北京 ｜ 校园招聘 ｜ 产品类</em><div class="zp-cont"><p>招聘中</p></div></div>
      <div class="zp-item" onclick="pageNew(3)"><span>销售经理</span>
        <em>北京 ｜ 社会招聘 ｜ 销售类</em><div class="zp-cont"><p>招聘中</p></div></div>
    </div>
    <div id="1"><div class="zp-head"><span>{detail}</span>
      <p>武汉 ｜ 开发类 ｜ 本科 ｜ 校园招聘</p></div>
      <div id="info1">研发内核</div><div id="info1_1">本科</div></div>
    <div id="2"><div class="zp-head"><span>产品经理</span>
      <p>北京 ｜ 产品类 ｜ 本科 ｜ 社会招聘</p></div>
      <div id="info2">产品设计</div><div id="info2_1">本科</div></div>
    """


class Page:
    def __init__(self, mismatch: bool = False) -> None:
        self.mismatch = mismatch

    async def content(self) -> str:
        return page_html(mismatch=self.mismatch)


class Session:
    last_evidence = "Recruitment.html"

    def __init__(self, mismatch: bool = False) -> None:
        self.page = Page(mismatch)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://uniontech.com/Recruitment.html"


def source() -> Source:
    return Source(
        source_id="COM0633",
        company_id="COM0633",
        company="统信软件",
        url="https://uniontech.com/Recruitment.html",
    )


async def test_uniontech_excludes_conflicted_detail(now: datetime) -> None:
    result = await UnionTechCampus(source(), cast(TransportSession, Session()), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].unique == 3
    assert result.scopes[0].skipped_out_of_scope == 2
    assert len(result.jobs) == 1
    assert result.jobs[0].duties == "研发内核"
    assert result.jobs[0].location == "武汉"
    assert not result.jobs[0].published
    assert result.warnings[0].code == "recruitment_type_conflict"


async def test_uniontech_rejects_detail_title_mismatch(now: datetime) -> None:
    result = await UnionTechCampus(
        source(), cast(TransportSession, Session(mismatch=True)), now
    ).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
