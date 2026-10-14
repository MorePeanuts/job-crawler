"""Replay the two roles and the headquarters proof in the official notice."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.shccig_mt import COMPANY, ShccigHeadquartersTrainees
from job_crawler.models import Source


def article(*, headquarters: bool = True, deadline: str = "2026年11月30日") -> str:
    statement = (
        "由集团总部统一招录、统一培养、统一管理、统一调配" if headquarters else "由下属公司分别招录"
    )
    paragraphs = [
        "一、管培生计划简介",
        statement,
        "二、招聘对象",
        "2027届应届硕博士研究生",
        "三、招聘岗位及专业",
        "1.职能管理岗",
        "学历要求：全日制硕士研究生及以上",
        "招聘人数：5-10人",
        "专业要求：法学类、财务审计类",
        "2.技术管理岗",
        "学历要求：全日制硕士研究生及以上",
        "招聘人数：5-10人",
        "专业要求：矿业类、化学化工类",
        "四、应聘基本条件",
        "1.2027届应届毕业生",
        "五、报名方式",
        "1.报名通道",
        "2.报名截止时间",
        deadline,
        "六、招聘流程",
    ]
    return (
        "<div class='article'><h1>"
        + COMPANY
        + " 2027年度管理培训生招聘简章</h1>"
        + "<div class='article-tishi'><span>集团公司人力资源部</span><span>2026-09-16</span></div>"
        + "<div class='article-con'>"
        + "".join(f"<p>{item}</p>" for item in paragraphs)
        + "</div></div>"
    )


class Page:
    def __init__(self, html: str) -> None:
        self.html = html

    async def content(self) -> str:
        return self.html


class Replay:
    last_evidence = "page.json"

    def __init__(self, html: str) -> None:
        self.page = Page(html)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith("/index/Article/index.html?cid=97&id=1429903")

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected observed call: {needle}")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError(f"unexpected request: {url}")


def source() -> Source:
    return Source(
        source_id="COM0062",
        company_id="COM0062",
        company=COMPANY,
        url="https://www.shccig.com/index/Article/index.html?cid=97&id=1429903",
    )


async def test_shccig_two_headquarters_roles(now: datetime) -> None:
    result = await ShccigHeadquartersTrainees(source(), Replay(article()), now).collect()
    assert result.coverage_issues() == []
    assert [j.title for j in result.jobs] == ["职能管理岗", "技术管理岗"]
    assert all(j.location == "" and j.duties == "" for j in result.jobs)
    assert all(j.published == "2026-09-16" and j.deadline == "2026-11-30" for j in result.jobs)


async def test_shccig_missing_headquarters_proof_is_blocked(now: datetime) -> None:
    result = await ShccigHeadquartersTrainees(
        source(), Replay(article(headquarters=False)), now
    ).collect()
    assert result.coverage_issues()
    assert result.jobs == []


async def test_shccig_expired_notice_has_no_effective_jobs(now: datetime) -> None:
    result = await ShccigHeadquartersTrainees(
        source(), Replay(article(deadline="2026-10-01")), now
    ).collect()
    assert result.coverage_issues() == []
    assert result.jobs == []
    assert result.scopes[0].skipped_expired == 2
