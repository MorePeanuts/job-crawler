"""湖南裕能中南大学双选会的岗位身份和局部失败回放。"""

from datetime import datetime
from typing import cast

import pytest

from job_crawler.adapters.yuneng_csu import YunengCsu2027, roster
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

URL = "https://career.csu.edu.cn/largefairs/company/id/1312/sid/104/stype/1"


def html(
    *,
    employer: str = "湖南裕能新能源电池材料股份有限公司",
    duplicate: bool = False,
    bad: bool = False,
) -> str:
    second_id = "1" if duplicate else "2"
    nature = "实习" if bad else "全职"
    return (
        "<h1>中南大学2027届秋季第二场大型综合双选会</h1>"
        '<table id="lTable"><tr><td>单位全称</td>'
        f"<td>{employer}</td><td>统一社会信用代码</td>"
        "<td>91430300MA4L54TU10</td></tr>"
        "<tr><td>招聘内容</td></tr>"
        "<tr><td>材料研发工程师</td><td>材料与化工</td><td>20</td>"
        "<td>12500</td><td>硕士</td><td>全职</td>"
        '<td><a class="apply_job" data-id="1">投递简历</a></td></tr>'
        "<tr><td>工艺工程师</td><td>材料科学</td><td>10</td>"
        f"<td>7500</td><td>本科</td><td>{nature}</td>"
        f'<td><a class="apply_job" data-id="{second_id}">投递简历</a></td></tr>'
        "</table>"
    )


class Page:
    def __init__(self, body: str) -> None:
        self.body = body

    async def content(self) -> str:
        return self.body


class Replay:
    last_evidence = "csu-fair.html"

    def __init__(self, body: str) -> None:
        self.page = Page(body)

    async def open(self, url: str, **kwargs: object) -> None:
        assert url == URL


def adapter(replay: Replay) -> YunengCsu2027:
    return YunengCsu2027(
        Source(
            source_id="COM0415",
            company_id="COM0415",
            company="湖南裕能新能源电池材料股份有限公司",
            url=URL,
        ),
        cast(Session, replay),
        datetime(2026, 10, 20),
    )


async def test_yuneng_extracts_every_posting_without_treating_fair_date_as_job_date() -> None:
    result = await adapter(Replay(html())).collect()
    assert not result.coverage_issues()
    assert {job.source_key for job in result.jobs} == {"1", "2"}
    assert result.scopes[0].terminal
    assert result.scopes[0].details == 2
    assert all(job.published == job.deadline == "" for job in result.jobs)
    assert result.jobs[0].requirements == "材料与化工"
    assert result.jobs[0].duties == ""


async def test_yuneng_bad_row_is_partial_and_keeps_valid_row() -> None:
    result = await adapter(Replay(html(bad=True))).collect()
    assert len(result.jobs) == 1
    assert result.coverage_issues()
    assert result.issues[0].job_key == "2"


def test_yuneng_rejects_wrong_employer_and_duplicate_id() -> None:
    with pytest.raises(CrawlError):
        roster(html(employer="其他公司"))
    with pytest.raises(CrawlError):
        roster(html(duplicate=True))
