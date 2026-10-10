import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from job_crawler.config import LLMConfig, MappingConfig
from job_crawler.llm import Enricher
from job_crawler.models import Job


class FakeClient:
    def __init__(self, answer: dict[str, Any], finish: str = "stop"):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.answer = answer
        self.finish = finish
        self.options: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.options = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason=self.finish,
                    message=SimpleNamespace(content=json.dumps(self.answer)),
                )
            ],
            usage=None,
        )


async def test_disabled_llm_needs_no_secret(tmp_path: Path, job: Job) -> None:
    enricher = Enricher(LLMConfig(), MappingConfig(), tmp_path)
    assert await enricher.enrich(job) == job
    assert enricher.calls == 0


async def test_custom_model_env_and_evidence(
    tmp_path: Path, job: Job, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUSTOM_TEST_KEY", "test-secret")
    enricher = Enricher(
        LLMConfig(enabled=True, model="custom", api_key_env="CUSTOM_TEST_KEY", max_calls=1),
        MappingConfig(),
        tmp_path,
    )
    client = FakeClient(
        {
            "education": {"value": "本科", "quote": "本科及以上"},
            "category": {"primary": None, "secondary": None, "quote": None},
        }
    )
    monkeypatch.setattr(enricher, "client", client)
    result = await enricher.enrich(job)
    assert result.education == "本科"
    assert client.options["model"] == "custom"
    assert "test-secret" not in (tmp_path / "00001.json").read_text()
    with pytest.raises(ValueError, match="预算"):
        await enricher.enrich(job)


@pytest.mark.parametrize(
    ("answer", "finish"),
    [
        ({"education": {"value": "博士", "quote": "并不存在的引证"}}, "stop"),
        ({"education": {"value": "本科", "quote": ""}}, "stop"),
        (
            {"category": {"primary": "互联网/AI", "secondary": "软件研发", "quote": "软件工程师"}},
            "stop",
        ),
        ({}, "length"),
    ],
)
async def test_rejects_unfounded_or_truncated_output(
    tmp_path: Path, job: Job, answer: dict[str, Any], finish: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    enricher = Enricher(LLMConfig(enabled=True), MappingConfig(), tmp_path)
    monkeypatch.setattr(enricher, "client", FakeClient(answer, finish))
    with pytest.raises(ValueError):
        await enricher.enrich(job)
