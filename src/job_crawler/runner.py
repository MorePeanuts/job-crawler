"""Programmatic run orchestration and deterministic finalization."""

import asyncio
import json
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from job_crawler import __version__
from job_crawler.adapters import REGISTRY
from job_crawler.config import Settings
from job_crawler.exporter import enums, export_workbook, import_errors, normalize, validate_mapping
from job_crawler.filtering import SHANGHAI, Window, select, window_start
from job_crawler.llm import Enricher
from job_crawler.models import Binding, Collection, Issue, Job, Source, SourceReport
from job_crawler.storage import Store, fingerprint, write_json
from job_crawler.transport import BrowserSession


def code_digest() -> str:
    root = Path(__file__).parent
    return fingerprint(
        {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*.py"))}
    )


def preflight(sources: list[Source], bindings: dict[str, Binding], settings: Settings) -> None:
    validate_mapping(settings.mapping)
    if not sources:
        raise ValueError("没有选中来源")
    if len({s.source_id for s in sources}) != len(sources):
        raise ValueError("重复来源 ID")
    for source in sources:
        binding = bindings.get(source.source_id)
        if binding:
            if binding.adapter not in REGISTRY:
                raise ValueError(f"未知适配器 {binding.adapter}")
            if REGISTRY[binding.adapter].version != binding.version:
                raise ValueError(f"适配器版本不匹配: {source.source_id}")


async def prepare_export(
    collections: dict[str, Collection],
    sources: list[Source],
    bindings: dict[str, Binding],
    settings: Settings,
    window: Window,
    as_of: datetime,
    output: Path,
) -> tuple[list[Job], list[dict[str, Any]], list[SourceReport]]:
    validate_mapping(settings.mapping)
    allowed = enums()
    valid: list[Job] = []
    review: list[dict[str, Any]] = []
    reports: list[SourceReport] = []
    enricher = Enricher(settings.llm, settings.mapping, output / "llm")
    try:
        for source in sources:
            collection = collections[source.source_id]
            binding = bindings.get(source.source_id)
            issues = collection.coverage_issues()
            report = SourceReport(
                source_id=source.source_id,
                company=source.company,
                adapter=f"{binding.adapter}@{binding.version}" if binding else "",
                scope_description=collection.scope_description,
                scopes=collection.scopes,
                collected=len(collection.jobs),
                issues=issues,
                warnings=collection.warnings,
            )
            seen: set[str] = set()
            excluded: Counter[str] = Counter()
            for original in collection.jobs:
                if original.key in seen:
                    report.issues.append(
                        Issue(
                            code="duplicate_identity",
                            message="重复岗位唯一键",
                            job_key=original.key,
                        )
                    )
                    continue
                seen.add(original.key)
                selection = select(original, window, as_of)
                if selection.kind == "exclude":
                    excluded[selection.reason] += 1
                    continue
                job = normalize(original, settings.mapping)
                if binding and binding.company_name:
                    job.company = binding.company_name
                else:
                    job.company = source.company
                problems: list[str] = []
                if selection.kind == "review":
                    problems.append(selection.reason)
                else:
                    report.selected += 1
                    # Model is called only where it can help; lack of taxonomy alone doesn't burn calls.
                    needs_education = job.education not in allowed["education"]
                    needs_category = (
                        bool(settings.mapping.category_paths) and not job.category_secondary
                    )
                    if settings.llm.enabled and (needs_education or needs_category):
                        try:
                            job = await enricher.enrich(job)
                        except Exception as exc:
                            problems.append(f"llm_error:{type(exc).__name__}")
                            report.issues.append(
                                Issue(
                                    code="llm_error",
                                    message=str(exc)
                                    if isinstance(exc, ValueError)
                                    else f"模型调用失败 ({type(exc).__name__})；检查端点、网络与密钥配置",
                                    job_key=job.key,
                                )
                            )
                problems.extend(import_errors(job, settings.mapping, allowed))
                if problems:
                    report.review += 1
                    review.append({"job": job.model_dump(mode="json"), "reasons": problems})
                else:
                    report.exported += 1
                    valid.append(job)
            report.excluded = dict(excluded)
            report.coverage = (
                "complete"
                if not issues and not any(i.code == "duplicate_identity" for i in report.issues)
                else ("partial" if collection.jobs else "blocked")
            )
            reports.append(report)
    finally:
        await enricher.close()
    return valid, review, reports


def save_results(
    output: Path,
    manifest: dict[str, Any],
    collections: dict[str, Collection],
    valid: list[Job],
    review: list[dict[str, Any]],
    reports: list[SourceReport],
) -> dict[str, Any]:
    complete = all(
        report.coverage == "complete" and report.review == 0 and not report.issues
        for report in reports
    )
    report = {
        **manifest,
        "status": "complete"
        if complete
        else "partial"
        if any(c.jobs for c in collections.values())
        else "blocked",
        "collected": sum(len(c.jobs) for c in collections.values()),
        "exported": len(valid),
        "review": len(review),
        "sources": [r.model_dump(mode="json") for r in reports],
        "finished_at": datetime.now(SHANGHAI).isoformat(),
    }
    write_json(
        output / "jobs.json",
        [
            job.model_dump(mode="json")
            for collection in collections.values()
            for job in collection.jobs
        ],
    )
    write_json(output / "review.json", review)
    write_json(output / "report.json", report)
    export_workbook(output / "jobs.xlsx", valid)
    return report


async def run(
    sources: list[Source],
    bindings: dict[str, Binding],
    settings: Settings,
    *,
    output: Path,
    window: Window = "all",
    as_of: datetime | None = None,
    resume: bool = False,
    state: Path = Path(".runtime/state.sqlite"),
) -> dict[str, Any]:
    """Collect selected sources. No network is needed until a supported adapter is entered."""
    preflight(sources, bindings, settings)
    output = await asyncio.to_thread(output.absolute)
    now = datetime.now(SHANGHAI)
    if resume:
        old = json.loads(await asyncio.to_thread((output / "manifest.json").read_text))
        saved_as_of = datetime.fromisoformat(old["as_of"])
        if as_of is not None and as_of != saved_as_of:
            raise ValueError("恢复时不能改变 as-of")
        as_of = saved_as_of
        run_id = old["run_id"]
    else:
        if await asyncio.to_thread(output.exists) and any(output.iterdir()):
            raise ValueError("输出目录非空，请使用新目录或 --resume")
        as_of = as_of or now
        run_id = uuid.uuid4().hex
    since = window_start(window, as_of)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "version": __version__,
        "code_digest": code_digest(),
        "window": window,
        "as_of": as_of.isoformat(),
        "since": since.isoformat() if since else None,
        "source_ids": [s.source_id for s in sources],
        "configuration": settings.model_dump(),
        "bindings": {
            s.source_id: bindings[s.source_id].model_dump()
            for s in sources
            if s.source_id in bindings
        },
    }
    digest = fingerprint({**manifest, "sources": [s.model_dump() for s in sources]})
    store = Store(state)
    collections: dict[str, Collection] = {}
    try:
        store.begin(run_id, digest, now, resume, settings.crawl.resume_hours)
        write_json(output / "manifest.json", manifest)
        for source in sources:
            binding = bindings.get(source.source_id)
            collection = Collection()
            if not source.url:
                collection.issues.append(
                    Issue(code="missing_entry", message="名录尚未填写招聘入口")
                )
            elif not binding or not binding.enabled:
                collection.issues.append(
                    Issue(
                        code="not_adapted" if not binding else "disabled",
                        message="来源未接入或已禁用，请按适配器开发规范接入",
                    )
                )
            else:
                print(f"采集 {source.source_id} {source.company} ({binding.adapter})", flush=True)
                try:
                    async with BrowserSession(
                        source.source_id,
                        run_id,
                        output / "evidence" / source.source_id,
                        store,
                        settings.crawl,
                        resume,
                    ) as session:
                        adapter = REGISTRY[binding.adapter](source, session, now, as_of)
                        collection = await adapter.collect()
                        collection.warnings.extend(session.navigation_warnings)
                except Exception as exc:
                    collection.issues.append(
                        Issue(
                            code="session_error", message=f"{type(exc).__name__}: {str(exc)[:600]}"
                        )
                    )
            collections[source.source_id] = collection
            store.save(collection.jobs)
            write_json(
                output / "collections" / f"{fingerprint(source.source_id)[:16]}.json",
                {"source": source.model_dump(), "collection": collection.model_dump(mode="json")},
            )
            print(
                f"  获得 {len(collection.jobs)} 条，覆盖问题 {len(collection.coverage_issues())}",
                flush=True,
            )
        valid, review, reports = await prepare_export(
            collections, sources, bindings, settings, window, as_of, output
        )
        report = save_results(output, manifest, collections, valid, review, reports)
        store.finish(run_id, report["status"])
        return report
    finally:
        store.close()


