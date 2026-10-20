"""楚江高校账号的目录身份与逐岗关联回放。"""

from datetime import datetime
from typing import Any, cast

from job_crawler.adapters.chujiang_ustc import API, ChujiangUstcCampus
from job_crawler.models import Source
from job_crawler.transport import Session


class Replay:
    last_evidence = "company.json"

    def __init__(self, *, duplicate: bool = False, wrong_company: bool = False) -> None:
        self.duplicate = duplicate
        self.wrong_company = wrong_company
        self.details: list[str] = []

    async def open(self, url: str, **kwargs: object) -> None:
        assert url.endswith("/Jobinformation/info.aspx?itemid=26568")

    async def observed(self, needle: str) -> dict[str, Any]:
        return {"url": API, "post_data": "action=companyinfo&cid=26568"}

    async def request(
        self, url: str, *, form: dict[str, str], detail: bool = False
    ) -> dict[str, Any]:
        assert url == API
        if form["action"] == "companyinfo":
            return {
                "r": 0,
                "CompanyName": "安徽楚江科技新材料股份有限公司",
                "OrgCode": "91340200743082289Q",
                "Profile": "本次招聘岗位均为总裁直培生",
                "JobList": [
                    {
                        "ID": 101 if self.duplicate else i,
                        "JobName": f"管培生{i}",
                        "UpdateDate": "2026-10-06T00:00:00+08:00",
                        "Count": 2,
                    }
                    for i in (101, 102)
                ],
            }
        key = form["jid"]
        self.details.append(key)
        self.last_evidence = f"detail-{key}.json"
        return {
            "r": 0,
            "ID": key,
            "CompanyID": "99999" if self.wrong_company and key == "102" else "26568",
            "CompanyName": "安徽楚江科技新材料股份有限公司",
            "JobName": f"管培生{key}",
            "WorkKind": "全职",
            "Describe": "参加企业培养计划",
            "Require": "本科及以上",
            "Workplace": "芜湖市",
            "EducationRequired": "本科",
            "UpdateTime": "2026-10-06",
        }


def adapter(replay: Replay) -> ChujiangUstcCampus:
    return ChujiangUstcCampus(
        Source(
            source_id="COM0281",
            company_id="COM0281",
            company="安徽楚江科技新材料股份有限公司",
            url="https://www.job.ustc.edu.cn/Jobinformation/info.aspx?itemid=26568",
        ),
        cast(Session, replay),
        datetime(2026, 10, 20),
    )


async def test_chujiang_complete_account_and_detail_identity() -> None:
    replay = Replay()
    result = await adapter(replay).collect()
    assert replay.details == ["101", "102"]
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 2
    assert [job.source_key for job in result.jobs] == ["101", "102"]
    assert all(job.published == "2026-10-06" and not job.deadline for job in result.jobs)


async def test_chujiang_duplicate_listing_fails_closed() -> None:
    result = await adapter(Replay(duplicate=True)).collect()
    assert result.coverage_issues()
    assert not result.jobs


async def test_chujiang_detail_mismatch_keeps_other_job_partial() -> None:
    result = await adapter(Replay(wrong_company=True)).collect()
    assert result.coverage_issues()
    assert [job.source_key for job in result.jobs] == ["101"]
