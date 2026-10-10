"""Safely import the user-supplied JS taxonomy and regenerate its TOML section."""

import argparse
import json
import re
from pathlib import Path

from job_crawler.config import MappingConfig
from job_crawler.exporter import validate_mapping
from job_crawler.storage import write_json
from job_crawler.taxonomy import parse_javascript


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument(
        "--output", type=Path, default=Path("src/job_crawler/assets/job-taxonomy.json")
    )
    args = parser.parse_args()
    tree = parse_javascript(args.input.read_text(encoding="utf-8"))
    validate_mapping(MappingConfig(category_paths=tree.paths()))
    config = args.config.read_text(encoding="utf-8")
    config = re.sub(
        r"(?ms)^(?:# Generated from job-position.js; edit by scripts/import_taxonomy.py\.\n)?\[mapping.category_paths\]\n.*?(?=^\[|\Z)",
        "",
        config,
    )
    section = "\n# Generated from job-position.js; edit by scripts/import_taxonomy.py.\n"
    section += "[mapping.category_paths]\n"
    for primary, children in tree.paths().items():
        section += json.dumps(primary, ensure_ascii=False) + " = "
        section += json.dumps(children, ensure_ascii=False) + "\n"
    write_json(args.output, tree.model_dump())
    args.config.write_text(config.rstrip() + "\n" + section, encoding="utf-8")
    print(f"一级分类 {len(tree.categories)}；二级路径 {sum(map(len, tree.paths().values()))}")


if __name__ == "__main__":
    main()
