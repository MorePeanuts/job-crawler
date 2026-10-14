"""Exercise the project's skill helper against real offline bundle exports."""

import asyncio
import json
import runpy
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from test_bundle import snapshot

from job_crawler.bundle import bundle
from job_crawler.config import Settings
from job_crawler.models import Job
from job_crawler.storage import write_json

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".agents/skills/add-recruitment-adapters/scripts/audit_delivery.py"
)
audit = runpy.run_path(str(SCRIPT))["audit"]


def settings() -> Settings:
    value = Settings()
    value.llm.enabled = False
    return value


async def test_review_rows_are_valid_delivery(tmp_path: Path, job: Job, now: datetime) -> None:
    source = snapshot(tmp_path / "input", job, now)
    root = tmp_path / "bundle"
    await bundle([source], root, settings(), as_of=now)
    result = audit(root, 1)
    assert result["ok"] and result["companies_with_jobs"] == 1
    assert result["selected"] == result["information_rows"] == result["review"] == 1
    assert result["exported"] == 0
    output = tmp_path / "audit.json"
    process = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            str(SCRIPT),
            str(root),
            "--expected-companies",
            "1",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0
    assert json.loads(output.read_text())["ok"]


async def test_two_sources_of_one_company_do_not_count_twice(
    tmp_path: Path, job: Job, now: datetime
) -> None:
    first = snapshot(tmp_path / "one", job, now)
    second = snapshot(tmp_path / "two", job.model_copy(update={"source_id": "OTHER"}), now)
    root = tmp_path / "bundle"
    await bundle([first, second], root, settings(), as_of=now)
    result = audit(root, 2)
    assert not result["ok"]
    assert result["companies_with_jobs"] == 1 and result["information_rows"] == 2


async def test_expired_only_company_is_not_counted(tmp_path: Path, job: Job, now: datetime) -> None:
    source = snapshot(tmp_path / "input", job.model_copy(update={"deadline": "2000-01-01"}), now)
    root = tmp_path / "bundle"
    await bundle([source], root, settings(), as_of=now)
    result = audit(root, 1)
    assert not result["ok"] and result["companies_with_jobs"] == 0


async def test_partial_source_invalidates_company(tmp_path: Path, job: Job, now: datetime) -> None:
    first = snapshot(tmp_path / "one", job, now)
    second = snapshot(tmp_path / "two", job.model_copy(update={"source_id": "OTHER"}), now)
    raw = json.loads(second.read_text())
    raw["collection"]["scopes"][0]["terminal"] = False
    write_json(second, raw)
    root = tmp_path / "bundle"
    await bundle([first, second], root, settings(), as_of=now)
    result = audit(root, 1)
    assert not result["ok"] and result["companies_with_jobs"] == 0
    assert any("覆盖" in error for error in result["errors"])


async def test_missing_workbook_row_and_duplicate_report_are_rejected(
    tmp_path: Path, job: Job, now: datetime
) -> None:
    source = snapshot(tmp_path / "input", job, now)
    root = tmp_path / "bundle"
    await bundle([source], root, settings(), as_of=now)
    path = root / "岗位信息汇总.xlsx"
    book = load_workbook(path)
    book.worksheets[0].delete_rows(2)
    book.save(path)
    book.close()
    assert not audit(root, 1)["ok"]
    report = json.loads((root / "report.json").read_text())
    report["sources"].append(report["sources"][0])
    write_json(root / "report.json", report)
    assert any("来源重复" in error for error in audit(root, 1)["errors"])
