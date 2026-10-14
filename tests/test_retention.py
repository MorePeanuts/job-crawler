"""Offline storage lifecycle: never hit a recruitment site or a model."""

import hashlib
import json
import os
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from job_crawler import retention
from job_crawler.cli import main
from job_crawler.config import IncrementalConfig
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Collection, Job, Scope
from job_crawler.storage import Store, write_json


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_run(name: str = "one", source: str = "TEST") -> Path:
    root = Path("outputs") / name
    write_json(
        root / "manifest.json",
        {"as_of": "2026-10-13T23:00:00+08:00", "window": "all", "source_ids": [source]},
    )
    write_json(root / "evidence/one.json", {"data": [1, 2], "html": "<p>example</p>"})
    (root / "jobs.xlsx").write_bytes(b"strict workbook test fixture")
    (root / "岗位信息汇总.xlsx").write_bytes(b"information workbook test fixture")
    return root


def test_archive_publish_restore_and_evidence(workspace: Path) -> None:
    root = make_run()
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    evidence = str(root / "evidence/one.json")
    archived = retention.archive_run(root, publish=True, label="50家")
    assert not root.exists()
    assert retention.evidence_exists(evidence)
    assert json.loads(retention.read_evidence(evidence))["data"] == [1, 2]
    assert all("/2026-10-13/" in p for p in archived.published)
    assert all(Path(p).suffix == ".xlsx" for p in Path("outputs").rglob("*") if p.is_file())
    target = Path(".runtime/restored")
    retention.restore(root, target)
    assert {
        p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()
    } == before
    with pytest.raises(ValueError, match="不存在"):
        retention.restore(root, target)
    with pytest.raises(ValueError, match="覆盖"):
        retention.archive_run(make_run("two"), publish=True, label="50家")


