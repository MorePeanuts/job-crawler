import json
import subprocess
import sys
from pathlib import Path

from job_crawler.models import Job
from job_crawler.storage import write_json


def test_evidence_audit_matches_job_identity_and_excludes_company_address(
    tmp_path: Path, job: Job
) -> None:
    job.source_key = "batch:correct"
    evidence = tmp_path / "evidence.json"
    write_json(
        evidence,
        {
            "data": {
                "post": [
                    {"id": "other", "DetailAddress": "别人的地址"},
                    {"id": "correct", "DetailAddress": None, "education": "本科"},
                ],
                "company": {"unitAddress": "总部地址"},
            },
        },
    )
    job.evidence = [str(evidence)]
    unmatched = job.model_copy(update={"source_key": "batch:missing"})
    write_json(tmp_path / "jobs.json", [j.model_dump(mode="json") for j in [job, unmatched]])
    write_json(
        tmp_path / "field-audit.json",
        {
            "records": [{"key": j.key} for j in [job, unmatched]],
        },
    )
    subprocess.run(
        [sys.executable, "scripts/audit_saved_fields.py", str(tmp_path)],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
    )
    result = json.loads((tmp_path / "saved-evidence-field-audit.json").read_text())
    assert result["statuses"] == {"matched": 1, "unmatched": 1}
    assert result["records"][0]["job_fields"] == [{"DetailAddress": None, "education": "本科"}]
    assert result["records"][1]["job_fields"] == []
