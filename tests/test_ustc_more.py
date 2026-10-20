"""中国科大认证账号三种 2027 届范围凭据回放。"""

from datetime import datetime
from typing import Any, cast

import pytest

from job_crawler.adapters.chujiang_ustc import (
    API,
    ShanyingUstc2027,
    TonglingUstc2027,
    UstcCompanyCampus,
    ZhongweiUstc2027,
)
from job_crawler.models import Source
from job_crawler.transport import Session


class Replay:
    last_evidence = "company.json"

    def __init__(self, kind: type[UstcCompanyCampus], *, wrong_year: bool = False) -> None:
        self.kind = kind
        self.wrong_year = wrong_year

    async def open(self, url: str, **kwargs: object) -> None:
        assert url.endswith(self.kind.path)

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": API,
            "post_data": f"action=companyinfo&cid={self.kind.company_id}",
        }

    async def request(
        self, url: str, *, form: dict[str, str], detail: bool = False
    ) -> dict[str, Any]:
        assert url == API
        title = (
            "铜陵有色2027年校园招聘"
            if self.kind is TonglingUstc2027
            else "2027届生产运营类"
            if self.kind is ZhongweiUstc2027
            else "储备造纸工程师"
        )
        if self.wrong_year:
            title = title.replace("2027", "2026")
        if form["action"] == "companyinfo":
            return {
                "r": 0,
                "CompanyName": self.kind.employer,
                "OrgCode": self.kind.credit_code,
                "JobList": [{"ID": 7, "JobName": title, "UpdateDate": "2026-10-09", "Count": 2}],
            }
        self.last_evidence = "job-7.json"
        return {
            "r": 0,
            "ID": "7",
            "CompanyID": self.kind.company_id,
            "CompanyName": self.kind.employer,
            "JobName": title,
            "WorkKind": "全职",
            "Describe": "参与业务培养",
            "Require": "2027届毕业生，本科及以上" if not self.wrong_year else "2026届毕业生",
            "Workplace": "安徽省",
            "EducationRequired": "本科",
            "UpdateTime": "2026-10-09",
        }


@pytest.mark.parametrize("kind", [TonglingUstc2027, ZhongweiUstc2027, ShanyingUstc2027])
@pytest.mark.parametrize("wrong_year", [False, True])
async def test_ustc_tenants_only_include_current_cohort(
    kind: type[UstcCompanyCampus], wrong_year: bool
) -> None:
    replay = Replay(kind, wrong_year=wrong_year)
    adapter = kind(
        Source(
            source_id="COM9999",
            company_id="COM9999",
            company=kind.employer,
            url="https://www.job.ustc.edu.cn" + kind.path,
        ),
        cast(Session, replay),
        datetime(2026, 10, 20),
    )
    result = await adapter.collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == (0 if wrong_year else 1)
    assert result.scopes[0].skipped_out_of_scope == (1 if wrong_year else 0)
