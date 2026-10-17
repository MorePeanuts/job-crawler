from datetime import datetime
from types import SimpleNamespace
from typing import cast

import pytest

from job_crawler.adapters.sihc import (
    COMPANY,
    COMPANY_NAME,
    Catalog,
    Detail,
    Record,
    SihcCampus,
    validate_catalog,
    validate_detail,
)
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session


def record(**changes: str) -> Record:
    return Record.model_validate(
        {
            "recruitId": "job-1",
            "companyId": COMPANY,
            "CR_COMPANY_ID": "subsidiary",
            "jobTitle": "入站博士后",
            "displayName": "深圳市高新投集团有限公司",
            "jobType": "01",
            "jobTypeDsc": "全职",
            "pubState": 1,
            "requireEduDsc": "博士研究生",
            "workCityDsc": "福田区",
            "address": "时代科技大厦",
            "endDate": "2026-12-07 00:00:00",
            "lastUpdateDt": "2026-09-07 09:11:07",
            **changes,
        }
    )


def catalog() -> Catalog:
    return Catalog.model_validate(
        {
            "companyId": COMPANY,
            "companyName": COMPANY_NAME,
            "page": {"pageIndex": 1, "pageSize": 12, "total": 1},
            "rows": [record()],
            "visibleIds": ["job-1"],
            "terminal": True,
        }
    )


def test_catalog_count_identity_and_terminal() -> None:
    data = catalog()
    validate_catalog(data, 1, None)
    data.page.total = 2
    with pytest.raises(Exception, match="条数"):
        validate_catalog(data, 1, None)


@pytest.mark.parametrize("change", ["company", "dom", "terminal", "duplicate", "total", "page"])
def test_catalog_rejects_changed_scope(change: str) -> None:
    data = catalog()
    total = None
    if change == "company":
        data.rows[0].companyId = "other"
    elif change == "dom":
        data.visibleIds = ["other"]
    elif change == "terminal":
        data.terminal = False
    elif change == "duplicate":
        data.rows *= 2
        data.visibleIds *= 2
        data.page.total = 2
    elif change == "total":
        total = 10
    else:
        data.page.pageIndex = 2
    with pytest.raises(CrawlError):
        validate_catalog(data, 1, total)


def test_detail_matches_actual_subsidiary_not_group_id() -> None:
    listing = record()
    row = record(companyId="subsidiary", recruitType="2")
    data = Detail(row=row, title=row.jobTitle, unit=row.displayName)
    validate_detail(data, listing)
    row.companyId = COMPANY
    with pytest.raises(Exception, match="单位ID"):
        validate_detail(data, listing)


@pytest.mark.parametrize(
    "field", ["recruitId", "jobTitle", "displayName", "recruitType", "jobType", "pubState"]
)
def test_detail_rejects_mismatch_or_unknown_enum(field: str) -> None:
    row = record(companyId="subsidiary", recruitType="2")
    data = Detail(row=row, title=row.jobTitle, unit=row.displayName)
    setattr(row, field, "changed")
    with pytest.raises(CrawlError):
        validate_detail(data, record())


def test_job_uses_body_requirements_and_never_update_as_publish(now: datetime) -> None:
    adapter = SihcCampus.__new__(SihcCampus)
    adapter.session = cast(Session, SimpleNamespace(last_evidence="fixture"))
    adapter.source = Source(
        source_id="COM0101",
        company_id="COM0101",
        company=COMPANY_NAME,
        url="https://jyjpc.iucai.com.cn/",
    )
    adapter.collected_at = now
    row = record(
        companyId="subsidiary",
        recruitType="2",
        jobResp="岗位职责：\n开展产业研究。\n应聘要求：\n博士毕业，专业相关。",
        jobReq="无",
    )
    job = adapter.make_job(row)
    assert job.duties == "开展产业研究。"
    assert "博士毕业" in job.requirements and "无" not in job.requirements
    assert job.published == "" and job.deadline == "2026-12-07 00:00:00"
    assert job.address == "福田区时代科技大厦" and job.company == COMPANY_NAME
    assert job.unit == "深圳市高新投集团有限公司"


def test_missing_body_is_not_invented(now: datetime) -> None:
    adapter = SihcCampus.__new__(SihcCampus)
    adapter.session = cast(Session, SimpleNamespace(last_evidence="fixture"))
    adapter.source = Source(
        source_id="COM0101",
        company_id="COM0101",
        company=COMPANY_NAME,
        url="https://jyjpc.iucai.com.cn/",
    )
    adapter.collected_at = now
    job = adapter.make_job(record())
    assert job.duties == job.requirements == job.published == ""