async def reexport(input_dir: Path, output: Path, settings: Settings) -> dict[str, Any]:
    """Reapply mapping to a historical run; explicitly retains original coverage/time."""
    if await asyncio.to_thread(lambda: output.exists() and any(output.iterdir())):
        raise ValueError("重新导出目录必须为空")
    manifest = json.loads(await asyncio.to_thread((input_dir / "manifest.json").read_text))
    sources = []
    collections = {}
    for path in sorted((input_dir / "collections").glob("*.json")):
        value = json.loads(await asyncio.to_thread(path.read_text))
        source = Source.model_validate(value["source"])
        sources.append(source)
        collections[source.source_id] = Collection.model_validate(value["collection"])
    if not sources or set(manifest["source_ids"]) != set(collections):
        raise ValueError("原始运行缺少来源结果；请先恢复采集")
    bindings = {key: Binding.model_validate(value) for key, value in manifest["bindings"].items()}
    valid, review, reports = await prepare_export(
        collections,
        sources,
        bindings,
        settings,
        manifest["window"],
        datetime.fromisoformat(manifest["as_of"]),
        output,
    )
    manifest["reexported_from"] = str(await asyncio.to_thread(input_dir.absolute))
    manifest["reexport_settings"] = settings.model_dump()
    write_json(output / "manifest.json", manifest)
    for source in sources:
        write_json(
            output / "collections" / f"{fingerprint(source.source_id)[:16]}.json",
            {
                "source": source.model_dump(),
                "collection": collections[source.source_id].model_dump(mode="json"),
            },
        )
    return save_results(output, manifest, collections, valid, review, reports)
