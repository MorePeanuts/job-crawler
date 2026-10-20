"""中南大学双选会集团子公司岗位归属与源字段回放。"""

import pytest

from job_crawler.adapters.yuneng_csu import (
    CrccTwentyTwoCsu2027,
    CscecFiveCivilCsu2027,
    PowerchinaEightCsu2027,
    job_row,
    roster,
)
from job_crawler.transport import CrawlError


@pytest.mark.parametrize(
    "tenant", [CscecFiveCivilCsu2027, CrccTwentyTwoCsu2027, PowerchinaEightCsu2027]
)
def test_group_booth_requires_exact_legal_entity_and_keeps_unlimited_degree(
    tenant: type[CscecFiveCivilCsu2027] | type[CrccTwentyTwoCsu2027] | type[PowerchinaEightCsu2027],
) -> None:
    html = (
        "<h1>中南大学2027届秋季第二场大型综合双选会</h1>"
        '<table id="lTable"><tr><td>单位全称</td>'
        f"<td>{tenant.employer}</td><td>统一社会信用代码</td>"
        f"<td>{tenant.credit_code}</td></tr><tr><td>招聘内容</td></tr>"
        "<tr><td>工程管理</td><td>土木工程</td><td>3</td>"
        "<td>8000</td><td>不限</td><td>全职</td>"
        '<td><a class="apply_job" data-id="123">投递简历</a></td></tr></table>'
    )
    rows = roster(html, tenant.employer, tenant.credit_code)
    assert len(rows) == 1
    assert job_row(rows[0])["education"] == "不限"
    with pytest.raises(CrawlError):
        roster(
            html.replace(tenant.credit_code, "000000000000000000"),
            tenant.employer,
            tenant.credit_code,
        )
