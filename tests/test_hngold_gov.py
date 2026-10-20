"""The public 2027 recruitment plan is the complete job catalog."""

from io import BytesIO

import pytest
from openpyxl import Workbook

from job_crawler.adapters.hngold_gov import announcement, positions
from job_crawler.transport import CrawlError


def fixture_book(numbers: tuple[int, ...] = (1, 2)) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["附件"])
    sheet.append(["湖南黄金洞矿业有限责任公司2027年招聘计划表"])
    sheet.append(["序号", "岗位", "学历", "专业", "专业具体分支"])
    for number in numbers:
        sheet.append([number, f"岗位{number}", "本科及以上", "工程", "采矿工程"])
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def test_announcement_matches_one_official_attachment() -> None:
    html = """<div>湖南黄金洞矿业有限责任公司招聘公告 更新时间：2026-10-12
    招聘对象，寻找发光的你 应往届毕业生 招聘职位，精准匹配你的专业
    <a href="https://www.hnrcsc.com/xbrcw/1791769290586.xlsx">
    附件 湖南黄金洞矿业有限责任公司2027年招聘计划表.xlsx</a></div>"""
    assert announcement(html) == ("2026-10-12", "https://www.hnrcsc.com/xbrcw/1791769290586.xlsx")
    with pytest.raises(CrawlError):
        announcement(html.replace("2027年招聘计划表.xlsx", "2026年招聘计划表.xlsx"))


def test_positions_require_contiguous_numbering_and_columns() -> None:
    assert [row["title"] for row in positions(fixture_book())] == ["岗位1", "岗位2"]
    with pytest.raises(CrawlError):
        positions(fixture_book((1, 3)))
