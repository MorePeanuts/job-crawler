import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters import REGISTRY
from job_crawler.models import Source


class Recorded:
    last_evidence = "public-field-fixture"

    def __init__(self, data: dict[str, Any]):
        self.data = data

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert urlsplit(url).hostname == urlsplit(self.data["source"]["url"]).hostname

    async def observed(self, needle: str) -> dict[str, Any]:
        if "Info" in needle:
            return {"url": self.data["detail_url"]}
        return {"url": self.data["list_url"], "post_data": json.dumps(self.data["payload"])}

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        if payload is not None:
            assert payload["PageIndex"] == 0
            return {"Code": 200, "Count": 1, "Data": [self.data["listed"]]}
        assert parse_qs(urlsplit(url).query)["jobAdId"] == [self.data["detail"]["Id"]]
        return {"Code": 200, "Data": self.data["detail"]}


@pytest.mark.parametrize(
    "fixture", sorted(Path("tests/fixtures/zhiye").glob("*.json")), ids=lambda p: p.stem
)
async def test_live_tenant_field_shapes(fixture: Path, now: datetime) -> None:
    data = json.loads(await asyncio.to_thread(fixture.read_text))
    adapter = REGISTRY[data["adapter"]]
    collection = await adapter(Source.model_validate(data["source"]), Recorded(data), now).collect()
    assert not collection.coverage_issues()
    assert len(collection.jobs) == 1
    assert collection.jobs[0].source_key == data["detail"]["Id"]
    assert collection.jobs[0].title == data["detail"]["JobAdName"]
