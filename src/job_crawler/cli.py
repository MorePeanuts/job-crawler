"""Small CLI; exit codes distinguish delivery failures from configuration errors."""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from job_crawler.config import load_bindings, load_settings
from job_crawler.filtering import SHANGHAI
from job_crawler.models import Source
from job_crawler.runner import preflight, reexport, run
from job_crawler.sources import read_sources, write_sources


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="job-crawler")
    commands = result.add_subparsers(dest="command", required=True)
    sources = commands.add_parser("sources", help="维护来源清单")
    actions = sources.add_subparsers(dest="action", required=True)
    for name in ("list", "import", "add"):
        action = actions.add_parser(name)
        action.add_argument("--file", type=Path, default=Path("sites/sources.csv"))
        if name == "list":
            action.add_argument("--bindings", type=Path, default=Path("sites/bindings.toml"))
            action.add_argument("--status", choices=["supported", "pending", "missing", "disabled"])
        elif name == "import":
            action.add_argument("input", type=Path)
            action.add_argument("--replace", action="store_true", help="明确替换已存在清单")
        else:
            action.add_argument("--id", required=True)
            action.add_argument("--company-id", required=True)
            action.add_argument("--company", required=True)
            action.add_argument("--url", required=True)
            action.add_argument("--notes", default="")
    for name in ("run", "check"):
        action = commands.add_parser(name)
        action.add_argument("--sources", type=Path, default=Path("sites/sources.csv"))
        action.add_argument("--bindings", type=Path, default=Path("sites/bindings.toml"))
        action.add_argument("--config", type=Path, default=Path("config.toml"))
        action.add_argument(
            "--source", action="append", help="按来源 ID 选择，可重复；默认全部已启用绑定"
        )
        action.add_argument(
            "--all-sources", action="store_true", help="包括未接入来源，逐一报告障碍"
        )
        if name == "run":
            action.add_argument("--window", choices=["all", "day", "week", "month"], default="all")
            action.add_argument("--as-of", help="ISO 时间，必须含时区")
            action.add_argument("--output", type=Path)
            action.add_argument("--state", type=Path, default=Path(".runtime/state.sqlite"))
            action.add_argument("--resume", action="store_true")
    action = commands.add_parser("export", help="修改映射后从历史采集结果重新导出，不访问网站")
    action.add_argument("input", type=Path)
    action.add_argument("--output", type=Path, required=True)
    action.add_argument("--config", type=Path, default=Path("config.toml"))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "sources":
            if args.action == "import":
                if args.file.exists() and not args.replace:
                    raise ValueError("目标清单已存在；要替换请显式使用 --replace")
                sources, notes = read_sources(args.input, allow_notes=True)
                write_sources(args.file, sources)
                print(
                    json.dumps(
                        {
                            "companies": len({s.company_id for s in sources}),
                            "sources": len(sources),
                            "with_url": sum(bool(s.url) for s in sources),
                            "notes": notes,
                        },
                        ensure_ascii=False,
                    )
                )
            elif args.action == "add":
                sources, _ = read_sources(args.file)
                if args.id in {s.source_id for s in sources}:
                    raise ValueError("来源 ID 已存在，请编辑已有行或使用新 ID")
                sources.append(
                    Source(
                        source_id=args.id,
                        company_id=args.company_id,
                        company=args.company,
                        url=args.url,
                        notes=args.notes,
                    )
                )
                write_sources(args.file, sources)
                print(f"已添加 {args.id}；适配器尚需单独接入")
            else:
                sources, _ = read_sources(args.file)
                bindings = load_bindings(args.bindings)
                for source in sources:
                    binding = bindings.get(source.source_id)
                    status = (
                        "missing"
                        if not source.url
                        else "pending"
                        if not binding
                        else "supported"
                        if binding.enabled
                        else "disabled"
                    )
                    if not args.status or status == args.status:
                        print(f"{source.source_id}\t{status}\t{source.company}\t{source.url}")
            return 0
        settings = load_settings(args.config)
        if args.command == "export":
            report = asyncio.run(reexport(args.input, args.output, settings))
        else:
            sources, _ = read_sources(args.sources)
            bindings = load_bindings(args.bindings)
            if args.source and args.all_sources:
                raise ValueError("--source 与 --all-sources 不能同时使用")
            if args.source:
                unknown = set(args.source) - {s.source_id for s in sources}
                if unknown:
                    raise ValueError(f"来源 ID 不存在: {sorted(unknown)}")
                sources = [s for s in sources if s.source_id in args.source]
            elif not args.all_sources:
                sources = [
                    s for s in sources if s.source_id in bindings and bindings[s.source_id].enabled
                ]
            preflight(sources, bindings, settings)
            if args.command == "check":
                print(f"配置检查通过；选中 {len(sources)} 个来源（不代表网络验收通过）")
                return 0
            if args.resume and not args.output:
                raise ValueError("--resume 需要 --output 指定原运行目录")
            output = args.output or Path("outputs") / datetime.now(SHANGHAI).strftime(
                "%Y%m%d-%H%M%S-%f"
            )
            report = asyncio.run(
                run(
                    sources,
                    bindings,
                    settings,
                    output=output,
                    window=args.window,
                    as_of=datetime.fromisoformat(args.as_of) if args.as_of else None,
                    resume=args.resume,
                    state=args.state,
                )
            )
        print(
            json.dumps(
                {key: report[key] for key in ("status", "collected", "exported", "review")},
                ensure_ascii=False,
            )
        )
        return 0 if report["status"] == "complete" else 2
    except ValidationError as exc:
        # Pydantic's default text includes the input value, which could be a pasted credential.
        errors = exc.errors(include_input=False, include_context=False, include_url=False)
        print(f"配置/输入错误: {json.dumps(errors, ensure_ascii=False)}", file=sys.stderr)
        return 1
    except (ValueError, OSError, KeyError) as exc:
        print(f"配置/输入错误: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断。已完成来源和请求检查点保留，可使用同目录 --resume。", file=sys.stderr)
        return 130
