from datetime import datetime

import pytest

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.jointown import PROJECTS, Campus, Trainee, merge_job, validate_projects
from job_crawler.models import Job, Scope, Source


def test_official_project_navigation() -> None:
    html = "九州通医药集团股份有限公司" + "".join(
        f'<a title="{name}" href="https://app.mokahr.com/campus-recruitment/jointown/{site}?hash=%23%2Fjobs"></a>'
        for site, name in PROJECTS.items()
    )
    validate_projects(html)
    with pytest.raises(Exception, match="新增或缺失"):
        validate_projects(html.replace("141506", "123456"))
    with pytest.raises(Exception, match="组织/域名"):
        validate_projects(html.replace("/jointown/", "/other/"))


def job(now: datetime, site: int) -> Job:
    return Job(
        source_id="COM0161",
        source_key="uuid",
        company="九州通医药集团股份有限公司",
        title="财务管培生",
        source_url=f"https://app.mokahr.com/campus-recruitment/jointown/{site}#/job/uuid",
        batch=PROJECTS[site],
        duties="负责财务管理",
        requirements="2027届本科以上",
        collected_at=now,
        evidence=[str(site)],
    )


def test_same_global_id_merges_projects_without_duplicating(now: datetime) -> None:
    first, second = job(now, 145419), job(now, 141506)
    merge_job(first, second)
    assert first.batch == "星辰校招生、星九管培生" and first.evidence == ["145419", "141506"]
    assert first.source_key == "uuid"


@pytest.mark.parametrize(
    "field,value", [("duties", "不同职责"), ("published", "2026-10-01"), ("work_type", "实习")]
)
def test_same_id_conflicting_content_fails(now: datetime, field: str, value: str) -> None:
    first, second = job(now, 145419), job(now, 141506)
    second = second.model_copy(update={field: value})
    with pytest.raises(Exception, match="业务字段冲突"):
        merge_job(first, second)


def test_incremental_fingerprint_separates_sites(
    monkeypatch: pytest.MonkeyPatch, now: datetime
) -> None:
    records = []

    def capture(
        self: Adapter,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> None:
        records.append((entity, listing, evidence))

    monkeypatch.setattr(Adapter, "before_detail", capture)
    src = Source(
        source_id="COM0161", company_id="COM0161", company="九州通", url="https://app.mokahr.com/"
    )
    # Base hook is replaced; neither adapter reads a transport for this test.
    for cls in (Campus, Trainee):
        instance = cls.__new__(cls)
        instance.source = src
        instance.collected_at = now
        instance.before_detail("job:uuid", {"id": "uuid"}, Scope(name="campus"), evidence="catalog")
    assert records[0][0] == records[1][0] == "job:uuid"
    assert records[0][1] != records[1][1] and records[0][2] == records[1][2] == "catalog"
