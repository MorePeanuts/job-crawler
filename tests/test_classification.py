import json
from datetime import datetime
from pathlib import Path

import httpx2 as httpx
import pytest
from openai import AsyncOpenAI
from openpyxl import load_workbook

from job_crawler.classification import (
    Classifier,
    classify_snapshot,
    job_content,
    validate_decisions,
)
from job_crawler.config import Settings, load_settings
from job_crawler.models import Collection, Job, Scope, Source
from job_crawler.storage import write_json
from job_crawler.taxonomy import load_taxonomy, parse_javascript

TAXONOMY = Path("src/job_crawler/assets/job-taxonomy.json")


def test_taxonomy_configuration_matches_authoritative_resource() -> None:
    tree = load_taxonomy(TAXONOMY)
    assert tree.paths() == load_settings(Path("config.toml")).mapping.category_paths
    assert len(tree.categories) == 20
    assert sum(map(len, tree.paths().values())) == 113
    assert "软件研发" in tree.paths()["互联网/AI"]
    assert "银行及金融服务" not in tree.paths()["互联网/AI"]


def test_js_is_parsed_as_data_only() -> None:
    text = "export const JOB_POSITION_CATEGORIES = [{name:'A',groups:[{name:'B',positions:['x', 'name: foo']}]}]"
    tree = parse_javascript(text)
    assert tree.paths() == {"A": ["B"]}
    assert tree.categories[0].groups[0].positions == ["x", "name: foo"]
    with pytest.raises(ValueError):
        parse_javascript(text.replace("'x'", "someFunction()"))
    with pytest.raises(ValueError):
        parse_javascript(text + "; alert('execute')")


def decision(key: str, **overrides: object) -> dict[str, object]:
    return {
        "id": key,
        "primary": "互联网/AI",
        "secondary": "软件研发",
        "quote": "Python",
        "reason": "开发职责明确",
        **overrides,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"secondary": "银行及金融服务"},
        {"quote": "另一个岗位的引证"},
        {"primary": None},
        {"id": "other"},
    ],
)
def test_reject_invalid_paths_ids_and_cross_job_quotes(change: dict[str, object]) -> None:
    inputs = {"job": {"title": "Python 开发", "duties": "", "category_raw": "", "requirements": ""}}
    with pytest.raises(ValueError):
        validate_decisions(
            {"items": [decision("job", **change)]}, inputs, {"互联网/AI": ["软件研发"]}
        )
    with pytest.raises(ValueError):
        validate_decisions(
            {"items": [decision("job"), decision("job")]}, inputs, {"互联网/AI": ["软件研发"]}
        )


def test_unresolved_is_not_forced_into_category() -> None:
    result = validate_decisions(
        {
            "items": [
                decision(
                    "job", primary=None, secondary=None, quote=None, reason="混合岗位，职责不明"
                )
            ]
        },
        {"job": {}},
        {},
    )
    assert result[0].primary is None


async def test_valid_cache_works_without_key_and_changes_invalidate(
    tmp_path: Path, job: Job, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    settings = Settings()
    tree = load_taxonomy(TAXONOMY)
    worker = Classifier(
        settings,
        tree,
        tmp_path / "cache",
        tmp_path / "audit",
        max_calls=0,
        concurrency=1,
        batch_size=1,
    )
    job.title = "Python 开发"
    content = job_content(job)
    key = worker.content_id(content)
    write_json(
        worker.cache / f"{key}.json",
        {"identity": worker.identity, "input": content, "decision": decision(key)},
    )
    results = await worker.classify([job, job.model_copy()])
    assert len(results) == 1 and worker.cache_hits == 1 and worker.calls == 0
    job.duties += "修改后的职责"
    assert worker.content_id(job_content(job)) != key
    assert not await worker.classify([job])
    assert "LLM 调用预算耗尽" in worker.errors.values()
    settings.llm.model = "different"
    other = Classifier(
        settings, tree, worker.cache, worker.audit, max_calls=0, concurrency=1, batch_size=1
    )
    assert other.content_id(content) != key
    cached = json.loads((worker.cache / f"{key}.json").read_text())
    cached["decision"]["secondary"] = "银行及金融服务"
    write_json(worker.cache / f"{key}.json", cached)
    original = job.model_copy(update={"duties": content["duties"]})
    assert not await worker.classify([original])


async def test_truncated_response_retried_and_budget_is_bounded(
    tmp_path: Path, job: Job, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        body = json.loads(request.content)
        content = body["messages"][1]["content"]
        payload = json.loads(content[content.index("[") :])
        items = [decision(item["id"], quote=item["title"]) for item in payload]
        return httpx.Response(
            200,
            json={
                "id": "mock",
                "created": 0,
                "model": "test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "length" if attempts == 1 else "stop",
                        "message": {"role": "assistant", "content": json.dumps({"items": items})},
                    }
                ],
            },
        )

    def client(**kwargs: object) -> AsyncOpenAI:
        return AsyncOpenAI(
            api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        )

    monkeypatch.setattr("job_crawler.classification.AsyncOpenAI", client)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    worker = Classifier(
        Settings(),
        load_taxonomy(TAXONOMY),
        tmp_path / "cache",
        tmp_path / "audit",
        max_calls=2,
        concurrency=1,
        batch_size=1,
    )
    result = await worker.classify([job, job.model_copy(update={"title": "其他岗位"})])
    assert len(result) == 1 and attempts == worker.calls == 2
    assert len(worker.errors) == 1
    assert len(list(worker.cache.glob("*.json"))) == 1
    assert (worker.audit / "00001-error.json").exists()


