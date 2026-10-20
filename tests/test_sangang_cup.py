"""三钢 2027 计划的合并单元格法人边界与岗位代码。"""

import pytest

from job_crawler.adapters.sangang_cup import roster
from job_crawler.transport import CrawlError


def page(*, bad_span: bool = False, duplicate_code: bool = False) -> str:
    body = [
        "<tr><th>序号</th><th>招聘单位</th><th>下属企业</th><th>招聘人数</th><th>岗位代码</th><th>专业要求</th><th>学历要求</th><th>工作地点</th></tr>",
        "<tr><th>专业要求</th></tr>",
    ]
    for index in range(1, 48):
        code = f"SG-SM-{index:02d}" if index <= 10 else f"XCL-X-{index:02d}"
        if duplicate_code and index == 47:
            code = "SG-SM-01"
        parts = [f"<td>{index}</td>"]
        if index == 1:
            parts.extend(
                [
                    '<td rowspan="28">福建三钢闽光股份有限公司</td>',
                    f'<td rowspan="{9 if bad_span else 10}">三明闽光生产运营中心</td>',
                ]
            )
        parts.extend([f"<td>2</td><td>{code}</td><td>冶金工程</td>"])
        if index == 1:
            parts.extend(['<td rowspan="10">大学本科及以上</td>', '<td rowspan="12">福建三明</td>'])
        body.append("<tr>" + "".join(parts) + "</tr>")
    return (
        "福建省三钢（集团）有限责任公司2027年专业技术人员招聘 "
        "发布时间：2026年10月16日11:22 2027届专业技术岗高校毕业生招聘计划汇总表"
        "<table>" + "".join(body) + "</table>"
    )


def test_sangang_whole_roster_restricts_listed_center() -> None:
    published, rows = roster(page())
    assert published == "2026-10-16"
    assert len(rows) == 47
    assert [row["id"] for row in rows if row["included"] == "1"] == [
        f"SG-SM-{index:02d}" for index in range(1, 11)
    ]
    assert sum(row["included"] == "0" for row in rows) == 37


@pytest.mark.parametrize("kwargs", [{"bad_span": True}, {"duplicate_code": True}])
def test_sangang_boundary_or_duplicate_fails_closed(kwargs: dict[str, bool]) -> None:
    with pytest.raises(CrawlError):
        roster(page(**kwargs))
