"""中南大学双选会多企业配置不得串岗。"""

from datetime import datetime
from typing import cast

import pytest

from job_crawler.adapters.yuneng_csu import CsuFair2027, ShagangCsu2027, ZhongjinlingnanCsu2027
from job_crawler.models import Source
from job_crawler.transport import Session


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
        assert "/largefairs/company/id/1312/sid/" in url


def fixture(employer: str, credit_code: str) -> str:
    return (
        "<h1>中南大学2027届秋季第二场大型综合双选会</h1>"
        '<table id="lTable"><tr><td>单位全称</td>'
        f"<td>{employer}</td><td>统一社会信用代码</td><td>{credit_code}</td></tr>"
        "<tr><td>招聘内容</td></tr>"
        "<tr><td>工程师</td><td>机械工程</td><td>3</td><td>10000</td>"
        '<td>本科</td><td>全职</td><td><a class="apply_job" data-id="88">投递简历</a></td></tr>'
        "</table>"
    )


@pytest.mark.parametrize(
    ("cls", "source_id"),
    [(ZhongjinlingnanCsu2027, "COM0282"), (ShagangCsu2027, "COM0109")],
)
async def test_csu_tenant_identity_isolated(cls: type[CsuFair2027], source_id: str) -> None:
    body = fixture(cls.employer, cls.credit_code)
    source = Source(
        source_id=source_id,
        company_id=source_id,
        company=cls.employer,
        url=f"https://career.csu.edu.cn{cls.path}",
    )
    result = await cls(source, cast(Session, Replay(body)), datetime(2026, 10, 20)).collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == 1
    assert result.jobs[0].unit == cls.employer

    other_body = fixture("其他公司", cls.credit_code)
    wrong = await cls(source, cast(Session, Replay(other_body)), datetime(2026, 10, 20)).collect()
    assert wrong.coverage_issues()
    assert not wrong.jobs
