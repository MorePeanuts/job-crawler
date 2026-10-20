"""Contract checks for Hongwang's two KMUST campus-linked positions."""

import pytest

from job_crawler.adapters.hongwang_kmust import detail, roster
from job_crawler.transport import CrawlError


def event(*, count: int = 2, second_career: int = 714546) -> str:
    return f"""
    <h1>宏旺控股集团2027届校园招聘宣讲会</h1>
    <p>宏旺控股集团有限公司</p>
    <div id="tab-jobs">招聘职位 ({count})</div>
    <div id="pane-jobs">
      <div class="career-job job-item"><a class="career-job-name"
        href="/detail/job?id=3231523&amp;career_id=714546">财务专员（海外）</a></div>
      <div class="career-job job-item"><a class="career-job-name"
        href="/detail/job?id=3231309&amp;career_id={second_career}">安全专员</a></div>
    </div>
    """


def position(*, employer: str = "宏旺控股集团有限公司", year: str = "2027") -> str:
    return f"""
    <h1 class="job-hero-title">财务专员（海外）</h1>
    <p class="job-hero-company">{employer}</p>
    <div class="job-hero-cond"><span>本科及以上</span><span>佛山市</span><span>全职</span></div>
    <div class="job-hero-stat"><div>发布时间</div>
      <div class="job-hero-stat-value">2026年8月31日</div></div>
    <div class="job-desc-block"><p class="job-desc-label">岗位职责：</p>
      <div class="job-desc-text"><ol><li>负责账务处理</li><li>参与报表编制</li></ol></div></div>
    <div class="job-desc-block"><p class="job-desc-label">岗位要求：</p>
      <div class="job-desc-text"><ol><li>本科，{year} 届应届</li>
      <li>工作地点为坦桑尼亚。</li></ol></div></div>
    """


def test_roster_checks_declared_count_and_career_identity() -> None:
    rows = roster(event())
    assert [row["id"] for row in rows] == ["3231523", "3231309"]
    with pytest.raises(CrawlError):
        roster(event(count=3))
    with pytest.raises(CrawlError):
        roster(event(second_career=999999))


def test_detail_uses_actual_overseas_location_and_requires_2027_employer() -> None:
    row = roster(event())[0]
    values = detail(position(), row)
    assert values["location"] == "坦桑尼亚"
    assert values["published"] == "2026-08-31"
    assert "负责账务处理" in values["duties"]
    with pytest.raises(CrawlError):
        detail(position(employer="其他公司"), row)
    with pytest.raises(CrawlError):
        detail(position(year="2026"), row)