@pytest.mark.parametrize("refine", [False, True])
async def test_classified_snapshot_roundtrip_preserves_source_and_reference_time(
    tmp_path: Path, job: Job, now: datetime, monkeypatch: pytest.MonkeyPatch, refine: bool
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    settings = load_settings(Path("config.toml"))
    tree = load_taxonomy(TAXONOMY)
    job.title = "市场营销" if refine else "Python 开发"
    job.category_primary = job.category_secondary = ""
    source = Source(source_id=job.source_id, company_id="TEST", company=job.company)
    original = tmp_path / "original"
    write_json(
        original / "manifest.json",
        {
            "run_id": "original",
            "as_of": now.isoformat(),
            "window": "all",
            "source_ids": [source.source_id],
            "bindings": {},
        },
    )
    write_json(
        original / "collections" / "source.json",
        {
            "source": source.model_dump(),
            "collection": Collection(
                jobs=[job],
                scopes=[
                    Scope(name="jobs", expected=1, listed=1, unique=1, details=1, terminal=True)
                ],
            ).model_dump(mode="json"),
        },
    )
    worker = Classifier(
        settings,
        tree,
        tmp_path / "cache",
        tmp_path / "audit",
        max_calls=0,
        concurrency=1,
        batch_size=1,
    )
    content = job_content(job)
    key = worker.content_id(content)
    write_json(
        worker.cache / f"{key}.json",
        {"identity": worker.identity, "input": content, "decision": decision(key, quote=job.title)},
    )
    if refine:
        reviewer = Classifier(
            settings,
            tree,
            worker.cache,
            worker.audit,
            max_calls=0,
            concurrency=1,
            batch_size=1,
            compact=True,
        )
        review_key = reviewer.content_id(content)
        write_json(
            reviewer.cache / f"{review_key}.json",
            {
                "identity": reviewer.identity,
                "input": content,
                "decision": decision(
                    review_key, primary="市场/广告/公关", secondary="市场/品牌推广", quote=job.title
                ),
            },
        )
    output = tmp_path / "output"
    result = await classify_snapshot(
        original, output, settings, tree, cache=worker.cache, max_calls=0, refine=refine
    )
    assert result["classification"]["classified"] == 1
    assert result["classification"]["calls"] == 0
    assert result["exported"] == 1
    manifest = json.loads((output / "result" / "manifest.json").read_text())
    assert manifest["as_of"] == now.isoformat()
    assert manifest["origins"][source.source_id]["as_of"] == now.isoformat()
    workbook = load_workbook(output / "result" / "岗位信息汇总.xlsx")
    assert workbook.worksheets[0]["D2"].value == ("市场/广告/公关" if refine else "互联网/AI")
    assert workbook.worksheets[0]["E2"].value == ("市场/品牌推广" if refine else "软件研发")
    workbook.close()
    raw_original = json.loads((original / "collections" / "source.json").read_text())
    assert raw_original["collection"]["jobs"][0]["category_primary"] == ""
