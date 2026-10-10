"""Extract minimal public field-shape fixtures from completed live collections."""

import argparse
import json
from pathlib import Path
from typing import Any

from job_crawler.storage import write_json

FIELDS = {
    "Id",
    "JobAdName",
    "CategoryId",
    "LocNames",
    "Org",
    "Degree",
    "DetailAddress",
    "ClassificationOne",
    "Duty",
    "Require",
    "PostDate",
    "EndTime",
}


def minimal(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[:200] if key in {"Duty", "Require"} and isinstance(value, str) else value
        for key, value in row.items()
        if key in FIELDS
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("ids", nargs="+")
    args = parser.parse_args()
    for identity in args.ids:
        root = args.root / identity
        report = json.loads((root / "report.json").read_text())
        assert report["sources"][0]["coverage"] == "complete"
        source = json.loads(next((root / "collections").glob("*.json")).read_text())["source"]
        jobs = json.loads((root / "jobs.json").read_text())
        detail = json.loads(Path(jobs[0]["evidence"][0]).read_text())
        listing = next(
            value
            for path in (root / "evidence").rglob("request-*.json")
            if ((value := json.loads(path.read_text())).get("payload") or {}).get("PageIndex") == 0
        )
        row = next(
            row for row in listing["data"]["Data"] if str(row["Id"]) == jobs[0]["source_key"]
        )
        write_json(
            Path("tests/fixtures/zhiye") / f"{identity}.json",
            {
                "note": "真实字段最小样本；正文截取200字符。回放只核验结构，不代替完整实时验收。",
                "source": source,
                "adapter": report["sources"][0]["adapter"].split("@")[0],
                "source_count": report["collected"],
                "payload": listing["payload"],
                "list_url": listing["url"],
                "detail_url": detail["url"],
                "listed": minimal(row),
                "detail": minimal(detail["data"]["Data"]),
            },
        )


if __name__ == "__main__":
    main()
