"""Durable per-run request state and first/last-seen indexes."""

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from job_crawler.models import Job

SECRET_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "csrf",
    "sessionid",
    "session_id",
    "password",
    "accesstoken",
    "refreshtoken",
    "csrftoken",
    "csrf_token",
}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if str(k).lower() in SECRET_KEYS else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value, strict=False)
                if isinstance(parsed, (dict, list)):
                    return json.dumps(redact(parsed), ensure_ascii=False)
            except ValueError:
                pass
        return re.sub(
            r"(?i)([?&](?:token|access_?token|refresh_?token|session_?id|_?csrf|api_?key)=)[^&\s\"<>]+",
            r"\1[REDACTED]",
            value,
        )
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, fingerprint TEXT, started TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS requests (run_id TEXT, source TEXT, key TEXT, state TEXT, evidence TEXT, error TEXT, PRIMARY KEY(run_id,source,key));
            CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, first_seen TEXT, last_seen TEXT, job TEXT);
        """)

    def close(self) -> None:
        self.db.close()

    def begin(
        self, run_id: str, digest: str, now: datetime, resume: bool, max_age_hours: float
    ) -> None:
        row = self.db.execute(
            "SELECT fingerprint,started FROM runs WHERE id=?", (run_id,)
        ).fetchone()
        if row:
            age = (now - datetime.fromisoformat(row[1])).total_seconds()
            if not resume or row[0] != digest or not 0 <= age <= max_age_hours * 3600:
                raise ValueError("运行已存在、参数/代码已变化或检查点已过期；请创建新运行")
        elif resume:
            raise ValueError("不存在可恢复运行")
        else:
            self.db.execute(
                "INSERT INTO runs VALUES (?,?,?,?)", (run_id, digest, now.isoformat(), "running")
            )
        self.db.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
        self.db.commit()

    def request(
        self, run_id: str, source: str, key: str, state: str, evidence: str = "", error: str = ""
    ) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO requests VALUES (?,?,?,?,?,?)",
            (run_id, source, key, state, evidence, redact(error)),
        )
        self.db.commit()

    def cached(self, run_id: str, source: str, key: str) -> str | None:
        row = self.db.execute(
            "SELECT evidence FROM requests WHERE run_id=? AND source=? AND key=? AND state='done'",
            (run_id, source, key),
        ).fetchone()
        return row[0] if row else None

    def save(self, jobs: list[Job]) -> None:
        for job in jobs:
            timestamp = job.collected_at.isoformat()
            self.db.execute(
                "INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET last_seen=excluded.last_seen,job=excluded.job",
                (
                    job.key,
                    timestamp,
                    timestamp,
                    json.dumps(redact(job.model_dump(mode="json")), ensure_ascii=False),
                ),
            )
        self.db.commit()

    def finish(self, run_id: str, status: str) -> None:
        self.db.execute("UPDATE runs SET status=? WHERE id=?", (status, run_id))
        self.db.commit()
