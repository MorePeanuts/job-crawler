"""Adapter primitives. Transport JSON is validated at this boundary."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from job_crawler.models import Collection, Issue, Job, Scope, Source
from job_crawler.transport import CrawlError, Session


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(text(item) for item in value)
    if isinstance(value, dict):
        # Do not stringify an unknown shape and masquerade it as normalized text.
        raise ValueError("文本字段返回未知对象结构")
    return BeautifulSoup(str(value), "html.parser").get_text("\n", strip=True)


def query(url: str, **updates: Any) -> str:
    parts = urlsplit(url)
    values = dict(parse_qs(parts.query, keep_blank_values=True))
    values.update({key: [str(value)] for key, value in updates.items()})
    return urlunsplit(parts._replace(query=urlencode(values, doseq=True)))


class Adapter:
    name = ""
    version = "1"
    host = ""
    path = ""
    scope_description = ""

    def __init__(self, source: Source, session: Session, collected_at: datetime):
        self.source = source
        self.session = session
        self.collected_at = collected_at
        self.result = Collection(scope_description=self.scope_description)

    async def collect(self) -> Collection:
        try:
            if urlsplit(self.source.url).hostname != self.host:
                raise CrawlError("entry_mismatch", "来源 URL 与绑定平台不匹配，需要重新接入")
            await self.session.open(f"https://{self.host}{self.path}")
            await self.harvest()
        except Exception as exc:
            self.error(exc)
        return self.result

    def error(self, exc: Exception, key: str = "") -> None:
        self.result.issues.append(
            Issue(
                code=exc.code if isinstance(exc, CrawlError) else "parse_or_request_error",
                message=str(exc)[:1000],
                source_id=self.source.source_id,
                job_key=key,
                url=self.source.url,
            )
        )

    def job(self, key: str, **fields: Any) -> Job:
        return Job(
            source_id=self.source.source_id,
            source_key=key,
            company=self.source.company,
            collected_at=self.collected_at,
            evidence=[self.session.last_evidence],
            **fields,
        )

    def add_page(
        self,
        scope: Scope,
        rows: list[dict[str, Any]],
        seen: set[str],
        key: Callable[[dict[str, Any]], str],
    ) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            raise CrawlError("schema_changed", "岗位列表不是数组")
        fresh = []
        scope.listed += len(rows)
        for row in rows:
            identity = key(row)
            if not identity or identity == "None":
                raise CrawlError("missing_identity", "缺少源对象 ID")
            if identity in seen:
                raise CrawlError("duplicate_page", "重复岗位或分页循环，停止受影响范围")
            seen.add(identity)
            fresh.append(row)
        scope.unique = len(seen)
        scope.evidence.append(self.session.last_evidence)
        return fresh

    async def harvest(self) -> None:
        raise NotImplementedError
