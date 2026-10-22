"""Guard Suning's public campus catalog and detail identity."""

import pytest

from job_crawler.adapters.suning_campus import catalog, detail
from job_crawler.transport import CrawlError


def listing() -> str:
    return """<html><body>苏宁易购<form id="form"><input name="type" value="manage"></form>
    <div class="post-th"><a class="post-link" href="/rps-campus/ftl/campus/managePositionDetail.htm?poId=24809">供应链运营</a>
    <h3 class="th-2">南京市</h3><h3 class="th-3">本科及以上</h3></div>
    <div class="post-th"><a class="post-link" href="/rps-campus/ftl/campus/managePositionDetail.htm?poId=26580">平台运营</a>
    <h3 class="th-2">南京市</h3><h3 class="th-3">本科及以上</h3></div></body></html>"""


def job_detail() -> str:
    return """<html><body>苏宁易购<div class="section-title">供应链运营<input id="poType" value="6"></div>
    <table class="section-table"><tr><th>职位类别：</th><td>营销类</td><th>学历要求：</th><td>本科及以上</td>
    <th>工作性质：</th><td>全职</td></tr><tr><th>工作地点：</th><td>南京市</td></tr></table>
    <div class="section-detail clearfix"><span class="caption">岗位职责：</span><p>供应链规划</p>
    <span class="caption">任职要求：</span><p>本科以上</p></div></body></html>"""


def test_campus_catalog_has_distinct_ids_and_details() -> None:
    rows = catalog(listing())
    assert [row["id"] for row in rows] == ["24809", "26580"]
    assert detail(job_detail(), rows[0])["requirements"] == "本科以上"


def test_campus_rejects_duplicate_and_wrong_detail() -> None:
    with pytest.raises(CrawlError, match="重复"):
        catalog(listing().replace("poId=26580", "poId=24809"))
    with pytest.raises(CrawlError, match="标题不一致"):
        detail(job_detail().replace("供应链运营", "社招经理"), catalog(listing())[0])
