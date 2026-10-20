"""The university table separates Zhongjin's owned units from a group institute."""

import pytest

from job_crawler.adapters.zhongjin_gold_chnu import INSTITUTE, MATERIALS, SMELTER, roster
from job_crawler.transport import CrawlError


def page() -> str:
    pieces = [
        f'<article class="articleCon"><h2 class="title">{SMELTER}2027年校园招聘简章</h2>',
        '<div class="property">发布时间：2026-10-03 01:15:41</div>',
        '<div class="conTxt">上市公司中金黄金股份有限公司全资子公司 '
        f"{MATERIALS}是中原黄金冶炼厂全资子公司<table>",
        "<tr><td>企业/单位</td><td>岗位</td><td>招聘人数</td>"
        "<td>学历要求</td><td>专业要求</td><td>联系人</td></tr>",
    ]
    for unit, count in ((SMELTER, 12), (MATERIALS, 6), (INSTITUTE, 5)):
        for index in range(count):
            first = f'<td rowspan="{count}">{unit}</td>' if index == 0 else ""
            last = "<td>联系人</td>" if index == 0 and unit != INSTITUTE else ""
            pieces.append(
                f"<tr>{first}<td>岗位{index}</td><td>1</td>"
                f"<td>本科及以上</td><td>化学工程</td>{last}</tr>"
            )
    return "".join(pieces) + "</table></div></article>"


def test_roster_has_18_owned_rows_and_5_other_rows() -> None:
    date, rows = roster(page())
    assert date == "2026-10-03"
    assert len(rows) == 23
    assert sum(row["unit"] != INSTITUTE for row in rows) == 18
    assert len({row["id"] for row in rows}) == 23


def test_roster_rejects_lost_group_boundary() -> None:
    with pytest.raises(CrawlError):
        roster(page().replace(f'rowspan="6">{MATERIALS}', f'rowspan="5">{MATERIALS}'))