def test_hash_failure_preserves_originals(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_run()
    monkeypatch.setattr(retention, "digest", lambda p: "wrong")
    with pytest.raises(ValueError, match="校验失败"):
        retention.archive_run(root)
    assert (root / "evidence/one.json").exists()
    assert not retention.index().archives


def test_archive_rejects_symlinks_and_parent(workspace: Path) -> None:
    root = make_run()
    (root / "link").symlink_to(workspace / "outputs")
    with pytest.raises(ValueError, match="符号链接"):
        retention.archive_run(root)
    with pytest.raises(ValueError, match="子目录"):
        retention.archive_run(Path("outputs"))


def test_zip_traversal_and_corruption_rejected(workspace: Path) -> None:
    root = make_run()
    archived = retention.archive_run(root)
    packed = Path(archived.path)
    with zipfile.ZipFile(packed, "w") as saved:
        saved.writestr("../escape.txt", "bad")
    with pytest.raises(ValueError, match="校验失败"):
        retention.restore(root, Path("restore"))
    saved_index = retention.index()
    saved_index.archives[archived.root].sha256 = hashlib.sha256(packed.read_bytes()).hexdigest()
    write_json(retention.INDEX, saved_index.model_dump())
    with pytest.raises(ValueError, match="不安全"):
        retention.restore(root, Path("restore"))
    assert not Path("escape.txt").exists()


def test_daily_reuse_survives_archive(workspace: Path, job: Job, now: datetime) -> None:
    root = make_run()
    job.evidence = [str((root / "evidence/one.json").absolute())]
    store = Store(Path(".runtime/state.sqlite"))
    baseline = IncrementalSource(store, "test", "all", now, now, IncrementalConfig())
    baseline.remember("job:1", {"id": 1}, [job])
    baseline.finish(
        Collection(
            jobs=[job],
            scopes=[Scope(name="jobs", expected=1, listed=1, unique=1, details=1, terminal=True)],
        )
    )
    retention.archive_run(root)
    ctx = IncrementalSource(
        store, "test", "day", now + timedelta(days=1), now + timedelta(days=1), IncrementalConfig()
    )
    resolved = ctx.before_detail("job:1", {"id": 1}, Scope(name="jobs"), "")
    assert resolved and resolved[0].detail_mode == "cached"
    assert resolved[0].collected_at == job.collected_at
    store.close()


def test_retention_preview_protection_and_cache_limit(workspace: Path) -> None:
    old = retention.archive_run(make_run("old"))
    referenced = retention.archive_run(make_run("referenced"))
    pinned = retention.archive_run(make_run("pinned"), pin=True)
    latest = retention.archive_run(make_run("latest"))
    saved = retention.index()
    for archive in saved.archives.values():
        archive.created -= 100 * 86400
    write_json(retention.INDEX, saved.model_dump())
    store = Store(Path(".runtime/custom.sqlite"))
    store.save_history("test", json.dumps({"evidence": referenced.root + "/evidence/one.json"}))
    store.close()
    cache = Path(".runtime/classification/old.json")
    write_json(cache, {"cached": True})
    old_time = time.time() - 100 * 86400
    os.utime(cache, (old_time, old_time))
    report = retention.maintenance()
    assert report["archives"] == [old.path]
    assert cache.exists() and Path(old.path).exists()
    retention.maintenance(apply=True)
    assert not cache.exists() and not Path(old.path).exists()
    assert all(Path(a.path).exists() for a in [referenced, pinned, latest])
    assert not retention.evidence_exists(str(Path(old.root) / "evidence/one.json"))


def test_missing_registered_state_stops_cleanup(workspace: Path) -> None:
    retention.register_state(Path("somewhere/state.db"))
    with pytest.raises(ValueError, match="数据库缺失"):
        retention.maintenance(apply=True)


def test_default_cli_delivers_date_files(workspace: Path) -> None:
    write_json(Path("unused.json"), {})
    Path("sites").mkdir()
    Path("sites/sources.csv").write_text(
        "企业ID,主体名称,招聘官网\nTEST,测试,https://example.test\n"
    )
    Path("sites/bindings.toml").write_text("")
    Path("config.toml").write_text("[llm]\nenabled=false\n")
    assert main(["run", "--source", "TEST"]) == 2
    saved = retention.index()
    assert len(saved.archives) == 1
    archived = next(iter(saved.archives.values()))
    assert len(archived.published) == 2
    assert not Path(archived.root).exists()
    assert Path(".runtime/state.sqlite").exists()
    assert main(["run", "--source", "TEST", "--output", archived.root]) == 1
    assert not Path(archived.root).exists()
    restored = Path(".runtime/restored")
    retention.restore(Path(archived.root), restored)
    assert main(["export", str(restored), "--output", "outputs/reexported"]) == 2
    assert Path("outputs/reexported/岗位信息汇总.xlsx").is_file()


def test_cache_capacity_uses_oldest_and_preserves_state(workspace: Path) -> None:
    folder = Path(".runtime/classification")
    folder.mkdir(parents=True)
    old = folder / "old.json"
    new = folder / "new.json"
    old.write_bytes(b"x" * 700_000)
    new.write_bytes(b"y" * 700_000)
    stamp = time.time() - 60
    os.utime(old, (stamp, stamp))
    store = Store(Path(".runtime/state.sqlite"))
    store.close()
    retention.maintenance(apply=True, cache_mb=1)
    assert not old.exists() and new.exists()
    assert Path(".runtime/state.sqlite").exists()


def test_corrupt_archive_is_not_valid_evidence(workspace: Path) -> None:
    root = make_run()
    archive = retention.archive_run(root)
    path = Path(archive.path)
    with path.open("ab") as stream:
        stream.write(b"modified after verification")
    assert not retention.evidence_exists(str(root / "evidence/one.json"))


def test_publish_never_deletes_its_destination(workspace: Path) -> None:
    root = make_run("2026-10-13")
    with pytest.raises(ValueError, match="待删除"):
        retention.archive_run(root, publish=True)
    assert (root / "岗位信息汇总.xlsx").is_file()
