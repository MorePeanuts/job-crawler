"""Combine chosen collection snapshots without revisiting recruitment websites."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from job_crawler.config import Settings
from job_crawler.exporter import export_workbook
from job_crawler.filtering import SHANGHAI, Window
from job_crawler.models import Binding, Collection, Job, Source
from job_crawler.runner import prepare_export, save_results
from job_crawler.storage import fingerprint, write_json


async def bundle(
    inputs: list[Path], output: Path, settings: Settings, *, as_of: datetime | None = None
) -> dict[str, Any]:
    """Inputs may be entire runs or individual collections/*.json files."""
    if await asyncio.to_thread(lambda: output.exists() and any(output.iterdir())):
        raise ValueError("汇总输出目录必须为空")
    sources: list[Source] = []
    collections: dict[str, Collection] = {}
    bindings: dict[str, Binding] = {}
    origins: dict[str, Any] = {}
    window: Window | None = None
    window_as_of: datetime | None = None
    for item in inputs:
        is_file = await asyncio.to_thread(item.is_file)
        root = item.parent.parent if is_file else item
        manifest = json.loads(await asyncio.to_thread((root / "manifest.json").read_text))
        current_window = manifest.get("window", "all")
        if current_window not in {"all", "day", "week", "month"}:
            raise ValueError("输入快照的时间窗口无效")
        if window is not None and window != current_window:
            raise ValueError("不能混合不同时间窗口的快照")
        window = current_window
        if window != "all":
            current_as_of = datetime.fromisoformat(manifest["as_of"])
            if window_as_of is not None and window_as_of != current_as_of:
                raise ValueError("窗口快照必须使用相同的筛选时刻")
            window_as_of = current_as_of
        paths = [item] if is_file else sorted((root / "collections").glob("*.json"))
        if not paths:
            raise ValueError(f"没有已保存的来源结果: {item}")
        loaded: set[str] = set()
        for path in paths:
            value = json.loads(await asyncio.to_thread(path.read_text))
            source = Source.model_validate(value["source"])
            if source.source_id in collections:
                raise ValueError(f"来源重复，请明确选择一轮结果: {source.source_id}")
            if source.source_id not in manifest["source_ids"]:
                raise ValueError("来源不属于原始运行清单")
            collection = Collection.model_validate(value["collection"])
            if any(j.source_id != source.source_id for j in collection.jobs):
                raise ValueError("岗位来源与采集文件不一致")
            loaded.add(source.source_id)
            sources.append(source)
            collections[source.source_id] = collection
            if source.source_id in manifest["bindings"]:
                bindings[source.source_id] = Binding.model_validate(
                    manifest["bindings"][source.source_id]
                )
            origins[source.source_id] = {
                "input": str(await asyncio.to_thread(path.absolute)),
                "run_id": manifest["run_id"],
                "as_of": manifest["as_of"],
                "code_digest": manifest.get("code_digest"),
            }
            if source.source_id in manifest.get("origins", {}):
                origins[source.source_id] = {
                    **manifest["origins"][source.source_id],
                    "bundled_input": str(await asyncio.to_thread(path.absolute)),
                }
        if not is_file and loaded != set(manifest["source_ids"]):
            raise ValueError(f"运行缺少来源文件: {item}；可明确选择已完成的单个来源文件")
    if not sources:
        raise ValueError("没有输入来源")
    if window_as_of is not None and as_of is not None and as_of != window_as_of:
        raise ValueError("不能改变窗口快照的筛选时刻；请重新采集")
    as_of = window_as_of or as_of or datetime.now(SHANGHAI)
    assert window is not None
    valid, review, reports = await prepare_export(
        collections, sources, bindings, settings, window, as_of, output
    )
    manifest = {
        "run_id": f"bundle-{fingerprint(origins)[:16]}",
        "window": window,
        "as_of": as_of.isoformat(),
        "source_ids": [s.source_id for s in sources],
        "bindings": {k: v.model_dump() for k, v in bindings.items()},
        "origins": origins,
        "configuration": settings.model_dump(),
        "snapshot_notice": "离线汇总开发期间采集快照；各来源采集时间见 origins，未重新访问确认在线状态。",
    }
    write_json(output / "manifest.json", manifest)
    for source in sources:
        write_json(
            output / "collections" / f"{fingerprint(source.source_id)[:16]}.json",
            {
                "source": source.model_dump(),
                "collection": collections[source.source_id].model_dump(mode="json"),
            },
        )
    report = save_results(output, manifest, collections, valid, review, reports)
    information = sorted(
        [*valid, *(Job.model_validate(item["job"]) for item in review)],
        key=lambda job: (job.company, job.title, job.key),
    )
    source_lookup = {source.source_id: source for source in sources}
    source_rows: list[list[str | int]] = [
        [
            r.company,
            source_lookup[r.source_id].url,
            origins[r.source_id]["as_of"],
            r.coverage,
            r.collected,
            sum(r.excluded.values()),
            r.exported + r.review,
            r.review,
        ]
        for r in reports
    ]
    export_workbook(
        output / "岗位信息汇总.xlsx", information, information=True, source_rows=source_rows
    )
    report["information_rows"] = len(information)
    report["information_notice"] = (
        "信息汇总含待补全/待核验岗位，非可直接导入表；严格导入表为 jobs.xlsx。"
    )
    write_json(output / "report.json", report)
    return report
