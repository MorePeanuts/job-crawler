import json
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from job_crawler.config import MappingConfig, Settings
from job_crawler.models import Collection, Issue, Job, Scope, Source
from job_crawler.runner import prepare_export, reexport, run, save_results


def complete(jobs: list[Job]) -> Collection:
    n = len(jobs)
    return Collection(
        jobs=jobs,
        scopes=[Scope(name="test", expected=n, listed=n, unique=n, details=n, terminal=True)],
    )


async def test_one_failure_never_hides_another_source(
    tmp_path: Path, now: datetime, job: Job, mapping: MappingConfig
) -> None:
    source = Source(source_id="TEST", company_id="A", company="后台精确公司名")
    other = Source(source_id="FAIL", company_id="B", company="受阻公司")
    collections = {
        "TEST": complete([job]),
        "FAIL": Collection(issues=[Issue(code="access_denied", message="403")]),
    }
    valid, review, reports = await prepare_export(
        collections, [source, other], {}, Settings(mapping=mapping), "all", now, tmp_path
    )
    assert len(valid) == 1 and valid[0].company == source.company and not review
    assert [r.coverage for r in reports] == ["complete", "blocked"]
    saved = save_results(tmp_path, {"run_id": "unit-test"}, collections, valid, review, reports)
    assert saved["status"] == "partial"


async def test_capture_complete_is_not_import_complete(
    tmp_path: Path, now: datetime, job: Job
) -> None:
    source = Source(source_id="TEST", company_id="A", company="公司")
    valid, review, reports = await prepare_export(
        {"TEST": complete([job])}, [source], {}, Settings(), "all", now, tmp_path
    )
    assert not valid and len(review) == 1
    assert reports[0].coverage == "complete"
    assert reports[0].review == 1


async def test_excel_limit_preserves_full_text_and_other_rows(
    tmp_path: Path, now: datetime, job: Job, mapping: MappingConfig
) -> None:
    oversized = job.model_copy(deep=True)
    oversized.source_key = "long"
    oversized.duties = "岗位职责" * 9000
    oversized.requirements += "\x1e岗位要求"
    collections = {"TEST": complete([job, oversized])}
    source = Source(source_id="TEST", company_id="A", company="公司")
    settings = Settings(mapping=mapping)
    settings.llm.enabled = False
    valid, review, reports = await prepare_export(
        collections, [source], {}, settings, "all", now, tmp_path
    )
    assert len(valid) == len(review) == 1
    saved = save_results(tmp_path, {}, collections, valid, review, reports)
    assert saved["information_overflow_fields"] == 2
    overflow = json.loads((tmp_path / "excel-overflow.json").read_text())
    assert overflow == [
        {"job_key": oversized.key, "field": "duties", "value": oversized.duties},
        {"job_key": oversized.key, "field": "requirements", "value": oversized.requirements},
    ]
    workbook = load_workbook(tmp_path / "岗位信息汇总.xlsx", read_only=True)
    rows = list(workbook.worksheets[0].values)
    assert len(rows) == 3
    assert any("excel-overflow.json" in str(row[8]) for row in rows[1:])
    workbook.close()


async def test_recovered_navigation_warning_kept_without_false_coverage_failure(
    tmp_path: Path, now: datetime, job: Job, mapping: MappingConfig
) -> None:
    source = Source(source_id="TEST", company_id="A", company="公司")
    collection = complete([job])
    collection.warnings.append(Issue(code="navigation_recovered", message="HTTP 412 + valid API"))
    valid, review, reports = await prepare_export(
        {"TEST": collection}, [source], {}, Settings(mapping=mapping), "all", now, tmp_path
    )
    saved = save_results(tmp_path, {}, {"TEST": collection}, valid, review, reports)
    assert saved["status"] == "complete"
    assert saved["sources"][0]["warnings"][0]["code"] == "navigation_recovered"


async def test_filter_before_import_validation(tmp_path: Path, now: datetime, job: Job) -> None:
    job.deadline = "2026-10-09"
    source = Source(source_id="TEST", company_id="A", company="公司")
    valid, review, reports = await prepare_export(
        {"TEST": complete([job])}, [source], {}, Settings(), "all", now, tmp_path
    )
    assert not valid and not review
    assert reports[0].excluded == {"expired": 1}


async def test_field_audit_preserves_source_and_explains_normalized_rows(
    tmp_path: Path, now: datetime, job: Job
) -> None:
    job.education = ""
    job.requirements = "本科、硕士、博士学历，计算机专业。"
    job.address = ""
    source = Source(source_id="TEST", company_id="A", company="公司")
    collections = {"TEST": complete([job])}
    valid, review, reports = await prepare_export(
        collections, [source], {}, Settings(), "all", now, tmp_path
    )
    save_results(tmp_path, {}, collections, valid, review, reports)
    raw = json.loads((tmp_path / "jobs.json").read_text())
    audit = json.loads((tmp_path / "field-audit.json").read_text())
    assert raw[0]["education"] == ""
    assert audit["summary"]["education"]["after_nonempty"] == 1
    fields = audit["records"][0]["fields"]
    assert fields["education"]["value"] == "本科"
    assert "本科、硕士、博士学历" in fields["education"]["provenance"]
    assert fields["address"]["status"] == "no_job_address_in_saved_fields"


async def test_empty_but_verified_directory(tmp_path: Path, now: datetime) -> None:
    source = Source(source_id="TEST", company_id="A", company="公司")
    collections = {"TEST": complete([])}
    valid, review, reports = await prepare_export(
        collections, [source], {}, Settings(), "all", now, tmp_path
    )
    assert save_results(tmp_path, {}, collections, valid, review, reports)["status"] == "complete"


async def test_unknown_source_run_and_reexport(tmp_path: Path) -> None:
    source = Source(source_id="NEW", company_id="A", company="新公司", url="https://example.test")
    output = tmp_path / "run"
    report = await run([source], {}, Settings(), output=output, state=tmp_path / "state.db")
    assert report["status"] == "blocked"
    assert (output / "jobs.xlsx").exists()
    exported = await reexport(output, tmp_path / "exported", Settings())
    assert exported["as_of"] == report["as_of"]
    assert exported["status"] == "blocked"
    chained = await reexport(tmp_path / "exported", tmp_path / "reexported-again", Settings())
    assert chained["as_of"] == report["as_of"]
    resumed = await run(
        [source], {}, Settings(), output=output, resume=True, state=tmp_path / "state.db"
    )
    assert resumed["run_id"] == report["run_id"]
    changed = Settings()
    changed.crawl.delay = 5
    with pytest.raises(ValueError, match="变化"):
        await run([source], {}, changed, output=output, resume=True, state=tmp_path / "state.db")
    with pytest.raises(ValueError, match="非空"):
        await run([source], {}, Settings(), output=output, state=tmp_path / "state.db")
