from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from job_crawler.bundle import bundle
from job_crawler.config import Settings
from job_crawler.models import Collection, Job, Scope, Source
from job_crawler.storage import write_json


def snapshot(path: Path, job: Job, now: datetime) -> Path:
    source = Source(source_id=job.source_id, company_id=job.company, company=job.company)
    write_json(
        path / "manifest.json",
        {
            "run_id": path.name,
            "as_of": now.isoformat(),
            "source_ids": [source.source_id],
            "bindings": {},
        },
    )
    item = path / "collections" / "source.json"
    write_json(
        item,
        {
            "source": source.model_dump(),
            "collection": Collection(
                jobs=[job],
                scopes=[
                    Scope(
                        name="jobs",
                        expected=1,
                        listed=1,
                        unique=1,
                        details=1,
                        terminal=True,
                    )
                ],
            ).model_dump(mode="json"),
        },
    )
    return item


async def test_merge_preserves_times_and_exports_review_rows(
    tmp_path: Path,
    job: Job,
    now: datetime,
) -> None:
    original_time = job.collected_at
    first = snapshot(tmp_path / "first", job, now)
    other = job.model_copy(update={"source_id": "OTHER", "deadline": "2000-01-01"})
    snapshot(tmp_path / "second", other, now)
    result = await bundle([first, tmp_path / "second"], tmp_path / "bundle", Settings())
    assert result["information_rows"] == 1 and result["review"] == 1
    assert len(result["sources"]) == 2
    assert result["sources"][1]["excluded"] == {"expired": 1}
    assert result["origins"][job.source_id]["as_of"] == now.isoformat()
    assert job.collected_at == original_time
    workbook = load_workbook(tmp_path / "bundle" / "岗位信息汇总.xlsx")
    assert workbook["岗位信息（待补全）"].max_row == 2
    assert workbook["岗位信息（待补全）"].max_column == 11
    assert workbook["企业采集情况"].max_row == 3
    assert workbook["企业采集情况"].cell(3, 7).value == 0
    workbook.close()
    chained = await bundle([tmp_path / "bundle"], tmp_path / "chained", Settings())
    assert chained["origins"][job.source_id]["as_of"] == now.isoformat()
    assert chained["information_rows"] == 1


async def test_merge_rejects_duplicate_source_and_incomplete_run(
    tmp_path: Path,
    job: Job,
    now: datetime,
) -> None:
    snapshot(tmp_path / "first", job, now)
    snapshot(tmp_path / "second", job, now)
    with pytest.raises(ValueError, match="来源重复"):
        await bundle([tmp_path / "first", tmp_path / "second"], tmp_path / "output", Settings())
    write_json(
        tmp_path / "first" / "manifest.json",
        {
            "run_id": "first",
            "as_of": now.isoformat(),
            "source_ids": [job.source_id, "MISSING"],
            "bindings": {},
        },
    )
    with pytest.raises(ValueError, match="缺少来源"):
        await bundle([tmp_path / "first"], tmp_path / "output", Settings())
