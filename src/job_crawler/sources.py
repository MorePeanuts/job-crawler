"""Maintain user-editable CSV without losing companies that lack an entry."""

import csv
from pathlib import Path

from job_crawler.models import Source

HEADERS = ["来源ID", "企业ID", "主体名称", "招聘官网", "备注"]


def read_sources(path: Path, *, allow_notes: bool = False) -> tuple[list[Source], list[str]]:
    sources: list[Source] = []
    issues: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"企业ID", "主体名称", "招聘官网"} <= set(reader.fieldnames or []):
            raise ValueError("来源 CSV 缺少 企业ID、主体名称、招聘官网 表头")
        for index, row in enumerate(reader, 2):
            if not any(row.values()):
                continue
            if (
                not row.get("主体名称")
                and allow_notes
                and (row.get("企业ID") or "").startswith("（注")
            ):
                issues.append(f"第 {index} 行是尾注，未作为来源导入")
                continue
            source = Source(
                source_id=row.get("来源ID") or row.get("企业ID") or "",
                company_id=row.get("企业ID") or "",
                company=row.get("主体名称") or "",
                url=row.get("招聘官网") or "",
                notes=row.get("备注") or "",
            )
            if source.source_id in seen:
                raise ValueError(f"重复来源 ID: {source.source_id}，多入口请使用独立来源ID")
            seen.add(source.source_id)
            sources.append(source)
    if not sources:
        raise ValueError("来源列表为空")
    return sources, issues


def write_sources(path: Path, sources: list[Source]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(HEADERS)
        for source in sources:
            writer.writerow(
                [source.source_id, source.company_id, source.company, source.url, source.notes]
            )
    temporary.replace(path)
