"""Audit field-bearing objects in saved evidence, without network or model calls.

uv run python scripts/audit_saved_fields.py OUTPUT_DIRECTORY
"""

import argparse
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from job_crawler.models import Job
from job_crawler.storage import write_json

FIELD = re.compile(r"address|location|workplace|workcity|locnames|degree|education", re.I)


def matching_objects(value: object, identity: str) -> list[dict[str, object]]:
    """Only inspect the object matching this job, never a neighboring job or company."""
    matches: list[dict[str, object]] = []
    if isinstance(value, dict):
        if any(str(value.get(key, "")) == identity for key in ("id", "Id", "idPosition")):
            matches.append(value)
        for child in value.values():
            matches.extend(matching_objects(child, identity))
    elif isinstance(value, list):
        for child in value:
            matches.extend(matching_objects(child, identity))
    return matches


@lru_cache(maxsize=128)
def load(path: str) -> object:
    return json.loads(Path(path).read_text())


def audit(job: Job) -> dict[str, object]:
    objects: list[dict[str, object]] = []
    errors: list[str] = []
    for path in job.evidence:
        try:
            data = load(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{type(exc).__name__}:{path}")
            continue
        objects.extend(matching_objects(data, job.source_key.rsplit(":", 1)[-1]))
    return {
        "key": job.key,
        "evidence": job.evidence,
        "status": "matched" if objects else "unmatched",
        "errors": errors,
        "job_fields": [{k: v for k, v in obj.items() if FIELD.search(k)} for obj in objects],
        "normalized": {"education": job.education, "address": job.address},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    # field-audit includes both strict import rows and rows awaiting completion.
    fields = json.loads((args.directory / "field-audit.json").read_text())
    selected = {row["key"] for row in fields["records"]}
    jobs = [Job.model_validate(j) for j in json.loads((args.directory / "jobs.json").read_text())]
    records = [audit(job) for job in jobs if job.key in selected]
    result = {
        "scope": "只检查现有岗位证据中的同 ID 对象。平安/阿里证据为列表接口；不声称检查了未抓取的详情页。单位联系地址不属于岗位对象，不据此填写工作地址。",
        "statuses": dict(Counter(str(row["status"]) for row in records)),
        "records": records,
    }
    write_json(args.directory / "saved-evidence-field-audit.json", result)
    print(json.dumps(result["statuses"], ensure_ascii=False))


if __name__ == "__main__":
    main()
