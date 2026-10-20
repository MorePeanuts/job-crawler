"""青山高校八岗目录仅纳入 2027 届展位核对的三岗。"""

from datetime import datetime
from typing import Any, cast

from job_crawler.adapters.chujiang_ustc import API, QingshanUstc2027
from job_crawler.models import Source
from job_crawler.transport import Session

TITLES = [
    "机械管培生",
    "采购助理",
    "电气管培生",
    "选矿管培生",
    "储备干部",
    "安环管培生",
    "冶金管培生",
    "会计",
]


class Replay:
    last_evidence = "company.json"

    def __init__(self, *, wrong_company: bool = False) -> None:
        self.wrong_company = wrong_company
        self.details: list[str] = []

    async def open(self, url: str, **kwargs: object) -> None:
        assert url.endswith("/Jobinformation/info.aspx?itemid=29423")

    async def observed(self, needle: str) -> dict[str, Any]:
        return {"url": API, "post_data": "action=companyinfo&cid=29423"}

    async def request(
        self, url: str, *, form: dict[str, str], detail: bool = False
    ) -> dict[str, Any]:
        assert url == API
        if form["action"] == "companyinfo":
            return {
                "r": 0,
                "CompanyName": "青山控股集团有限公司",
                "OrgCode": "91330300751176226P",
                "JobList": [
                    {"ID": index, "JobName": title, "UpdateDate": "2026-09-04", "Count": 1}
                    for index, title in enumerate(TITLES, start=1)
                ],
            }
        key = form["jid"]
        self.details.append(key)
        self.last_evidence = f"job-{key}.json"
        return {
            "r": 0,
            "ID": key,
            "CompanyID": "99999" if self.wrong_company and key == "1" else "29423",
            "CompanyName": "青山控股集团有限公司",
            "JobName": TITLES[int(key) - 1],
            "WorkKind": "全职",
            "Describe": "参加生产经营培养",
            "Require": "具备1年以上电气相关岗位工作经验" if key == "3" else "本科及以上",
            "Workplace": "印度尼西亚",
            "EducationRequired": "本科",
            "UpdateTime": "2026-09-04",
        }


def adapter(replay: Replay) -> QingshanUstc2027:
    return QingshanUstc2027(
        Source(
            source_id="COM0064",
            company_id="COM0064",
            company="青山控股集团有限公司",
            url="https://www.job.ustc.edu.cn/Jobinformation/info.aspx?itemid=29423",
        ),
        cast(Session, replay),
        datetime(2026, 10, 20),
    )


async def test_qingshan_eight_details_three_current_cohort_jobs() -> None:
    replay = Replay()
    result = await adapter(replay).collect()
    assert replay.details == [str(i) for i in range(1, 9)]
    assert not result.coverage_issues()
    assert result.scopes[0].expected == 8
    assert result.scopes[0].skipped_out_of_scope == 5
    assert {job.title for job in result.jobs} == {"机械管培生", "冶金管培生", "会计"}


async def test_qingshan_wrong_account_detail_is_partial() -> None:
    result = await adapter(Replay(wrong_company=True)).collect()
    assert result.coverage_issues()
    assert {job.title for job in result.jobs} == {"冶金管培生", "会计"}
