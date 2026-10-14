"""Replay the observed CMBC campus organization and paginated detail contract."""

from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.cmbc import CmbcCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "cmbc.json"

    def __init__(self, fault: str = ""):
        self.fault = fault
        self.pages: list[int] = []
        self.details: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://career.cmbc.com.cn/#/app/recruitmentlist/campus/"
        assert ready_endpoints == ("/portal/rest/careerrecruitment/search.view",)

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/careerrecruitment/search.view"
        return {
            "url": "https://career.cmbc.com.cn/portal/rest/careerrecruitment/search.view?random=1"
        }

    def row(self, number: int) -> dict[str, str]:
        return {
            "id": f"job-{number}",
            "careerRecruitment_career_name": f"校园岗{number}",
            "careerRecruitment_career_enterprise_name": "民生理财" if number == 21 else "北京分行",
            "careerRecruitment_regions_name": "北京",
            "careerRecruitment_career_publishDate": "2026-09-03 12:00:00",
            "careerRecruitment_career_expirationDate": "2026-10-25",
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert payload is None
        if "enterpriseList.view" in url:
            return {
                "success": True,
                "data": {
                    "total": 21,
                    "enterprises": [
                        {
                            "id": "0103",
                            "name": "北京分行",
                            "total": 20,
                            "parentId": "default-enterprise",
                        },
                        {
                            "id": "0200",
                            "name": "民生理财",
                            "total": 1,
                            "parentId": "default-enterprise",
                        },
                    ],
                },
            }
        if "search.view" in url:
            assert form is not None and form["searchRecruitmentIds"] == "campus"
            assert form["searchEnterpriseId"] == ""
            page = int(form["pageNo"])
            self.pages.append(page)
            rows = [self.row(i) for i in range(1, 21)] if page == 1 else [self.row(21)]
            if page == 2 and self.fault == "duplicate":
                rows = [self.row(20)]
            if page == 2 and self.fault == "unknown_unit":
                rows[0]["careerRecruitment_career_enterprise_name"] = "未知公司"
            return {
                "success": True,
                "data": {
                    "totalLine": 21,
                    "pageCount": 2,
                    "pageNo": page,
                    "pageSize": 20,
                    "items": rows,
                },
            }
        assert detail
        key = urlsplit(url).path.rsplit("/", 1)[-1].removesuffix(".view")
        assert parse_qs(urlsplit(url).query)["recruitmentId"] == [key]
        self.details.append(key)
        if self.fault == "detail_failure" and key == "job-3":
            raise RuntimeError("detail unavailable")
        row = self.row(int(key.removeprefix("job-")))
        if self.fault == "identity" and key == "job-3":
            row["id"] = "wrong"
        row["careerRecruitment_career_careerDetail_content"] = "<p>培养一线业务能力</p>"
        row["careerRecruitment_career_careerDetail_qualifications"] = "<p>本科及以上</p>"
        return {"success": True, "data": row}


def source() -> Source:
    return Source(
        source_id="COM0108",
        company_id="COM0108",
        company="中国民生银行股份有限公司",
        url="https://career.cmbc.com.cn/#/app/recruitmentlist/campus/",
    )


async def test_cmbc_full_pages_and_other_entity_boundary(now: datetime) -> None:
    replay = Replay()
    result = await CmbcCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [1, 2]
    assert len(replay.details) == 20
    assert len(result.jobs) == 20
    assert result.scopes[0].skipped_out_of_scope == 1
    assert result.jobs[0].published == "2026-09-03 12:00:00"
    assert result.jobs[0].duties == "培养一线业务能力"


async def test_cmbc_invalid_pages_units_or_details_are_partial(now: datetime) -> None:
    for fault in ("duplicate", "unknown_unit", "detail_failure", "identity"):
        result = await CmbcCampus(source(), Replay(fault), now).collect()
        assert result.coverage_issues(), fault
