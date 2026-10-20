"""The 2027 YTO notice exposes four complete hiring tracks."""

import pytest

from job_crawler.adapters.yto_zju import demand
from job_crawler.transport import CrawlError


def notice() -> str:
    rows = "".join(
        f"<p>{i}．{title}工作地点:{location}工作方向:{direction}专业要求:{majors}</p>"
        for i, title, location, direction, majors in (
            (1, "国际管培生", "全球", "海外快递", "物流专业"),
            (2, "科技管培生", "上海/杭州/西安", "开发、算法", "计算机专业"),
            (3, "速递管培生", "全国", "营运", "管理专业"),
            (4, "圆通航空", "杭州/嘉兴", "机务工程", "机械专业"),
        )
    )
    return (
        '<div class="con-tit">圆通2027年校招宣讲会</div>'
        '<div class="dwxx-tit">圆通速递有限公司</div>'
        '<div class="con-info"><span class="dif">发布时间：2026-09-28 08:51:13  点击数量：540</span></div>'
        '<div class="con-con">三、招聘对象应届本科、硕士毕业生毕业时间2026年10月1日-2027年9月30日'
        f"四、招聘岗位{rows}五、福利待遇六、校招日历网申：即日起 请尽早投递。</div>"
        '<div class="con-con">企业介绍</div>'
    )


def test_four_tracks_keep_locations_and_directions() -> None:
    date, rows = demand(notice())
    assert date == "2026-09-28"
    assert [row["title"] for row in rows] == ["国际管培生", "科技管培生", "速递管培生", "圆通航空"]
    assert rows[1] == {
        "title": "科技管培生",
        "location": "上海/杭州/西安",
        "direction": "开发、算法",
        "majors": "计算机专业",
    }


def test_extra_hiring_track_or_missing_major_fails_closed() -> None:
    with pytest.raises(CrawlError):
        demand(
            notice().replace(
                "五、福利待遇", "5．新岗位工作地点:上海工作方向:研发专业要求:软件五、福利待遇"
            )
        )
    with pytest.raises(CrawlError):
        demand(notice().replace("专业要求:计算机专业", ""))


def test_non_2027_or_different_account_fails_closed() -> None:
    with pytest.raises(CrawlError):
        demand(notice().replace("2027年校招", "2026年校招"))
    with pytest.raises(CrawlError):
        demand(notice().replace("圆通速递有限公司</div>", "其他公司</div>"))
