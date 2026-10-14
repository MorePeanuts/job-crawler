"""Verified compressed archives; original evidence references remain readable."""

import fcntl
import hashlib
import json
import shutil
import sqlite3
import time
import zipfile
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache, wraps
from pathlib import Path

from pydantic import Field

from job_crawler.filtering import SHANGHAI
from job_crawler.models import Model
from job_crawler.storage import write_json

INDEX = Path(".runtime/archive-index.json")


def locked[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        with INDEX.with_suffix(".lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            return function(*args, **kwargs)

    return wrapped


class Archive(Model):
    root: str
    path: str
    created: float
    pinned: bool = False
    original_bytes: int
    archive_bytes: int
    sha256: str
    published: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    window: str = "all"
    observed_at: float = 0.0


class ArchiveIndex(Model):
    archives: dict[str, Archive] = Field(default_factory=dict)
    state_paths: list[str] = Field(default_factory=list)


def index() -> ArchiveIndex:
    return ArchiveIndex.model_validate_json(INDEX.read_text()) if INDEX.exists() else ArchiveIndex()


@locked
def register_state(path: Path) -> None:
    saved = index()
    absolute = str(path.resolve())
    if absolute not in saved.state_paths:
        saved.state_paths.append(absolute)
        write_json(INDEX, saved.model_dump())


@lru_cache(maxsize=1)
def _cached_index(path: str, modified: int) -> ArchiveIndex:
    return ArchiveIndex.model_validate_json(Path(path).read_text())


@lru_cache(maxsize=512)
def _members(path: str, modified: int, expected: str) -> frozenset[str]:
    if digest(Path(path)) != expected:
        raise ValueError("归档校验失败")
    with zipfile.ZipFile(path) as saved:
        return frozenset(saved.namelist())


def archived_member(path: Path) -> tuple[Path, str] | None:
    if not INDEX.exists():
        return None
    saved = _cached_index(str(INDEX.resolve()), INDEX.stat().st_mtime_ns)
    absolute = path.absolute()
    for parent in absolute.parents:
        archive = saved.archives.get(str(parent))
        if archive:
            packed = Path(archive.path)
            member = absolute.relative_to(parent).as_posix()
            if packed.is_file() and member in _members(
                str(packed), packed.stat().st_mtime_ns, archive.sha256
            ):
                return packed, member
    return None


def evidence_exists(path: str) -> bool:
    try:
        return Path(path).is_file() or archived_member(Path(path)) is not None
    except (OSError, ValueError, zipfile.BadZipFile):
        return False


def read_evidence(path: str) -> str:
    if Path(path).is_file():
        return Path(path).read_text(encoding="utf-8")
    location = archived_member(Path(path))
    if location is None:
        raise FileNotFoundError(path)
    packed, member = location
    with zipfile.ZipFile(packed) as saved:
        return saved.read(member).decode("utf-8")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@locked
def archive_run(
    root: Path, *, publish: bool = False, label: str | None = None, pin: bool = False
) -> Archive:
    """Only use on an idle directory. Keep originals until verification and indexing finish."""
    if root.is_symlink():
        raise ValueError("归档目录不能是符号链接")
    root = root.resolve()
    allowed = [Path("outputs").resolve(), Path(".runtime/runs").resolve()]
    if not any(root.is_relative_to(base) and root != base for base in allowed):
        raise ValueError("只能归档 outputs 或 .runtime/runs 下的运行子目录")
    saved = index()
    key = str(root)
    if key in saved.archives:
        raise ValueError("原目录已归档；请使用新的运行目录")
    paths = sorted(root.rglob("*"))
    if not root.is_dir() or any(p.is_symlink() for p in paths):
        raise ValueError("运行目录不存在或含符号链接")
    files = [p for p in paths if p.is_file()]
    if not files:
        raise ValueError("不能归档空目录")
    published: list[tuple[Path, Path]] = []
    manifest = (
        json.loads((root / "manifest.json").read_text())
        if (root / "manifest.json").is_file()
        else {}
    )
    if publish:
        day = datetime.fromisoformat(manifest["as_of"]).astimezone(SHANGHAI).date().isoformat()
        name = label or f"{manifest['window']}-{root.name}"
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("表格标签不能包含路径")
        for filename, suffix in [("岗位信息汇总.xlsx", "岗位信息汇总"), ("jobs.xlsx", "严格导入")]:
            source = root / filename
            target = Path("outputs") / day / f"{name}-{suffix}.xlsx"
            if not source.is_file():
                raise ValueError(f"缺少交付文件: {filename}")
            if target.resolve().is_relative_to(root):
                raise ValueError("发布目录不能位于待删除的运行目录内")
            if target.exists():
                raise ValueError(f"拒绝覆盖已发布表格: {target}")
            published.append((source, target))
    archive_path = (
        Path(".runtime/archives") / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.zip"
    )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        raise ValueError("存在未登记压缩包，请先检查恢复，不能覆盖")
    temporary = archive_path.with_suffix(".zip.tmp")
    hashes = {p.relative_to(root).as_posix(): digest(p) for p in files}
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as packed:
            for path in files:
                packed.write(path, path.relative_to(root).as_posix())
        with zipfile.ZipFile(temporary) as packed:
            for member, expected in hashes.items():
                with packed.open(member) as stream:
                    hashed = hashlib.sha256()
                    while chunk := stream.read(1024 * 1024):
                        hashed.update(chunk)
                    if hashed.hexdigest() != expected:
                        raise ValueError(f"压缩校验失败: {member}")
        # Detect writes during compression; never delete a changed source tree.
        current = {
            p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file()
        }
        if current != hashes:
            raise ValueError("目录在归档期间变化，请停止采集后重试")
        for source, target in published:
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            if digest(target) != hashes[source.name]:
                raise ValueError("发布校验失败，原件保留")
        temporary.replace(archive_path)
        archive = Archive(
            root=key,
            path=str(archive_path.resolve()),
            created=time.time(),
            pinned=pin,
            source_ids=manifest.get("source_ids", []),
            window=manifest.get("window", "all"),
            observed_at=datetime.fromisoformat(manifest["as_of"]).timestamp()
            if manifest.get("as_of")
            else 0.0,
            original_bytes=sum(p.stat().st_size for p in files),
            archive_bytes=archive_path.stat().st_size,
            sha256=digest(archive_path),
            published=[str(p.resolve()) for _, p in published],
        )
        saved.archives[key] = archive
        write_json(INDEX, saved.model_dump())
        shutil.rmtree(root)
        return archive
    finally:
        temporary.unlink(missing_ok=True)


def restore(root: Path, target: Path) -> None:
    archive = index().archives[str(root.absolute())]
    packed = Path(archive.path)
    if digest(packed) != archive.sha256:
        raise ValueError("归档校验失败，拒绝恢复")
    if target.exists():
        raise ValueError("恢复目录必须不存在")
    with zipfile.ZipFile(packed) as saved:
        for member in saved.infolist():
            if (
                not (target / member.filename).resolve().is_relative_to(target.resolve())
                or (member.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("归档含不安全路径")
        target.mkdir(parents=True)
        saved.extractall(target)


def protected_archives(saved: ArchiveIndex) -> set[str]:
    """Protect references in every live state DB, including custom development state paths."""
    protected: set[str] = set()
    databases = set(Path(".runtime").rglob("*.sqlite")) | set(Path("outputs").rglob("*.sqlite"))
    databases.update(Path(p) for p in saved.state_paths)
    for database in databases:
        if not database.is_file():
            raise ValueError(f"状态数据库缺失，停止清理: {database}")
        with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as db:
            tables = {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "source_history" not in tables:
                continue
            for (snapshot,) in db.execute("SELECT snapshot FROM source_history"):
                for root in saved.archives:
                    if root in snapshot or str(Path(root).relative_to(Path.cwd())) in snapshot:
                        protected.add(root)
    return protected


@locked
def maintenance(
    *,
    apply: bool = False,
    days: int = 30,
    cache_days: int = 90,
    cache_mb: int = 2048,
    cache_dirs: list[Path] | None = None,
) -> dict[str, object]:
    if min(days, cache_days, cache_mb) < 1:
        raise ValueError("保留期限和容量必须为正数")
    saved = index()
    protected = protected_archives(saved)
    latest: dict[tuple[str, str], Archive] = {}
    for archive in sorted(saved.archives.values(), key=lambda a: (a.observed_at, a.created)):
        for source in archive.source_ids:
            latest[(source, archive.window)] = archive
    protected.update(a.root for a in latest.values())
    now = time.time()
    expired = {
        k: a
        for k, a in saved.archives.items()
        if not a.pinned and k not in protected and now - a.created > days * 86400
    }
    candidates = sorted(
        {
            p
            for folder in (
                cache_dirs or [Path(".runtime/classification"), Path(".runtime/education")]
            )
            for p in folder.rglob("*.json")
            if p.is_file() and not p.is_symlink()
        },
        key=lambda p: p.stat().st_mtime,
    )
    total = sum(p.stat().st_size for p in candidates)
    discard: list[Path] = []
    for path in candidates:
        if now - path.stat().st_mtime > cache_days * 86400 or total > cache_mb * 1024**2:
            discard.append(path)
            total -= path.stat().st_size
    report: dict[str, object] = {
        "apply": apply,
        "archives": [a.path for a in expired.values()],
        "cache_files": len(discard),
        "protected_archives": len(protected),
        "reclaim_bytes": sum(Path(a.path).stat().st_size for a in expired.values())
        + sum(p.stat().st_size for p in discard),
    }
    if apply:
        for key, archive in expired.items():
            Path(archive.path).unlink()
            del saved.archives[key]
        write_json(INDEX, saved.model_dump())
        for path in discard:
            path.unlink()
    return report
