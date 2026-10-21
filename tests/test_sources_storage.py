from datetime import datetime, timedelta
from pathlib import Path

import pytest

from job_crawler.models import Job, Source
from job_crawler.sources import read_sources, write_sources
from job_crawler.storage import Store, redact


def test_initial_inventory() -> None:
    sources, issues = read_sources(Path("sites/sources.csv"))
    assert len(sources) >= 807
    assert sum(bool(s.url) for s in sources) >= 237
    unicorn = [source for source in sources if "SPEC-275" in source.notes]
    assert len(unicorn) == 307
    assert unicorn[0].source_id == "COM0501" and unicorn[0].company == "字节跳动"
    assert unicorn[-1].source_id == "COM0807" and unicorn[-1].company == "玻色量子"
    assert sum(bool(source.url) for source in unicorn) >= 100
    assert issues == []


def test_roundtrip_and_duplicate_sources(tmp_path: Path) -> None:
    path = tmp_path / "sources.csv"
    sources = [
        Source(source_id="A", company_id="CO1", company="公司", url=""),
        Source(source_id="A-campus", company_id="CO1", company="公司", url="https://example.test"),
    ]
    write_sources(path, sources)
    assert read_sources(path)[0] == sources
    write_sources(path, sources + [sources[0]])
    with pytest.raises(ValueError, match="重复"):
        read_sources(path)


def test_only_recognized_footer_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "in.csv"
    path.write_text("企业ID,主体名称,招聘官网\nA,公司,\n（注：来源说明）\n", encoding="utf-8")
    sources, issues = read_sources(path, allow_notes=True)
    assert len(sources) == 1 and len(issues) == 1
    with pytest.raises(ValueError):
        read_sources(path)
    with pytest.raises(ValueError):
        Source(source_id="../escape", company_id="A", company="公司")


def test_resume_checks_fingerprint_and_age(tmp_path: Path, now: datetime, job: Job) -> None:
    store = Store(tmp_path / "state.db")
    try:
        store.begin("run", "hash1", now, False, 6)
        store.begin("run", "hash1", now + timedelta(hours=1), True, 6)
        for digest, clock in [("hash2", now), ("hash1", now + timedelta(hours=7))]:
            with pytest.raises(ValueError):
                store.begin("run", digest, clock, True, 6)
        store.request("run", "A", "req", "done", "/some/evidence.json")
        assert store.cached("run", "A", "req") == "/some/evidence.json"
        assert store.cached("other", "A", "req") is None
        store.save([job])
        original = job.collected_at
        job.collected_at += timedelta(hours=1)
        store.save([job])
        assert store.db.execute("select first_seen,last_seen from records").fetchone() == (
            original.isoformat(),
            job.collected_at.isoformat(),
        )
    finally:
        store.close()


def test_credentials_redacted() -> None:
    value = redact(
        {
            "token": "secret",
            "cookie": "secret",
            "url": "https://example.test?access_token=secret&id=1",
        }
    )
    assert "secret" not in str(value)
    assert "id=1" in value["url"]
    assert "secret" not in str(redact({"body": '{"access_token":"secret","id":1}'}))
