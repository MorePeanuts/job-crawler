"""Checks Rongsheng's 2027 boardroom and production role boundaries."""

import pytest

from job_crawler.adapters.rongsheng_hebut import roster
from job_crawler.transport import CrawlError


def notice(*, extra: str = "", employer: str = "浙江荣盛控股集团有限公司") -> str:
    return f"""
    <div class="zhaopinxx_con1">
      <p class="p1">荣盛集团2027届全球校园招聘正式启动</p>
      <a class="p2">{employer}</a>
      <p class="p3">发布时间：2026-10-08<span>浏览量：194</span></p>
    </div>
    <div class="zhaopinxx_con2_con">
      <p>荣盛集团2027届校园招聘</p><p>一、【专业大类】</p><p>化工、材料、法学</p>
      <p>二、【招聘岗位】</p>
      <p>集团总部（杭州萧山）：法务</p>
      <p>商务板块（杭州萧山）：商务培训生</p>
      <p>炼化板块（浙江舟山）：生产管培生（工艺、设备、电气、仪控）、翻译、会计</p>
      <p>创新中心（浙江宁波）：研发{extra}</p>
      <p>三、【网申链接】</p><p><a title="易拉宝.png"
        href="/Upload/file/20261008/1791423919814812.png">易拉宝</a></p>
    </div>
    """


def test_roster_keeps_production_tracks_as_one_job() -> None:
    published, rows = roster(notice())
    assert published == "2026-10-08"
    assert len(rows) == 6
    assert rows[2]["title"] == "生产管培生（工艺、设备、电气、仪控）"
    assert rows[2]["location"] == "浙江舟山"


def test_roster_rejects_new_job_and_wrong_employer() -> None:
    with pytest.raises(CrawlError):
        roster(notice(extra="、新增岗位"))
    with pytest.raises(CrawlError):
        roster(notice(employer="其他企业"))
