from datetime import datetime

import pytest

from job_crawler.config import MappingConfig
from job_crawler.filtering import SHANGHAI
from job_crawler.models import Job


@pytest.fixture(autouse=True)
def isolate_model_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # The suite must never spend the developer's configured production API key.
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 10, 12, tzinfo=SHANGHAI)


@pytest.fixture
def job(now: datetime) -> Job:
    return Job(
        source_id="TEST",
        source_key="1",
        company="测试公司",
        title="软件工程师",
        source_url="https://example.test/job/1",
        apply_url="https://example.test/job/1",
        education="本科",
        location="广东省/深圳市",
        category_primary="互联网/AI",
        category_secondary="软件研发",
        duties="研发业务系统",
        requirements="本科及以上",
        published="2026-10-10",
        collected_at=now,
    )


@pytest.fixture
def mapping() -> MappingConfig:
    return MappingConfig(category_paths={"互联网/AI": ["软件研发", "前端开发"]})
