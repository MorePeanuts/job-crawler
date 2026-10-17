from datetime import datetime
from typing import Any

import pytest
from test_zhiye import Replay

from job_crawler.adapters.asus import AsusMainlandCampus
from job_crawler.models import Source


class AsusReplay(Replay):
    def __init__(self, failure: str = ""):
        super().__init__()
        self.failure = failure
        self.page = self

    async def content(self) -> str:
        if "asus.zhiye.com" not in self.opens[-1]:
            return "华硕科技（苏州）有限公司"
        body = """<footer>华硕电脑 校园招聘</footer><div class="joblist"><table class="jobsTable">
        <tr><td>职位名称</td></tr><tr><td>无任何在招职位</td></tr></table></div><div class="pager"></div>"""
        if self.failure == "identity":
            body = body.replace("华硕电脑", "未知公司")
        elif self.failure == "new_jobs":
            body = body.replace("无任何在招职位", "<a href='/job/1'>工程师</a>")
        elif self.failure == "pagination":
            body = body.replace('class="pager">', 'class="pager"><a>2</a>')
        elif self.failure == "missing_table":
            body = body.replace('class="jobsTable"', "")
        return body

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        response = await super().request(url, payload=payload, detail=detail)
        for row in response["Data"]:
            row.update(
                JobAdName=f"研发工程师{row['Id']}",
                CategoryId="2",
                Kind="全职",
                Duty="开发产品",
                Require="本科，经验为佳",
                Degree="本科",
                LocNames="苏州市",
            )
        return response


def source() -> Source:
    return Source(
        source_id="COM0154",
        company_id="COM0154",
        company="华硕电脑股份有限公司",
        url="https://asustek.zhiye.com/campus/jobs",
    )


async def test_two_portals_keep_full_nonzero_directory(now: datetime) -> None:
    replay = AsusReplay()
    result = await AsusMainlandCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == 21 and replay.pages == [0, 1] and not replay.details
    assert result.scopes[1].expected == 0 and result.scopes[1].terminal
    assert all(j.duties == "开发产品" and "经验为佳" in j.requirements for j in result.jobs)


@pytest.mark.parametrize("failure", ["identity", "new_jobs", "pagination", "missing_table"])
async def test_legacy_change_retains_rd_jobs_but_fails_coverage(
    now: datetime, failure: str
) -> None:
    result = await AsusMainlandCampus(source(), AsusReplay(failure), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 21
