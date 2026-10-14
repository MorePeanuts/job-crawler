"""Plan evidence-backed description repairs without changing a historical workbook.

uv run python scripts/repair_description_snapshot.py INPUT OUTPUT --moka-iv PUBLIC_IV
The IV is the public Moka page parameter, not an account credential. The plan
contains no encryption parameters. Apply cell patches to a copy of the workbook.
"""

import argparse
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from job_crawler.adapters.base import text
from job_crawler.adapters.moka import decode
from job_crawler.description import clean_field_headings, split_sections
from job_crawler.models import Job
from job_crawler.storage import write_json


def objects(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        result = [value]
        for child in value.values():
            result.extend(objects(child))
        # Browser-observed responses store their JSON body as a string.
        body = value.get("body")
        if isinstance(body, str):
            result.extend(objects(json.loads(body)))
        return result
    if isinstance(value, list):
        return [row for child in value for row in objects(child)]
    return []


@lru_cache(maxsize=128)
def evidence_objects(path: str, iv: str) -> list[dict[str, object]]:
    value = json.loads(Path(path).read_text())
    if isinstance(value.get("body"), str):
        value = json.loads(value["body"])
    data = value.get("data")
    if "necromancer" in value:
        data = value
    if isinstance(data, dict) and "necromancer" in data:
        if not iv:
            raise ValueError("Moka evidence requires the public page aesIv")
        value = decode(data, iv)
    return objects(value)


def raw_description(job: Job, field: str, iv: str) -> str:
    descriptions: set[str] = set()
    for path in job.evidence:
        for row in evidence_objects(path, iv):
            if field in row and any(
                str(row.get(key, "")) == job.source_key for key in ("id", "jobNumber", "jobid")
            ):
                value = row[field]
                if not isinstance(value, str):
                    raise ValueError(f"Non-text description: {job.key}")
                descriptions.add(value)
    if len(descriptions) != 1:
        raise ValueError(f"Missing/ambiguous same-ID evidence: {job.key}")
    return descriptions.pop()


def legacy_sections(body: str, adapter: str) -> tuple[str, str]:
    """Frozen v1 behavior solely to verify historical evidence-to-snapshot linkage."""
    if adapter.startswith("zhaopin-"):
        for marker in ("任职要求", "任职资格", "岗位要求", "应聘条件", "任职条件"):
            duties, found, requirements = body.partition(marker)
            if found and duties.strip() and requirements.strip():
                return duties.strip(), requirements.lstrip("：:\n ").strip()
        return body, ""
    if adapter.startswith("coapi-"):
        parts = re.split(r"(岗位职责|工作职责|职位职责|任职要求|岗位要求|任职资格)\s*[：:]?", body)
        duties = []
        requirements = []
        for label, content in zip(parts[1::2], parts[2::2], strict=True):
            (duties if label in {"岗位职责", "工作职责", "职位职责"} else requirements).append(
                content.strip(" \n：:")
            )
        pair = "\n".join(filter(None, duties)), "\n".join(filter(None, requirements))
        return pair if any(pair) else (body, "")
    if adapter == "bilibili-campus":
        match = re.search(r"(?:工作要求|岗位要求|任职要求|任职资格)\s*[:：]", body)
        if not match:
            return body, ""
        return (
            re.sub(
                r"^(?:工作职责|岗位职责|职位描述)\s*[:：]\s*", "", body[: match.start()]
            ).strip(),
            body[match.end() :].strip(),
        )
    if not adapter.startswith("moka-"):
        raise ValueError(f"Unsupported legacy adapter: {adapter}")
    duties = []
    requirements = []
    is_requirement = False
    for line in (line.strip() for line in body.splitlines()):
        label = re.sub(r"[：:\s【】]", "", line)
        label = re.sub(r"^[一二三四五六七八九十0-9]+[、.．]", "", label)
        if label in {"岗位职责", "工作职责", "职位职责", "职位描述"}:
            is_requirement = False
        elif label in {"任职要求", "岗位要求", "任职资格", "职位要求", "应聘要求", "基本要求"}:
            is_requirement = True
        elif line not in {"：", ":"}:
            (requirements if is_requirement else duties).append(line)
    return "\n".join(duties), "\n".join(requirements)


def repair(job: Job, adapter: str, iv: str) -> tuple[str, str, str]:
    field = (
        "detail"
        if adapter.startswith("zhaopin-")
        else "jobinfo"
        if adapter.startswith("coapi-")
        else "jobDescription"
        if adapter.startswith("moka-")
        else "positionDescription"
        if adapter == "bilibili-campus"
        else ""
    )
    if field and job.detail_mode != "listing_only" and (job.duties or job.requirements):
        raw = raw_description(job, field, iv)
        body = text(raw)
        # Moka v1 ran HTML text extraction twice, once in _job and once in sections.
        if adapter.startswith("moka-"):
            body = text(body)
        old = legacy_sections(body, adapter)
        if old != (job.duties, job.requirements):
            raise ValueError(f"Original parser does not reproduce snapshot: {job.key}")
        if adapter.startswith("moka-"):
            body = re.sub(r"(?m)^[ \t]*[:：][ \t]*$", "", body)
        duties, requirements = split_sections(
            body, include_preamble=not adapter.startswith("coapi-")
        )
        # A heading-only repair does not reformat otherwise unchanged paragraphs.
        if re.sub(r"\s", "", duties) == re.sub(r"\s", "", job.duties):
            duties = job.duties
        if re.sub(r"\s", "", requirements) == re.sub(r"\s", "", job.requirements):
            requirements = job.requirements
        return duties, requirements, f"same-ID evidence:{field};v1 replay matched"
    return (
        clean_field_headings(job.duties),
        clean_field_headings(job.requirements),
        "explicit line-start heading in saved structured field; ownership preserved",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--moka-iv", default="")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("Output must be a new empty directory")
    manifest = json.loads((args.input / "manifest.json").read_text())
    jobs = [Job.model_validate(row) for row in json.loads((args.input / "jobs.json").read_text())]
    delivered = [
        Job.model_validate(row) for row in json.loads((args.input / "delivered.json").read_text())
    ]
    if len({j.key for j in jobs}) != len(jobs):
        raise ValueError("Duplicate job identities")
    updates: dict[str, tuple[str, str]] = {}
    records: list[dict[str, object]] = []
    for job in jobs:
        adapter = manifest["bindings"][job.source_id]["adapter"]
        duties, requirements, reason = repair(job, adapter, args.moka_iv)
        if (duties, requirements) != (job.duties, job.requirements):
            updates[job.key] = duties, requirements
            records.append(
                {
                    "key": job.key,
                    "company": job.company,
                    "title": job.title,
                    "adapter": adapter,
                    "evidence": job.evidence,
                    "reason": reason,
                    "old": {"duties": job.duties, "requirements": job.requirements},
                    "new": {"duties": duties, "requirements": requirements},
                }
            )
    patches: list[dict[str, object]] = []
    delivered.sort(key=lambda j: (j.company, j.title, j.key))
    for row, job in enumerate(delivered, 2):
        if job.key not in updates:
            continue
        for column, field, value in zip(
            ("I", "J"), ("duties", "requirements"), updates[job.key], strict=True
        ):
            if value != getattr(job, field):
                patches.append(
                    {
                        "cell": f"{column}{row}",
                        "old": getattr(job, field),
                        "new": value,
                        "key": job.key,
                    }
                )
    selected = {j.key for j in delivered}
    counts = Counter(str(r["company"]) for r in records if r["key"] in selected)
    write_json(
        args.output / "description-repair.json",
        {
            "source": str(args.input.resolve()),
            "source_run_id": manifest["run_id"],
            "source_as_of": manifest["as_of"],
            "offline": True,
            "rows": len(delivered),
            "changed_rows": sum(counts.values()),
            "changed_cells": len(patches),
            "companies": dict(counts),
            "records": records,
        },
    )
    write_json(args.output / "cell-patches.json", patches)
    for job in delivered:
        if job.key in updates:
            job.duties, job.requirements = updates[job.key]
    write_json(args.output / "delivered.json", [j.model_dump(mode="json") for j in delivered])
    print(
        json.dumps(
            {
                "rows": len(delivered),
                "changed_rows": sum(counts.values()),
                "companies": dict(counts),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
