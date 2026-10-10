"""No secrets in configuration files; keys are looked up only at call time."""

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from job_crawler.models import Binding, Model


class LLMConfig(Model):
    enabled: bool = False
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    max_calls: int = Field(default=20, ge=0)
    timeout: float = Field(default=60, gt=0)
    max_tokens: int = Field(default=1500, ge=100)
    extra_body: dict[str, Any] = Field(default_factory=dict)


class CrawlConfig(Model):
    max_seconds: float = Field(default=3600, gt=0)
    timeout: float = Field(default=60, gt=0)
    max_requests: int = Field(default=20000, ge=1)
    navigation_timeout: float = Field(default=180, gt=0)
    delay: float = Field(default=0.3, ge=0)
    retries: int = Field(default=2, ge=0, le=5)
    chrome_channel: str = "chrome"
    resume_hours: float = Field(default=6, gt=0, le=24)


class MappingConfig(Model):
    education_policy: Literal["minimum_eligible", "explicit_only"] = "minimum_eligible"
    category_paths: dict[str, list[str]] = Field(default_factory=dict)
    # Exact source category -> explicit template pair, never title guessing.
    categories: dict[str, list[str]] = Field(default_factory=dict)
    education: dict[str, str] = Field(default_factory=dict)
    locations: dict[str, str] = Field(default_factory=dict)
    use_source_url_as_apply_url: bool = True


class Settings(Model):
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    mapping: MappingConfig = Field(default_factory=MappingConfig)


def load_settings(path: Path | None = None) -> Settings:
    if path is None:
        return Settings()
    return Settings.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def load_bindings(path: Path) -> dict[str, Binding]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if set(raw) - {"sources"}:
        raise ValueError("bindings only accepts [sources.<source_id>]")
    return {key: Binding.model_validate(value) for key, value in raw.get("sources", {}).items()}
