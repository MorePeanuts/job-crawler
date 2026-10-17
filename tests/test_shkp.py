from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.shkp import ShkpMainland, parse
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session


def document(names: tuple[str, ...] = ("商场租务", "顾客关系管理（CRM）", "写字楼销售租赁")) -> str:
    items = "".join(
        f'<div class="accordion-item"><div class="title">{name}</div><div class="accordion-content"><p>部门负责租赁管理工作。</p><ul><li>进行市场调研。</li></ul></div></div>'
        for name in names
    )
    return f"""<h1>管理培训生(内地)</h1>
    <div><h3>聘任地区</h3><p>上海 | 南京 | 苏州</p></div>
    <div><h3>聘任部门</h3>{items}</div>
    <div><h3>入职要求</h3><p>应届或近年毕业的大学生，具备沟通能力。</p></div>
    <div><h3>申请及查询</h3><table>
    <tr><td colspan="2">管理培训生(内地)招聘<br>2027年</td></tr>
    <tr><td>申请截止日期</td><td>2026年11月22日</td></tr>
    <tr><td>正式上班</td><td>2027年7月</td></tr></table>
    <a href="https://xyz.51job.com/External/Apply.aspx?CtmID=7978865">申请</a></div>
    <footer>新鸿基地产发展有限公司</footer>"""


def test_all_departments_and_full_cities_with_source_deadline() -> None:
    rows = parse(document())
    assert len(rows) == 3 and len({r.key for r in rows}) == 3
    assert rows[0].title == "管理培训生（内地）—商场租务"
    assert rows[0].location == "上海 | 南京 | 苏州"
    assert rows[0].deadline == "2026-11-22" and rows[0].batch == "2027年内地管理培训生"
    assert "市场调研" in rows[0].duties and "沟通能力" in rows[0].requirements
    expanded = parse(document(("新方向", "商场租务", "顾客关系管理（CRM）", "写字楼销售租赁")))
    assert len(expanded) == 4 and expanded[1].key == rows[0].key


@pytest.mark.parametrize("change", ["duplicate", "empty", "heading", "date", "link"])
def test_incomplete_sections_or_new_links_fail(change: str) -> None:
    html = document()
    if change == "duplicate":
        html = document(("商场租务", "商场租务"))
    elif change == "empty":
        html = html.replace("<p>部门负责租赁管理工作。</p><ul><li>进行市场调研。</li></ul>", "")
    elif change == "heading":
        html = html.replace("<h1>管理培训生(内地)</h1>", "<h1>未授权</h1>")
    elif change == "date":
        html = html.replace("2026年11月22日", "待定")
    else:
        html = html.replace("部门负责租赁管理工作。", '<a href="/unparsed">查看完整职责</a>')
    with pytest.raises(CrawlError):
        parse(html)


class Replay:
    last_evidence = "fixture"

    def __init__(self, output: Path):
        self.output = output
        self.page = self

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://www.shkp.com/zh-CN/work-with-us/management-trainee-mainland"

    async def content(self) -> str:
        return document()

    def snapshot(self, label: str, html: str) -> str:
        return "fixture"


async def test_no_invented_publication_or_degree_and_incremental_reuse(
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
        assert listing_job is not None
        assert listing_job.education == listing_job.published == ""
        assert isinstance(listing, dict) and listing["deadline"] == "2026-11-22"
        scope.reused_details += 1
        return [listing_job]

    monkeypatch.setattr(Adapter, "before_detail", before)
    source = Source(
        source_id="COM0246",
        company_id="COM0246",
        company="新鸿基地产发展有限公司",
        url="https://www.shkp.com/zh-CN/work-with-us/management-trainee-mainland",
    )
    result = await ShkpMainland(source, cast(Session, Replay(tmp_path)), now).collect()
    assert result.coverage_issues() == [] and len(result.jobs) == 3
    assert result.scopes[0].reused_details == 3
