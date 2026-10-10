"""Cache-first enrichment of selected normalized jobs before final export."""

from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from job_crawler.classification import classify_jobs
from job_crawler.config import MappingConfig, Settings
from job_crawler.exporter import enums
from job_crawler.llm import Enricher
from job_crawler.models import Job
from job_crawler.storage import fingerprint, write_json
from job_crawler.taxonomy import Category, Group, Taxonomy, load_taxonomy


def configured_taxonomy(settings: Settings) -> Taxonomy:
    tree = load_taxonomy(Path(str(files("job_crawler").joinpath("assets/job-taxonomy.json"))))
    if tree.paths() == settings.mapping.category_paths:
        return tree
    return Taxonomy(
        source="mapping.category_paths",
        sha256=fingerprint(settings.mapping.category_paths),
        categories=[
            Category(name=primary, groups=[Group(name=name, positions=[]) for name in children])
            for primary, children in settings.mapping.category_paths.items()
        ],
    )


async def enrich_delivery(
    jobs: list[Job], settings: Settings, output: Path, as_of: datetime
) -> dict[str, list[str]]:
    """Mutate only selected copies, preserving original source snapshots."""
    config = settings.llm
    errors: dict[str, list[str]] = {}
    summary: dict[str, Any] = {
        "enabled": config.enabled,
        "model": config.model,
        "max_calls": config.max_calls,
        "calls": 0,
        "cache_hits": 0,
    }
    if not config.enabled:
        write_json(output / "enrichment-report.json", summary)
        return errors
    paths = settings.mapping.category_paths
    candidates = [j for j in jobs if j.category_secondary not in paths.get(j.category_primary, [])]
    if candidates and paths:
        classification = await classify_jobs(
            candidates,
            settings,
            configured_taxonomy(settings),
            output,
            cache=Path(config.cache_dir),
            as_of=as_of,
            max_calls=config.max_calls,
            concurrency=config.concurrency,
            batch_size=config.batch_size,
            refine=config.refine,
        )
        write_json(output / "classification-report.json", classification)
        summary["classification"] = {k: v for k, v in classification.items() if k != "items"}
        summary["calls"] = classification["calls"]
        summary["cache_hits"] = classification["cache_hits"]
        for item in classification["items"]:
            decision = item["decision"]
            if not decision or not decision["primary"]:
                errors.setdefault(item["job"], []).append(
                    "classification_unresolved:" + (item["error"] or decision["reason"])
                )
    # Category inference has its own batched cache. This stage can change education only.
    education_config = config.model_copy(update={"max_calls": config.max_calls - summary["calls"]})
    worker = Enricher(
        education_config,
        MappingConfig(education_policy=settings.mapping.education_policy),
        output / "education-audit",
        education_only=True,
        cache=Path(config.education_cache_dir),
    )
    allowed = enums()["education"]
    try:
        for job in jobs:
            if job.education in allowed:
                continue
            try:
                result = await worker.enrich(job)
                job.education = result.education
                job.field_sources.update(result.field_sources)
            except Exception as exc:
                # Do not persist API exceptions that could contain credentials or request bodies.
                reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                errors.setdefault(job.key, []).append(f"education_llm_error:{reason}")
    finally:
        await worker.close()
    summary["education"] = {"calls": worker.calls, "cache_hits": worker.cache_hits}
    summary["calls"] += worker.calls
    summary["cache_hits"] += worker.cache_hits
    summary["errors"] = errors
    write_json(output / "enrichment-report.json", summary)
    return errors
