"""Recover individually valid responses after a stopped batch classification run."""

import argparse
import json
from pathlib import Path

from job_crawler.classification import Classifier, Decisions, job_content, validate_decisions
from job_crawler.config import load_settings
from job_crawler.models import Job
from job_crawler.storage import write_json
from job_crawler.taxonomy import load_taxonomy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(".runtime/classification"))
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument(
        "--taxonomy", type=Path, default=Path("src/job_crawler/assets/job-taxonomy.json")
    )
    args = parser.parse_args()
    tree = load_taxonomy(args.taxonomy)
    classifier = Classifier(
        load_settings(args.config),
        tree,
        args.cache,
        args.audit,
        max_calls=0,
        concurrency=1,
        batch_size=1,
    )
    # Response IDs are SHA256(identity + complete input), so changed inputs/config cannot match.
    inputs = {}
    for path in (args.snapshot / "collections").glob("*.json"):
        for raw in json.loads(path.read_text())["collection"]["jobs"]:
            content = job_content(Job.model_validate(raw))
            inputs[classifier.content_id(content)] = content
    recovered = 0
    for path in sorted(args.audit.glob("*.json")):
        raw = json.loads(path.read_text())
        if raw.get("finish_reason") != "stop" or raw.get("model") != classifier.settings.llm.model:
            continue
        try:
            items = Decisions.model_validate_json(raw["raw_output"]).items
            ids = [item.id for item in items]
            if (
                len(ids) != len(set(ids))
                or set(ids) != set(raw["ids"])
                or not set(ids) <= inputs.keys()
            ):
                continue
            for item in items:
                target = args.cache / f"{item.id}.json"
                if target.exists() or not item.primary:
                    continue
                try:
                    validate_decisions(
                        {"items": [item.model_dump()]}, {item.id: inputs[item.id]}, tree.paths()
                    )
                except ValueError:
                    continue
                write_json(
                    target,
                    {
                        "identity": classifier.identity,
                        "input": inputs[item.id],
                        "decision": item.model_dump(),
                    },
                )
                recovered += 1
        except ValueError:
            continue
    print(f"恢复 {recovered} 条通过逐岗位校验的响应；未发起模型调用")


if __name__ == "__main__":
    main()
